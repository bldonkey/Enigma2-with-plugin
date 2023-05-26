# Embedded file name: src/utils.py

from datetime import timedelta, datetime

def trace(*args):
    print('[IPTV]', *args)


def getMAC(ifname = 'eth0'):
    import socket
    import fcntl
    import struct
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        info = fcntl.ioctl(s.fileno(), 35111, struct.pack('256s', ifname[:15]))
    except IOError:
        return '00:00:00:00:00:00'

    return ':'.join([ '%02x' % ord(char) for char in info[18:24] ]).upper()


def getBoxModel():
    try:
        from boxbranding import getBoxType
        return getBoxType()
    except ImportError:
        trace('boxbranding module not found')

    for info_file in ('hwmodel', 'gbmodel', 'boxtype', 'vumodel', 'azmodel', 'model'):
        try:
            with open('/proc/stb/info/%s' % info_file) as f:
                return f.read().strip()
        except IOError:
            continue

    return 'unknown'


def getBoxSerial():
    try:
        with open('/proc/stb/info/sn') as f:
            return f.read().strip()
    except IOError:
        return 'unavailable'


def getImageInfo():
    try:
        from boxbranding import getImageDistro, getImageVersion
        return '%s_%s' % (getImageDistro(), getImageVersion())
    except ImportError:
        return 'unknown'


def tdSec(td):
    return td.days * 86400 + td.seconds


def secTd(sec):
    return timedelta(sec / 86400, sec % 86400)


def tdmSec(td):
    return int(tdSec(td) * 1000) + 1


def toDate(time):
    return datetime(time.year, time.month, time.day)


def formatLength(sec):
    return '%d:%02d:%02d' % (sec / 3600, sec / 60 % 60, sec % 60)


class SimpleTime(object):
    """primitive time measure for profiling purposes"""

    def __init__(self, name):
        self.name = name
        self.t = datetime.now()

    def finish(self):
        diff = datetime.now() - self.t
        print('[IPTV] TIME(%s): %s' % (self.name, diff.total_seconds()))
        del self.name