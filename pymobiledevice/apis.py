#! /usr/bin/env python
# -*- coding: utf-8 -*-
#
# vim: fenc=utf-8
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4
#
#

"""
File name: apis.py
Author: dhilipsiva <dhilipsiva@gmail.com>
Date created: 2016-06-19
"""

from os import path
# from pprint import pprint

from pymobiledevice.afc import AFCClient
from pymobiledevice.lockdown import LockdownClient


class AppManager(object):
    """
    The App Manager
    """

    def __init__(self, udid):
        super(AppManager, self).__init__()
        self.udid = udid
        self.lockdown = LockdownClient(udid)
        self.service = self.lockdown.startService(
            "com.apple.mobile.installation_proxy")

    def install_ipa(self, ipa_path):
        """
        docstring for install_ipa
        """
        afc = AFCClient(lockdown=self.lockdown)
        afc.set_file_contents(
            path.basename(ipa_path), open(ipa_path, "rb").read())
        cmd = {"Command": "Install", "PackagePath": path.basename(ipa_path)}
        return self.service.sendPlist(cmd)

    def uninstall_ipa(self, bundle_id):
        cmd = {"Command": "Uninstall", "ApplicationIdentifier": bundle_id}
        return self.service.sendPlist(cmd)

    def list_ipas(self):
        cmd = {"Command": "Lookup"}
        self.service.sendPlist(cmd)
        apps_details = self.service.recvPlist().get("LookupResult")
        apps = []
        for app in apps_details:
            if apps_details[app]['ApplicationType'] == 'User':
                apps.append(app)
        return apps
