#!/usr/bin/env python3

from pprint import pprint
from cmd import Cmd
import posixpath
import logging
import struct
import os

from construct import Struct, Const, Int64ul, Container, Switch, Enum, Bytes, Tell, this

from pymobiledevice.lockdown import LockdownClient
from pymobiledevice.util import hexdump, parsePlist

MAXIMUM_READ_SIZE = 1 << 16
MODE_MASK = 0o0000777

afc_opcode_t = Enum(Int64ul,
                    AFC_OP_STATUS=0x00000001,
                    AFC_OP_DATA=0x00000002,  # Data */
                    AFC_OP_READ_DIR=0x00000003,  # ReadDir */
                    AFC_OP_READ_FILE=0x00000004,  # ReadFile */
                    AFC_OP_WRITE_FILE=0x00000005,  # WriteFile */
                    AFC_OP_WRITE_PART=0x00000006,  # WritePart */
                    AFC_OP_TRUNCATE=0x00000007,  # TruncateFile */
                    AFC_OP_REMOVE_PATH=0x00000008,  # RemovePath */
                    AFC_OP_MAKE_DIR=0x00000009,  # MakeDir */
                    AFC_OP_GET_FILE_INFO=0x0000000a,  # GetFileInfo */
                    AFC_OP_GET_DEVINFO=0x0000000b,  # GetDeviceInfo */
                    AFC_OP_WRITE_FILE_ATOM=0x0000000c,  # WriteFileAtomic (tmp file+rename) */
                    AFC_OP_FILE_OPEN=0x0000000d,  # FileRefOpen */
                    AFC_OP_FILE_OPEN_RES=0x0000000e,  # FileRefOpenResult */
                    AFC_OP_READ=0x0000000f,  # FileRefRead */
                    AFC_OP_WRITE=0x00000010,  # FileRefWrite */
                    AFC_OP_FILE_SEEK=0x00000011,  # FileRefSeek */
                    AFC_OP_FILE_TELL=0x00000012,  # FileRefTell */
                    AFC_OP_FILE_TELL_RES=0x00000013,  # FileRefTellResult */
                    AFC_OP_FILE_CLOSE=0x00000014,  # FileRefClose */
                    AFC_OP_FILE_SET_SIZE=0x00000015,  # FileRefSetFileSize (ftruncate) */
                    AFC_OP_GET_CON_INFO=0x00000016,  # GetConnectionInfo */
                    AFC_OP_SET_CON_OPTIONS=0x00000017,  # SetConnectionOptions */
                    AFC_OP_RENAME_PATH=0x00000018,  # RenamePath */
                    AFC_OP_SET_FS_BS=0x00000019,  # SetFSBlockSize (0x800000) */
                    AFC_OP_SET_SOCKET_BS=0x0000001A,  # SetSocketBlockSize (0x800000) */
                    AFC_OP_FILE_LOCK=0x0000001B,  # FileRefLock */
                    AFC_OP_MAKE_LINK=0x0000001C,  # MakeLink */
                    AFC_OP_SET_FILE_TIME=0x0000001E,  # set st_mtime */
                    )

afc_error_t = Enum(Int64ul,
                   AFC_E_SUCCESS=0,
                   AFC_E_UNKNOWN_ERROR=1,
                   AFC_E_OP_HEADER_INVALID=2,
                   AFC_E_NO_RESOURCES=3,
                   AFC_E_READ_ERROR=4,
                   AFC_E_WRITE_ERROR=5,
                   AFC_E_UNKNOWN_PACKET_TYPE=6,
                   AFC_E_INVALID_ARG=7,
                   AFC_E_OBJECT_NOT_FOUND=8,
                   AFC_E_OBJECT_IS_DIR=9,
                   AFC_E_PERM_DENIED=10,
                   AFC_E_SERVICE_NOT_CONNECTED=11,
                   AFC_E_OP_TIMEOUT=12,
                   AFC_E_TOO_MUCH_DATA=13,
                   AFC_E_END_OF_DATA=14,
                   AFC_E_OP_NOT_SUPPORTED=15,
                   AFC_E_OBJECT_EXISTS=16,
                   AFC_E_OBJECT_BUSY=17,
                   AFC_E_NO_SPACE_LEFT=18,
                   AFC_E_OP_WOULD_BLOCK=19,
                   AFC_E_IO_ERROR=20,
                   AFC_E_OP_INTERRUPTED=21,
                   AFC_E_OP_IN_PROGRESS=22,
                   AFC_E_INTERNAL_ERROR=23,
                   AFC_E_MUX_ERROR=30,
                   AFC_E_NO_MEM=31,
                   AFC_E_NOT_ENOUGH_DATA=32,
                   AFC_E_DIR_NOT_EMPTY=33,
                   )

