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

from optparse import OptionParser
from datetime import datetime
from six import PY3
from sys import exit
import logging
import time
import re

from termcolor import colored

from pymobiledevice.lockdown import LockdownClient

CHUNK_SIZE = 4096
TIME_FORMAT = '%H:%M:%S'
SYSLOG_LINE_SPLITTER = '\n\x00'


class Syslog(object):
    """
    View system logs
    """

    def __init__(self, lockdown=None, udid=None, logger=None):
        self.logger = logger or logging.getLogger(__name__)
        self.lockdown = lockdown if lockdown else LockdownClient(udid=udid)
        self.c = self.lockdown.start_service("com.apple.syslog_relay")
        if self.c:
            self.c.send("watch")
        else:
            exit(1)

    def watch(self, watchtime=None, log_file=None, proc_name=None, use_colors=True):
        """
        View log
        :param watchtime: time (seconds)
        :type watchtime: int
        :param log_file: full path to the log file
        :type log_file: str
        :param proc_name: process name
        :type proc_name: str
        """
        syslog_exp = re.compile(
            r'(?P<month>\w+)\s+(?P<day>\d+)\s+(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2}) '
            r'(?P<device_name>.+?) (?P<process>.+?)(\((?P<image_name>.+?)\))?\[(?P<pid>\d+)\] '
            r'<(?P<level>\w+)>: (?P<message>.+)')
        begin = time.strftime(TIME_FORMAT)
        buf = ''

        start_time = time.time()

        while True:
            # read in chunks till we have at least one syslog line
            chunk = self.c.recv(CHUNK_SIZE)
            if PY3:
                chunk = chunk.decode('utf-8')

            buf += chunk

            # SYSLOG_LINE_SPLITTER is used to split each syslog line
            if SYSLOG_LINE_SPLITTER in buf:
                lines = buf.split(SYSLOG_LINE_SPLITTER)

                # handle partial last lines
                if not buf.endswith(SYSLOG_LINE_SPLITTER):
                    buf = lines[-1]
                    lines = lines[:-1]

                for line in lines:
                    if len(line) == 0:
                        continue

                    syslog_entry = syslog_exp.match(line)
                    if syslog_entry is None:
                        raise Exception('failed to parse log line: {}'.format(line))

                    syslog_entry = syslog_entry.groupdict()

                    if proc_name:
                        if syslog_entry['process'] != proc_name:
                            continue

                    # use real year since the syslog entry doesn't store that information
                    timestamp = datetime.strptime('{year} {month} {day} {hour}:{minute}:{second}'.format(
                        year=datetime.now().year, month=syslog_entry['month'], day=syslog_entry['day'],
                        hour=syslog_entry['hour'], minute=syslog_entry['minute'], second=syslog_entry['second']
                    ), '%Y %b %d %H:%M:%S')

                    timestamp = str(timestamp)
                    process = syslog_entry['process']
                    image_name = ''
                    if syslog_entry['image_name'] is not None:
                        image_name = '({})'.format(syslog_entry['image_name'])
                    pid = syslog_entry['pid']
                    level = syslog_entry['level']
                    message = syslog_entry['message']

                    if use_colors:
                        timestamp = colored(str(timestamp), 'green')
                        process = colored(process, 'magenta')
                        if len(image_name) > 0:
                            image_name = colored(image_name, 'magenta')
                        pid = colored(syslog_entry['pid'], 'cyan')
                        level = colored(syslog_entry['level'], {
                            'Notice': 'white',
                            'Error': 'red',
                            'Fault': 'red',
                            'Warning': 'yellow',
                        }[level])

                        message = colored(syslog_entry['message'], 'white')

                    print('{timestamp} {process}{image_name}[{pid}] <{level}>: {message}'.format(
                        timestamp=timestamp, process=process, image_name=image_name, pid=pid, level=level,
                        message=message,
                    ))

                    if log_file:
                        with open(log_file, 'a') as f:
                            f.write(line + '\n')

                    if watchtime:
                        if time.time() - start_time > watchtime:
                            return


if __name__ == "__main__":
    parser = OptionParser(usage="%prog")
    parser.add_option("-u", "--udid",
                      default=False, action="store", dest="device_udid", metavar="DEVICE_UDID",
                      help="Device udid")
    parser.add_option("-p", "--process", dest="procName", default=False,
                      help="Show process log only", type="string")
    parser.add_option("-o", "--logfile", dest="logFile", default=False,
                      help="Write Logs into specified file", type="string")
    parser.add_option("-w", "--watch-time",
                      default=False, action="store", dest="watchtime", metavar="WATCH_TIME",
                      help="watchtime")
    (options, args) = parser.parse_args()

    try:
        try:
            logging.basicConfig(level=logging.INFO)
            lckdn = LockdownClient(options.device_udid)
            syslog = Syslog(lockdown=lckdn)
            syslog.watch(watchtime=int(options.watchtime), proc_name=options.procName, log_file=options.logFile)
        except KeyboardInterrupt:
            print("KeyboardInterrupt caught")
            raise
        else:
            pass
    except (KeyboardInterrupt, SystemExit):
        exit()
