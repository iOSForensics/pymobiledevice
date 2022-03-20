#!/usr/bin/env python3
import os
from pprint import pprint
import logging
import json

from termcolor import colored
import coloredlogs
import IPython
import click
from pygments import highlight, lexers, formatters

from pymobiledevice.afc import AFCShell, AFCClient
from pymobiledevice.diagnostics_service import DiagnosticsService
from pymobiledevice.installation_proxy_service import InstallationProxyService
from pymobiledevice.lockdown import LockdownClient
from pymobiledevice.mobile_config import MobileConfigService
from pymobiledevice.notification_proxy_service import NotificationProxyService
from pymobiledevice.os_trace_service import OsTraceService
from pymobiledevice.pcapd_service import PcapdService
from pymobiledevice.screenshot_service import ScreenshotService
from pymobiledevice.dvt_secure_socket_proxy import DvtSecureSocketProxyService

coloredlogs.install(level=logging.DEBUG)

logging.getLogger('asyncio').disabled = True
logging.getLogger('parso.cache').disabled = True
logging.getLogger('parso.cache.pickle').disabled = True
logging.getLogger('parso.python.diff').disabled = True
logging.getLogger('humanfriendly.prompts').disabled = True


def print_object(buf, colored=True):
    if colored:
        formatted_json = json.dumps(buf, sort_keys=True, indent=4)
        colorful_json = highlight(formatted_json, lexers.JsonLexer(), formatters.TerminalFormatter())
        print(colorful_json)
    else:
        pprint(buf)


class Command(click.Command):
    @staticmethod
    def udid(ctx, param, value):
        return LockdownClient(udid=value)

    def __init__(self, *args, **kwargs):
        super(Command, self).__init__(*args, **kwargs)
        self.params[:0] = [
            click.Option(('lockdown', '--udid'), callback=self.udid)
        ]


@click.group()
def cli():
    pass


@cli.group()
def apps():
    """ application options """
    pass


@apps.command('list', cls=Command)
@click.option('-u', '--user', is_flag=True, help='include user apps')
@click.option('-s', '--system', is_flag=True, help='include system apps')
def apps_list(lockdown, user, system):
    """ list installed apps """
    app_types = []
    if user:
        app_types.append('User')
    if system:
        app_types.append('System')
    pprint(InstallationProxyService(lockdown=lockdown).get_apps(app_types))


@apps.command('uninstall', cls=Command)
@click.argument('bundle_id')
def apps_uninstall(lockdown, bundle_id):
    """ uninstall app by given bundle_id """
    pprint(InstallationProxyService(lockdown=lockdown).uninstall(bundle_id))


@apps.command('install', cls=Command)
@click.argument('ipa_path', type=click.Path(exists=True))
def apps_install(lockdown, ipa_path):
    """ install given .ipa """
    pprint(InstallationProxyService(lockdown=lockdown).install_from_local(ipa_path))


@cli.group()
def config():
    """ configuration options """
    pass


@config.command('list', cls=Command)
def config_list(lockdown):
    """ list installed profiles """
    pprint(MobileConfigService(lockdown=lockdown).get_profile_list())


@config.command('install', cls=Command)
@click.argument('profile', type=click.File('rb'))
def config_install(lockdown, profile):
    """ install given profile file """
    pprint(MobileConfigService(lockdown=lockdown).install_profile(profile.read()))


@config.command('remove', cls=Command)
@click.argument('name')
def config_remove(lockdown, name):
    """ remove profile by name """
    pprint(MobileConfigService(lockdown=lockdown).remove_profile(name))


@cli.group()
def lockdown():
    """ lockdown options """
    pass


@lockdown.command('recovery', cls=Command)
def lockdown_recovery(lockdown):
    """ enter recovery """
    pprint(lockdown.enter_recovery())


@lockdown.command('service', cls=Command)
@click.argument('service_name')
def lockdown_service(lockdown, service_name):
    """ send-receive raw service messages """
    client = lockdown.start_service(service_name)
    logging.info('use `client` variable to interact with the connected service')
    IPython.embed()


@cli.group()
def diagnostics():
    """ diagnostics options """
    pass


@diagnostics.command('restart', cls=Command)
def diagnostics_restart(lockdown):
    """ restart device """
    DiagnosticsService(lockdown=lockdown).restart()