AFC_FOPEN_RDONLY = 0x00000001  # /**< r   O_RDONLY */
AFC_FOPEN_RW = 0x00000002  # /**< r+  O_RDWR   | O_CREAT */
AFC_FOPEN_WRONLY = 0x00000003  # /**< w   O_WRONLY | O_CREAT  | O_TRUNC */
AFC_FOPEN_WR = 0x00000004  # /**< w+  O_RDWR   | O_CREAT  | O_TRUNC */
AFC_FOPEN_APPEND = 0x00000005  # /**< a   O_WRONLY | O_APPEND | O_CREAT */
AFC_FOPEN_RDAPPEND = 0x00000006  # /**< a+  O_RDWR   | O_APPEND | O_CREAT */

AFC_HARDLINK = 1
AFC_SYMLINK = 2

AFC_LOCK_SH = 1 | 4  # /**< shared lock */
AFC_LOCK_EX = 2 | 4  # /**< exclusive lock */
AFC_LOCK_UN = 8 | 4  # /**< unlock */

# not really necessary
MAXIMUM_WRITE_SIZE = 1 << 32

AFCMAGIC = b"CFA6LPAA"

AFCPacket = Struct(
    'magic' / Const(AFCMAGIC),
    'entire_length' / Int64ul,
    'this_length' / Int64ul,
    'packet_num' / Int64ul,
    'operation' / afc_opcode_t,
    '_data_offset' / Tell,
    # 'data' / Bytes(this.entire_length - this._data_offset),
)


def list_to_dict(d):
    d = d.decode('utf-8')
    t = d.split("\x00")
    t = t[:-1]

    assert len(t) % 2 == 0
    res = {}
    for i in range(int(len(t) / 2)):
        res[t[i * 2]] = t[i * 2 + 1]
    return res


