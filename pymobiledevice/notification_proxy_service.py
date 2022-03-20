#!/usr/bin/env python
import logging

from pymobiledevice.lockdown import LockdownClient


class NotificationProxyService(object):
    def __init__(self, lockdown=None, service_name="com.apple.mobile.notification_proxy", udid=None, logger=None):
        self.logger = logger or logging.getLogger(__name__)
        self.lockdown = lockdown if lockdown else LockdownClient(udid=udid)
        self.service = self.lockdown.start_service(service_name)

    def notify_post(self, name):
        """ Send notification to the device's notification_proxy. """
        self.service.send_plist({"Command": "PostNotification",
                                 "Name": name})

        self.service.send_plist({"Command": "Shutdown"})
        res = self.service.recv_plist()
        if res.get("Command", None) != "ProxyDeath":
            raise Exception(f'invalid response: {res}')

    def notify_register_dispatch(self, name):
        """ Tells the device to send a notification on the specified event. """
        self.logger.info("Observing %s", name)
        self.service.send_plist({"Command": "ObserveNotification",
                                 "Name": name})

    def receive_notification(self):
        while True:
            yield self.service.recv_plist()