@diagnostics.command('shutdown', cls=Command)
def diagnostics_shutdown(lockdown):
    """ shutdown device """
    DiagnosticsService(lockdown=lockdown).shutdown()


@diagnostics.command('sleep', cls=Command)
def diagnostics_sleep(lockdown):
    """ put device into sleep """
    DiagnosticsService(lockdown=lockdown).sleep()


@diagnostics.command('info', cls=Command)
def diagnostics_info(lockdown):
    """ get diagnostics info """
    pprint(DiagnosticsService(lockdown=lockdown).info())


@diagnostics.command('ioregistry', cls=Command)
@click.option('--plane')
@click.option('--name')
@click.option('--ioclass')
def diagnostics_ioregistry(lockdown, plane, name, ioclass):
    """ get ioregistry info """
    pprint(DiagnosticsService(lockdown=lockdown).ioregistry(plane=plane, name=name, ioclass=ioclass))


@diagnostics.command('mg', cls=Command)
@click.argument('keys', nargs=-1, default=None)
def diagnostics_mg(lockdown, keys):
    """ get MobileGestalt key values from given list. If empty, return all known. """
    pprint(DiagnosticsService(lockdown=lockdown).mobilegestalt(keys=keys))


@cli.group()
def syslog():
    """ syslog options """
    pass


@syslog.command('live', cls=Command)
@click.option('-o', '--out', type=click.File('wt'), help='log file')
@click.option('--nocolor', is_flag=True, help='disable colors')
@click.option('--pid', type=click.INT, default=-1, help='pid to filter. -1 for all')
@click.option('-m', '--match', help='match expression')
def syslog_live(lockdown, out, nocolor, pid, match):
    """ view live syslog lines """

    log_level_colors = {
        'Notice': 'white',
        'Error': 'red',
        'Fault': 'red',
        'Warning': 'yellow',
    }

    for syslog_entry in OsTraceService(lockdown=lockdown).syslog(pid=pid):
        pid = syslog_entry.pid
        timestamp = syslog_entry.timestamp
        level = syslog_entry.level
        filename = syslog_entry.filename
        image_name = os.path.basename(syslog_entry.image_name)
        message = syslog_entry.message
        process_name = os.path.basename(filename)

        if not nocolor:
            timestamp = colored(str(timestamp), 'green')
            process_name = colored(process_name, 'magenta')
            if len(image_name) > 0:
                image_name = colored(image_name, 'magenta')
            pid = colored(syslog_entry['pid'], 'cyan')

            if level in syslog_entry:
                level = colored(level, log_level_colors[level])

            message = colored(syslog_entry['message'], 'white')

        line = '{timestamp} {process_name}{{{image_name}}}[{pid}] <{level}>: {message}'.format(
            timestamp=timestamp, process_name=process_name, image_name=image_name, pid=pid, level=level,
            message=message,
        )

        if match and match not in line:
            continue

        print(line)

        if out:
            out.write(line)


@syslog.command('archive', cls=Command)
@click.argument('out', type=click.File('wb'))
def syslog_archive(lockdown, out):
    """
    create PAX archive.
    use `pax -r < filename` for extraction.
    """
    result, tar = OsTraceService(lockdown=lockdown).create_archive()
    out.write(tar)


@cli.command(cls=Command)
@click.argument('out', type=click.File('wb'), required=False)
def pcap(lockdown, out):
    """ sniff device traffic """
    PcapdService(lockdown=lockdown).watch(out=out)


@cli.command(cls=Command)
@click.argument('out', type=click.File('wb'))
def screenshot(lockdown, out):
    """ take a screenshot in TIFF format """
    out.write(ScreenshotService(lockdown=lockdown).take_screenshot())


@cli.command(cls=Command)
@click.argument('action', type=click.Choice(['flush', 'shell']))
def crash(lockdown, action):
    """ crash utils """
    if action == 'flush':
        ack = b'ping\x00'
        assert ack == lockdown.start_service('com.apple.crashreportmover').recv_exact(len(ack))
    elif action == 'shell':
        AFCShell(udid=udid, afcname='com.apple.crashreportcopymobile').cmdloop()


@cli.group()
def afc():
    """ FileSystem utils """
    pass


