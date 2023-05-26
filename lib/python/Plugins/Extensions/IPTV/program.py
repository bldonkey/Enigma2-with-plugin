# Embedded file name: src/program.py

try:
    from typing import List
except ImportError:
    pass

from datetime import datetime
from .utils import tdSec, tdmSec

class EpgCache(object):

    def __init__(self, programs):
        self.cache = programs
        self.pos = 0

    def find(self, time):
        if self._now(self.pos, time):
            return self.curnxt()
        self.pos += 1
        if self._now(self.pos, time):
            return self.curnxt()
        self.pos = self.bisect(time)
        if self._now(self.pos, time):
            return self.curnxt()
        else:
            return (None, None)

    def isActive(self, time):
        """
        Check if the update is needed. We want to have live program and two following programs.
        """
        t = self.expireTime()
        return t is not None and t >= time

    def expireTime(self):
        """
        Return time when cache should be updated
        :rtype: datetime | None
        """
        if self.cache:
            index = max(0, len(self.cache) - 3)
            return self.cache[index].end
        else:
            return None
            return None

    def findCurrent(self, time):
        return self.find(time)[0]

    def findCurrentFollowing(self, time):
        self.find(time)
        if self._now(self.pos, time):
            return self.cache[self.pos:self.pos + 3]
        return []

    def bisect(self, x):
        lo = 0
        hi = len(self.cache)
        while lo < hi:
            mid = (lo + hi) // 2
            if x < self.cache[mid].end:
                hi = mid
            else:
                lo = mid + 1

        return lo

    def _now(self, i, time):
        return i < len(self.cache) and self.cache[i].isAt(time)

    def curnxt(self):
        i = self.pos
        current_program = self.cache[i]
        next_program = i + 1 < len(self.cache) and self.cache[i + 1] or None
        return (current_program, next_program)


class Program(object):

    def __init__(self, begin, end, title, description, has_archive):
        self.begin = begin
        self.end = end
        self.title = title
        self.description = description
        self.has_archive = has_archive

    @staticmethod
    def fromData(d):
        return Program(datetime.fromtimestamp(d['begin']), datetime.fromtimestamp(d['end']), d['title'].encode('utf-8'), d['info'].encode('utf-8'), d.get('has_archive', False))

    @classmethod
    def fromJson(cls, value):
        return cls.fromData(value)

    def toJson(self):
        return {'begin': int(self.begin.strftime('%s')),
         'end': int(self.end.strftime('%s')),
         'title': self.title,
         'info': self.description,
         'has_archive': self.has_archive}

    def duration(self):
        return tdSec(self.end - self.begin)

    def timePass(self, t):
        return tdSec(t - self.begin)

    def timeLeft(self, t):
        return tdSec(self.end - t)

    def timeLeftm(self, t):
        return tdmSec(self.end - t)

    def percent(self, t, size):
        return size * self.timePass(t) / self.duration()

    def isAt(self, t):
        return self.begin <= t < self.end

    def __repr__(self):
        return self.begin.strftime('%H:%M') + '-' + self.end.strftime('%H:%M') + '|' + self.title