class AFCClient(object):
    def __init__(self, lockdown=None, service_name="com.apple.afc", service=None, udid=None, logger=None):
        self.logger = logger or logging.getLogger(__name__)
        self.serviceName = service_name
        self.lockdown = lockdown if lockdown else LockdownClient(udid=udid)
        self.service = service if service else self.lockdown.start_service(self.serviceName)
        self.packet_num = 0

    def _dispatch_packet(self, operation, data, this_length=0):
        afcpack = Container(magic=AFCMAGIC,
                            entire_length=AFCPacket.sizeof() + len(data),
                            this_length=AFCPacket.sizeof() + len(data),
                            packet_num=self.packet_num,
                            operation=operation)
        if this_length:
            afcpack.this_length = this_length
        header = AFCPacket.build(afcpack)
        self.packet_num += 1
        self.service.send(header + data)

    def _receive_data(self):
        res = self.service.recv_exact(AFCPacket.sizeof())
        status = afc_error_t.AFC_E_SUCCESS
        data = ""
        if res:
            res = AFCPacket.parse(res)
            assert res["entire_length"] >= AFCPacket.sizeof()
            length = res["entire_length"] - AFCPacket.sizeof()
            data = self.service.recv_exact(length)
            if res.operation == afc_opcode_t.AFC_OP_STATUS:
                if length != 8:
                    self.logger.error("Status length != 8")
                status = afc_error_t.parse(data)
            elif res.operation != afc_opcode_t.AFC_OP_DATA:
                pass  # print "error ?", res
        return status, data

    def _do_operation(self, opcode, data: bytes = b""):
        self._dispatch_packet(opcode, data)
        status, data = self._receive_data()

        if status != afc_error_t.AFC_E_SUCCESS:
            raise Exception(f'opcode: {opcode} failed with status: {status}')

        return data

    def get_device_info(self):
        return list_to_dict(self._do_operation(afc_opcode_t.AFC_OP_GET_DEVINFO))

    def read_directory(self, dirname):
        data = self._do_operation(afc_opcode_t.AFC_OP_READ_DIR, dirname.encode())
        data = data.decode('utf-8')
        return [x for x in data.split("\x00") if x != ""]

    def make_directory(self, dirname):
        return self._do_operation(afc_opcode_t.AFC_OP_MAKE_DIR, dirname.encode())

    def remove_directory(self, dirname):
        info = self.get_file_info(dirname)
        if not info or info.get("st_ifmt") != "S_IFDIR":
            self.logger.info("remove_directory: %s not S_IFDIR", dirname)
            return

        for d in self.read_directory(dirname):
            if d == "." or d == ".." or d == "":
                continue

            info = self.get_file_info(dirname + "/" + d)
            if info.get("st_ifmt") == "S_IFDIR":
                self.remove_directory(dirname + "/" + d)
            else:
                self.logger.info("%s/%s", dirname, d)
                self.file_remove(dirname + "/" + d)
        assert len(self.read_directory(dirname)) == 2  # .. et .
        return self.file_remove(dirname)

    def get_file_info(self, filename):
        self.logger.info(filename.encode())
        return list_to_dict(self._do_operation(afc_opcode_t.AFC_OP_GET_FILE_INFO, filename.encode()))

    def make_link(self, target, linkname, type=AFC_SYMLINK):
        linkname = linkname.encode('utf-8')
        separator = b"\x00"
        return self._do_operation(afc_opcode_t.AFC_OP_MAKE_LINK,
                                  struct.pack("<Q", type) + target + separator + linkname + separator)

    def file_open(self, filename, mode=AFC_FOPEN_RDONLY):
        filename = filename.encode('utf-8')
        separator = b"\x00"
        data = self._do_operation(afc_opcode_t.AFC_OP_FILE_OPEN, struct.pack("<Q", mode) + filename + separator)
        return struct.unpack("<Q", data)[0]

    def file_close(self, handle):
        return self._do_operation(afc_opcode_t.AFC_OP_FILE_CLOSE, struct.pack("<Q", handle))

    def file_remove(self, filename):
        filename = filename.encode('utf-8')
        separator = b"\x00"
        return self._do_operation(afc_opcode_t.AFC_OP_REMOVE_PATH, filename + separator)

    def file_rename(self, old, new):
        old = old.encode('utf-8')
        new = new.encode('utf-8')
        separator = b"\x00"
        return self._do_operation(afc_opcode_t.AFC_OP_RENAME_PATH, old + separator + new + separator)

    def file_read(self, handle, sz):
        data = b""
        while sz > 0:
            if sz > MAXIMUM_READ_SIZE:
                toRead = MAXIMUM_READ_SIZE
            else:
                toRead = sz
            try:
                self._dispatch_packet(afc_opcode_t.AFC_OP_READ, struct.pack("<QQ", handle, toRead))
                status, chunk = self._receive_data()
            except:
                import traceback
                traceback.print_exc()
                self.lockdown = LockdownClient()
                self.service = self.lockdown.start_service("com.apple.afc")
                return self.file_read(handle, sz)

            if status != afc_error_t.AFC_E_SUCCESS:
                break
            sz -= toRead
            data += chunk
        return data

    def file_write(self, handle, data, chunk_size=MAXIMUM_WRITE_SIZE):
        file_handle = struct.pack("<Q", handle)
        chunks_count = len(data) // chunk_size
        b = b''
        for i in range(chunks_count):
            chunk = data[i * chunk_size:(i + 1) * chunk_size]
            self._dispatch_packet(afc_opcode_t.AFC_OP_WRITE,
                                  file_handle + chunk,
                                  this_length=48)
            b += chunk

            status, response = self._receive_data()
            if status != afc_error_t.AFC_E_SUCCESS:
                raise IOError(f'failed to write chunk: {status}')

        if len(data) % chunk_size:
            chunk = data[chunks_count * chunk_size:]
            self._dispatch_packet(afc_opcode_t.AFC_OP_WRITE,
                                  file_handle + chunk,
                                  this_length=48)

            b += chunk

            status, response = self._receive_data()
            if status != afc_error_t.AFC_E_SUCCESS:
                raise IOError(f'failed to write last chunk: {status}')

    def get_file_contents(self, filename):
        info = self.get_file_info(filename)
        if info:
            if info['st_ifmt'] == 'S_IFLNK':
                filename = info['LinkTarget']

            if info['st_ifmt'] == 'S_IFDIR':
                self.logger.info("%s is directory...", filename)
                return

            self.logger.info("Reading: %s", filename)
            h = self.file_open(filename)
            if not h:
                return
            d = self.file_read(h, int(info["st_size"]))
            self.file_close(h)
            return d
        return

    def set_file_contents(self, filename, data):
        h = self.file_open(filename, AFC_FOPEN_WR)
        self.file_write(h, data)
        self.file_close(h)

    def dir_walk(self, dirname):
        dirs = []
        files = []
        for fd in self.read_directory(dirname):
            fd = fd.decode('utf-8')
            if fd in ('.', '..', ''):
                continue
            infos = self.get_file_info(posixpath.join(dirname, fd))
            if infos and infos.get('st_ifmt') == 'S_IFDIR':
                dirs.append(fd)
            else:
                files.append(fd)

        yield dirname, dirs, files

        if dirs:
            for d in dirs:
                for walk_result in self.dir_walk(posixpath.join(dirname, d)):
                    yield walk_result