@afc.command('shell', cls=Command)
def afc_shell(lockdown):
    """ open an AFC shell rooted at /var/mobile/Media """
    AFCShell(lockdown=lockdown, afcname='com.apple.afc').cmdloop()


@afc.command('pull', cls=Command)
@click.argument('remote_file', type=click.Path(exists=False))
@click.argument('local_file', type=click.File('wb'))
def afc_pull(lockdown, remote_file, local_file):
    """ open an AFC shell rooted at /var/mobile/Media """
    local_file.write(AFCClient(lockdown=lockdown).get_file_contents(remote_file))


@afc.command('push', cls=Command)
@click.argument('local_file', type=click.File('rb'))
@click.argument('remote_file', type=click.Path(exists=False))
def afc_push(lockdown, local_file, remote_file):
    """ open an AFC shell rooted at /var/mobile/Media """
    AFCClient(lockdown=lockdown).set_file_contents(remote_file, local_file.read())


@afc.command('ls', cls=Command)
@click.argument('remote_file', type=click.Path(exists=False))
def afc_ls(lockdown, remote_file):
    """ open an AFC shell rooted at /var/mobile/Media """
    pprint(AFCClient(lockdown=lockdown).read_directory(remote_file))


@afc.command('rm', cls=Command)
@click.argument('remote_file', type=click.Path(exists=False))
def afc_rm(lockdown, remote_file):
    """ open an AFC shell rooted at /var/mobile/Media """
    AFCClient(lockdown=lockdown).file_remove(remote_file)


@cli.command(cls=Command)
def ps(lockdown):
    """ show process list """
    pprint(OsTraceService(lockdown=lockdown).get_pid_list())


@cli.command(cls=Command)
@click.argument('action', type=click.Choice(['post', 'observe']))
@click.argument('names', nargs=-1)
def notification(lockdown, action, names):
    """ API for notify_post() & notify_register_dispatch(). """
    service = NotificationProxyService(lockdown=lockdown)
    for name in names:
        if action == 'post':
            service.notify_post(name)
        elif action == 'observe':
            service.notify_register_dispatch(name)

    if action == 'observe':
        for event in service.receive_notification():
            logging.info(event)


@cli.group()
def developer():
    """ developer options """
    pass


@developer.command('proclist', cls=Command)
@click.option('--nocolor', is_flag=True)
def proclist(lockdown, nocolor):
    """ show process list """
    with DvtSecureSocketProxyService(lockdown=lockdown) as dvt:
        processes = dvt.proclist()
        for process in processes:
            if 'startDate' in process:
                process['startDate'] = str(process['startDate'])

        print_object(processes, colored=not nocolor)


@developer.command('applist', cls=Command)
@click.option('--nocolor', is_flag=True)
def applist(lockdown, nocolor):
    """ show application list """
    with DvtSecureSocketProxyService(lockdown=lockdown) as dvt:
        apps = dvt.applist()
        print_object(apps, colored=not nocolor)


@developer.command('kill', cls=Command)
@click.argument('pid', type=click.INT)
def kill(lockdown, pid):
    """ Kill a process by its pid. """
    with DvtSecureSocketProxyService(lockdown=lockdown) as dvt:
        dvt.kill(pid)


@developer.command('launch', cls=Command)
@click.argument('bundle_id', type=click.STRING)
def launch(lockdown, bundle_id):
    """ Kill a process by its pid. """
    with DvtSecureSocketProxyService(lockdown=lockdown) as dvt:
        pid = dvt.launch(bundle_id)
        print(f'Process launched with pid {pid}')


@developer.command('shell', cls=Command)
def shell(lockdown):
    """ Launch developer shell. """
    with DvtSecureSocketProxyService(lockdown=lockdown) as dvt:
        dvt.shell()


@developer.command('ls', cls=Command)
@click.argument('path', type=click.Path(exists=False))
def ls(lockdown, path):
    """ Launch developer shell. """
    with DvtSecureSocketProxyService(lockdown=lockdown) as dvt:
        pprint(dvt.ls(path))


@developer.command('ls', cls=Command)
@click.argument('path', type=click.Path(exists=False))
def ls(lockdown, path):
    """ Launch developer shell. """
    with DvtSecureSocketProxyService(lockdown=lockdown) as dvt:
        pprint(dvt.ls(path))


if __name__ == '__main__':
    cli()
