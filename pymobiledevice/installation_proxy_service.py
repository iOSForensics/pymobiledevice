#!/usr/bin/env python
# -*- coding: utf8 -*-
#
# $Id$
#
# Copyright (c) 2012-2014 "dark[-at-]gotohack.org"
#
# This file is part of pymobiledevice
#
# pymobiledevice is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
#

import logging
import os
import posixpath

from pymobiledevice.lockdown import LockdownClient
from pymobiledevice.afc import AFCClient

client_options = {
    "SkipUninstall": False,
    "ApplicationSINF": False,
    "iTunesMetadata": False,
    "ReturnAttributes": False
}


class InstallationProxyService(object):
    def __init__(self, lockdown=None, udid=None, logger=None):
        self.logger = logger or logging.getLogger(__name__)
        self.lockdown = lockdown if lockdown else LockdownClient(udid=udid)
        if not self.lockdown:
            raise Exception("Unable to start lockdown")
        self.service = self.lockdown.start_service("com.apple.mobile.installation_proxy")

    def watch_completion(self, handler=None, *args):
        while True:
            response = self.service.recv_plist()
            if not response:
                break
            error = response.get('Error')
            if error:
                raise IOError(f'{error}: {response.get("ErrorDescription")}')
            completion = response.get("PercentComplete")
            if completion:
                if handler:
                    self.logger.debug("calling handler")
                    handler(completion, *args)
                self.logger.info("%s %% Complete", response.get("PercentComplete"))
            if response.get("Status") == "Complete":
                return response.get("Status")
        return "Error"

    def send_cmd_for_bid(self, bid, cmd="Archive", options=None, handler=None, *args):
        cmd = {"Command": cmd,
               "ApplicationIdentifier": bid}
        if options:
            cmd.update({"ClientOptions": options})
        self.service.send_plist(cmd)
        self.logger.info("%s : %s\n", cmd, self.watch_completion(handler, *args))

    def uninstall(self, bid, options=None, handler=None, *args):
        return self.send_cmd_for_bid(bid, "Uninstall", options, handler, args)

    def install_from_local(self, ipa_path, cmd="Install", options=None, handler=None, *args):
        if options is None:
            options = {}
        remote_path = posixpath.join('/', os.path.basename(ipa_path))
        afc = AFCClient(self.lockdown)
        afc.set_file_contents(remote_path, open(ipa_path, "rb").read())
        cmd = {"Command": cmd,
               "ClientOptions": options,
               "PackagePath": remote_path}
        self.service.send_plist(cmd)
        self.watch_completion(handler, args)

    def install(self, ipa_path, options=None, handler=None, *args):
        if options is None:
            options = {}
        return self.install_from_local(ipa_path, "Install", options, handler, args)

    def upgrade(self, ipa_path, options=None, handler=None, *args):
        if options is None:
            options = {}
        return self.install_from_local(ipa_path, "Upgrade", options, handler, args)

    def check_capabilities_match(self, capabilities, options=None):
        if options is None:
            options = {}
        cmd = {"Command": "CheckCapabilitiesMatch",
               "ClientOptions": options}

        if capabilities:
            cmd["Capabilities"] = capabilities

        self.service.send_plist(cmd)
        result = self.service.recv_plist().get("LookupResult")
        return result

    def browse(self, options=None, attributes=None):
        if options is None:
            options = {}
        if attributes:
            options["ReturnAttributes"] = attributes

        cmd = {"Command": "Browse",
               "ClientOptions": options}

        self.service.send_plist(cmd)

        result = []
        while True:
            z = self.service.recv_plist()
            if not z:
                break

            data = z.get("CurrentList")
            if data:
                result += data

            if z.get("Status") == "Complete":
                break

        return result

    def apps_info(self, options=None):
        if options is None:
            options = {}
        cmd = {"Command": "Lookup",
               "ClientOptions": options}

        self.service.send_plist(cmd)
        return self.service.recv_plist().get('LookupResult')

    def archive(self, bid, options=None, handler=None, *args):
        if options is None:
            options = {}
        self.send_cmd_for_bid(bid, "Archive", options, handler, args)

    def restore_archive(self, bid, options=None, handler=None, *args):
        if options is None:
            options = {}
        self.send_cmd_for_bid(bid, "Restore", options, handler, args)

    def remove_archive(self, bid, options=None, handler=None, *args):
        if options is None:
            options = {}
        self.send_cmd_for_bid(bid, "RemoveArchive", options, handler, args)

    def archives_info(self, options=None):
        if options is None:
            options = {}
        cmd = {"Command": "LookupArchive",
               "ClientOptions": options}
        return self.service.send_request(cmd).get("LookupResult")

    def search_path_for_bid(self, bid):
        path = None
        for a in self.get_apps(app_types=["User", "System"]):
            if a.get("CFBundleIdentifier") == bid:
                path = a.get("Path") + "/" + a.get("CFBundleExecutable")
        return path

    def get_apps(self, app_types=None):
        if app_types is None:
            app_types = ["User"]
        return [app for app in self.apps_info().values()
                if app.get("ApplicationType") in app_types]

    def print_apps(self, app_types=None):
        if app_types is None:
            app_types = ["User"]
        for app in self.get_apps(app_types):
            print(("%s : %s => %s" % (app.get("CFBundleDisplayName"),
                                      app.get("CFBundleIdentifier"),
                                      app.get("Path") if app.get("Path")
                                      else app.get("Container"))).encode('utf-8'))

    def get_apps_bid(self, app_types=None):
        if app_types is None:
            app_types = ["User"]
        return [app["CFBundleIdentifier"]
                for app in self.get_apps()
                if app.get("ApplicationType") in app_types]

    def close(self):
        self.service.close()
