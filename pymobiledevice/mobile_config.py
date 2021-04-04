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

import plistlib
import logging

from pymobiledevice.util import read_file
from pymobiledevice.lockdown import LockdownClient

from optparse import OptionParser
from pprint import pprint


class MobileConfigService(object):
    def __init__(self, lockdown, udid=None, logger=None):
        self.logger = logger or logging.getLogger(__name__)
        self.lockdown = lockdown if lockdown else LockdownClient(udid=udid)
        self.service = lockdown.start_service("com.apple.mobile.MCInstall")

    def get_profile_list(self):
        self.service.send_plist({"RequestType": "GetProfileList"})
        res = self.service.recv_plist()
        if res.get("Status") != "Acknowledged":
            self.logger.error("GetProfileList error")
            self.logger.error(res)
            return
        return res

    def install_profile(self, s):
        self.service.send_plist({"RequestType": "InstallProfile", "Payload": plistlib.Data(s)})
        return self.service.recv_plist()

    def remove_profile(self, ident):
        profiles = self.get_profile_list()
        if not profiles:
            return
        if not profiles["ProfileMetadata"].has_key(ident):
            self.logger.info("Trying to remove not installed profile %s", ident)
            return
        meta = profiles["ProfileMetadata"][ident]
        pprint(meta)
        data = plistlib.writePlistToString({"PayloadType": "Configuration",
                                            "PayloadIdentifier": ident,
                                            "PayloadUUID": meta["PayloadUUID"],
                                            "PayloadVersion": meta["PayloadVersion"]
                                            })
        self.service.send_plist({"RequestType": "RemoveProfile", "ProfileIdentifier": plistlib.Data(data)})
        return self.service.recv_plist()


def main():
    parser = OptionParser(usage="%prog")
    parser.add_option("-l", "--list", dest="list", action="store_true",
                      default=False, help="List installed profiles")
    parser.add_option("-i", "--install", dest="install", action="store",
                      metavar="FILE", help="Install profile")
    parser.add_option("-r", "--remove", dest="remove", action="store",
                      metavar="IDENTIFIER", help="Remove profile")
    (options, args) = parser.parse_args()

    if not options.list and not options.install and not options.remove:
        parser.print_help()
        return
    lockdown = LockdownClient()
    mc = MobileConfigService(lockdown)

    if options.list:
        pprint(mc.get_profile_list())
    elif options.install:
        mc.install_profile(read_file(options.install))
    elif options.remove:
        pprint(mc.remove_profile(options.remove))


if __name__ == "__main__":
    main()