class AFCShell(Cmd):
    def __init__(self, afcname='com.apple.afc', completekey='tab', stdin=None, stdout=None, client=None,
                 logger=None, lockdown=None, udid=None):
        Cmd.__init__(self, completekey=completekey, stdin=stdin, stdout=stdout)
        self.logger = logger or logging.getLogger(__name__)
        self.lockdown = lockdown if lockdown else LockdownClient(udid=udid)
        self.afc = client if client else AFCClient(self.lockdown, service_name=afcname)
        self.curdir = '/'
        self.prompt = 'AFC$ ' + self.curdir + ' '
        self.complete_cat = self._complete
        self.complete_ls = self._complete

    def do_exit(self, p):
        return True

    def do_quit(self, p):
        return True

    def do_pwd(self, p):
        print(self.curdir)

    def do_link(self, p):
        z = p.split()
        self.afc.make_link(AFC_SYMLINK, z[0], z[1])

    def do_cd(self, p):
        if not p.startswith("/"):
            new = posixpath.join(self.curdir, p)
        else:
            new = p

        new = os.path.normpath(new).replace("\\", "/").replace("//", "/")
        if self.afc.read_directory(new):
            self.curdir = new
            self.prompt = "AFC$ %s " % new
        else:
            self.logger.error("%s does not exist", new)

    def _complete(self, text, line, begidx, endidx):
        filename = text.split("/")[-1]
        dirname = "/".join(text.split("/")[:-1])
        return [dirname + "/" + x for x in self.afc.read_directory(self.curdir + "/" + dirname) if
                x.startswith(filename)]

    def do_ls(self, p):
        dirname = posixpath.join(self.curdir, p)
        if self.curdir.endswith("/"):
            dirname = self.curdir + p
        d = self.afc.read_directory(dirname)
        if d:
            for dd in d:
                print(dd)

    def do_cat(self, p):
        data = self.afc.get_file_contents(posixpath.join(self.curdir, p))
        if data and p.endswith(".plist"):
            pprint(parsePlist(data))
        else:
            print(data)

    def do_rm(self, p):
        f = self.afc.get_file_info(posixpath.join(self.curdir, p))
        if f['st_ifmt'] == 'S_IFDIR':
            d = self.afc.remove_directory(posixpath.join(self.curdir, p))
        else:
            d = self.afc.file_remove(posixpath.join(self.curdir, p))

    def do_pull(self, user_args):
        args = user_args.split()
        if len(args) != 2:
            local_path = "."
            remote_path = user_args
        else:
            local_path = args[1]
            remote_path = args[0]

        remote_file_info = self.afc.get_file_info(posixpath.join(self.curdir, remote_path))
        if not remote_file_info:
            logging.error("remote file does not exist")
            return

        out_path = posixpath.join(local_path, remote_path)
        if remote_file_info['st_ifmt'] == 'S_IFDIR':
            if not os.path.isdir(out_path):
                os.makedirs(out_path, MODE_MASK)

            for d in self.afc.read_directory(remote_path):
                if d == "." or d == ".." or d == "":
                    continue
                self.do_pull(remote_path + "/" + d + " " + local_path)
        else:
            contents = self.afc.get_file_contents(posixpath.join(self.curdir, remote_path))
            out_dir = os.path.dirname(out_path)
            if not os.path.exists(out_dir):
                os.makedirs(out_dir, MODE_MASK)
            with open(out_path, 'wb') as remote_file_info:
                remote_file_info.write(contents)

    def do_push(self, p):
        src_dst = p.split()
        if len(src_dst) != 2:
            self.logger.error('USAGE: push <src> <dst>')
            return
        src = src_dst[0]
        dst = src_dst[1]

        src = os.path.expanduser(src)
        dst = os.path.expanduser(dst)

        logging.info(f'from {src} to {dst}')
        if os.path.isdir(src):
            self.afc.make_directory(os.path.join(dst))
            for x in os.listdir(src):
                if x.startswith("."):
                    continue
                path = os.path.join(src, x)
                self.do_push(path + " " + dst + "/" + path)
        else:
            data = open(src, "rb").read()
            self.afc.set_file_contents(posixpath.join(self.curdir, dst), data)

    def do_head(self, p):
        print(self.afc.get_file_contents(posixpath.join(self.curdir, p))[:32])

    def do_hexdump(self, filename):
        filename = posixpath.join(self.curdir, filename)
        hexdump(self.afc.get_file_contents(filename))

    def do_mkdir(self, p):
        print(self.afc.make_directory(p))

    def do_rmdir(self, p):
        return self.afc.remove_directory(p)

    def do_info(self, p):
        for k, v in self.afc.get_device_info().items():
            print(k, '\t:\t', v)

    def do_mv(self, p):
        t = p.split()
        return self.afc.rename_path(t[0], t[1])

    def do_stat(self, filename):
        filename = posixpath.join(self.curdir, filename)
        pprint(self.afc.get_file_info(filename))
