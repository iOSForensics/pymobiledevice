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
from __future__ import print_function
from six import PY3
import struct
import time
import sys
import logging

from pymobiledevice.lockdown import LockdownClient

from tempfile import mkstemp
from optparse import OptionParser

"""
struct pcap_hdr_s {
        guint32 magic_number;   /* magic number */
        guint16 version_major;  /* major version number */
        guint16 version_minor;  /* minor version number */
        gint32  thiszone;       /* GMT to local correction */
        guint32 sigfigs;        /* accuracy of timestamps */
        guint32 snaplen;        /* max length of captured packets, in octets */
        guint32 network;        /* data link type */
} pcap_hdr_t;
typedef struct pcaprec_hdr_s {
        guint32 ts_sec;         /* timestamp seconds */
        guint32 ts_usec;        /* timestamp microseconds */
        guint32 incl_len;       /* number of octets of packet saved in file */
        guint32 orig_len;       /* actual length of packet */
} pcaprec_hdr_t;
"""
LINKTYPE_ETHERNET = 1
LINKTYPE_RAW = 101


class PcapOut(object):

    def __init__(self, pipename=r'test.pcap'):
        self.pipe = open(pipename, 'wb')
        self.pipe.write(struct.pack("<LHHLLLL", 0xa1b2c3d4, 2, 4, 0, 0, 65535, LINKTYPE_ETHERNET))

    def __del__(self):
        self.pipe.close()

    def writePacket(self, packet):
        t = time.time()
        # TODO check milisecond conversion
        pkthdr = struct.pack('<LLLL', int(t), int(t * 1000000 % 1000000), len(packet), len(packet))
        data = pkthdr + packet
        l = self.pipe.write(data)
        self.pipe.flush()
        return True


class Win32Pipe(object):
    def __init__(self, pipename=r'\\.\pipe\wireshark'):
        self.pipe = win32pipe.CreateNamedPipe(pipename,
                                              win32pipe.PIPE_ACCESS_OUTBOUND,
                                              win32pipe.PIPE_TYPE_MESSAGE | win32pipe.PIPE_WAIT,
                                              1, 65536, 65536,
                                              300,
                                              None)
        print("Connect wireshark to %s" % pipename)
        win32pipe.ConnectNamedPipe(self.pipe, None)
        win32file.WriteFile(self.pipe, struct.pack("<LHHLLLL", 0xa1b2c3d4, 2, 4, 0, 0, 65535, LINKTYPE_ETHERNET))

    def writePacket(self, packet):
        t = time.time()
        pkthdr = struct.pack("<LLLL", int(t), int(t * 1000000 % 1000000), len(packet), len(packet))
        errCode, nBytesWritten = win32file.WriteFile(self.pipe, pkthdr + packet)
        return errCode == 0


if __name__ == "__main__":
    if sys.platform == "darwin":
        print("Why not use rvictl ?")

    parser = OptionParser(usage="%prog")
    parser.add_option("-u", "--udid",
                      default=False, action="store", dest="device_udid", metavar="DEVICE_UDID",
                      help="Device udid")
    parser.add_option("-o", "--output", dest="output", default=False,
                      help="Output location", type="string")

    (options, args) = parser.parse_args()
    if sys.platform == "win32":
        import win32pipe, win32file

        output = Win32Pipe()

    else:
        if options.output:
            path = options.output
        else:
            _, path = mkstemp(prefix="device_dump_", suffix=".pcap", dir=".")
        print("Recording data to: %s" % path)
        output = PcapOut(path)

    logging.basicConfig(level=logging.INFO)
    lockdown = LockdownClient(options.device_udid)
    pcap = lockdown.start_service("com.apple.pcapd")

    while True:
        d = pcap.recv_plist()
        if not d:
            break
        if not PY3:
            d = d.data
        hdrsize, xxx, packet_size = struct.unpack(">LBL", d[:9])
        flags1, flags2, offset_to_ip_data, zero = struct.unpack(">LLLL", d[9:0x19])

        assert hdrsize >= 0x19
        if PY3:
            interfacetype = d[0x19:hdrsize].strip(b"\x00")
        else:
            interfacetype = d[0x19:hdrsize].strip("\x00")
            interfacetype = "b'" + "\\x".join("{:02x}".format(ord(c)) for c in interfacetype) + "'"
        t = time.time()
        print(interfacetype, packet_size, t)
        packet = d[hdrsize:]
        assert packet_size == len(packet)

        if offset_to_ip_data == 0:
            # add fake ethernet header for pdp packets
            if PY3:
                packet = b"\xBE\xEF" * 6 + b"\x08\x00" + packet
            else:
                packet = "\xBE\xEF" * 6 + "\x08\x00" + packet
        if not output.writePacket(packet):
            break
