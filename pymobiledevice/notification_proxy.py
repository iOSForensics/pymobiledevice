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

import time
import plistlib
import time
import logging

from pymobiledevice.lockdown import LockdownClient

from six.moves import _thread as thread
from pprint import pprint

# NP Client to device Notifications (post_notification)
NP_SYNC_WILL_START           = "com.apple.itunes-mobdev.syncWillStart"
NP_SYNC_DID_START            = "com.apple.itunes-mobdev.syncDidStart"
NP_SYNC_DID_FINISH           = "com.apple.itunes-mobdev.syncDidFinish"
NP_SYNC_LOCK_REQUEST         = "com.apple.itunes-mobdev.syncLockRequest"

# Device to NP Client Notifications (get_notification)
NP_SYNC_CANCEL_REQUEST       = "com.apple.itunes-client.syncCancelRequest"
NP_SYNC_SUSPEND_REQUEST      = "com.apple.itunes-client.syncSuspendRequest"
NP_SYNC_RESUME_REQUEST       = "com.apple.itunes-client.syncResumeRequest"
NP_PHONE_NUMBER_CHANGED      = "com.apple.mobile.lockdown.phone_number_changed"
NP_DEVICE_NAME_CHANGED       = "com.apple.mobile.lockdown.device_name_changed"
NP_TIMEZONE_CHANGED          = "com.apple.mobile.lockdown.timezone_changed"
NP_TRUSTED_HOST_ATTACHED     = "com.apple.mobile.lockdown.trusted_host_attached"
NP_HOST_DETACHED             = "com.apple.mobile.lockdown.host_detached"
NP_HOST_ATTACHED             = "com.apple.mobile.lockdown.host_attached"
NP_REGISTRATION_FAILED       = "com.apple.mobile.lockdown.registration_failed"
NP_ACTIVATION_STATE          = "com.apple.mobile.lockdown.activation_state"
NP_BRICK_STATE               = "com.apple.mobile.lockdown.brick_state"
NP_DISK_USAGE_CHANGED        = "com.apple.mobile.lockdown.disk_usage_changed"
NP_DS_DOMAIN_CHANGED         = "com.apple.mobile.data_sync.domain_changed"
NP_BACKUP_DOMAIN_CHANGED     = "com.apple.mobile.backup.domain_changed"
NP_APP_INSTALLED             = "com.apple.mobile.application_installed"
NP_APP_UNINSTALLED           = "com.apple.mobile.application_uninstalled"
NP_DEV_IMAGE_MOUNTED         = "com.apple.mobile.developer_image_mounted"
NP_ATTEMPTACTIVATION         = "com.apple.springboard.attemptactivation"
NP_ITDBPREP_DID_END          = "com.apple.itdbprep.notification.didEnd"
NP_LANGUAGE_CHANGED          = "com.apple.language.changed"
NP_ADDRESS_BOOK_PREF_CHANGED = "com.apple.AddressBook.PreferenceChanged"


class NPClient(object):
    def __init__(self, lockdown=None, serviceName="com.apple.mobile.notification_proxy", udid=None, logger=None):
        self.logger = logger or logging.getLogger(__name__)
        self.lockdown = lockdown if lockdown else LockdownClient(udid=udid)
        self.service = self.lockdown.start_service(serviceName)

    def stop_session(self):
        self.logger.info("Disconecting...")
        self.service.close()


    def post_notification(self, notification):
        #Sends a notification to the device's notification_proxy.

        self.service.send_plist({"Command": "PostNotification",
                                "Name": notification})

        self.service.send_plist({"Command": "Shutdown"})
        res = self.service.recv_plist()
        #pprint(res)
        if res:
            if res.get("Command") == "ProxyDeath":
                return res.get("Command")
            else:
                self.logger.error("Got unknown NotificationProxy command %s", res.get("Command"))
                self.logger.debug(res)
        return


    def observe_notification(self, notification):
        #Tells the device to send a notification on the specified event
        self.logger.info("Observing %s", notification)
        self.service.send_plist({"Command": "ObserveNotification",
                                "Name": notification})


    def get_notification(self, notification):
        #Checks if a notification has been sent by the device

        res = self.service.recv_plist()
        if res:
            if res.get("Command") == "RelayNotification":
                if res.get("Name"):
                    return res.get("Name")

            elif res.get("Command") == "ProxyDeath":
                    self.logger.error("NotificationProxy died!")
            else:
                self.logger.warn("Got unknown NotificationProxy command %s", res.get("Command"))
                self.logger.debug(res)
        return


    def notifier(self, name, args=None):

        if args == None:
            return None

        self.observe_notification(args.get("notification"))

        while args.get("running") == True:
            np_name = self.get_notification(args.get("notification"))
            if np_name:
                userdata = args.get("userdata")
                try:
                    thread.start_new_thread( args.get("callback") , (np_name, userdata, ) )
                except:
                    self.logger.error("Error: unable to start thread")

    def subscribe(self, notification, cb, data=None):

        np_data = {
            "running": True,
            "notification": notification,
            "callback": cb,
            "userdata": data,
        }

        thread.start_new_thread( self.notifier, ("NotificationProxyNotifier_"+notification, np_data, ) )
        while(1):
            time.sleep(1)



def cb_test(name,data=None):
    print("Got Notification >> %s" % name)
    print("Data:")
    pprint(data)


if __name__ == "__main__":
    np = NPClient()
    np.subscribe(NP_DEVICE_NAME_CHANGED, cb_test, data=None)

