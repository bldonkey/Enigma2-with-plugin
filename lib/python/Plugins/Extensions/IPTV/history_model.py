# Embedded file name: src/history_model.py

try:
    from typing import List, Optional, Tuple
except ImportError:
    pass

from datetime import datetime
from .program import Program
from .schema import Field, ListField, ObjectData, tdatetime, tint, toptional, ttuple

class HistoryEntry(ObjectData):
    path = ttuple((tint(), tint()))
    cid = tint()
    time = toptional(tdatetime())
    epg = toptional(Program)

    def __init__(self, path = None, cid = 0, time = None, epg = None):
        """
        :param (int, int)|None path: group index, channel index
        :param int cid: channel id
        :param datetime|None time: saved time for archive or None for live
        :param Program|None epg: saved epg for archive
        """
        self.path = path
        self.cid = cid
        self.time = time
        self.epg = epg

    def copy(self):
        return HistoryEntry(self.path, self.cid, self.time, self.epg)

    def equals(self, other):
        return self.cid == other.cid and self.time == other.time

    def __repr__(self):
        return 'History(%s, %s, %s)' % (self.path, self.cid, self.time)


class HistoryModel(Field):
    _List = ListField(HistoryEntry)

    def __init__(self, history):
        self._history = history

    @classmethod
    def fromJson(cls, value):
        return cls(cls._List.fromJson(value))

    @classmethod
    def toJson(cls, value):
        return cls._List.toJson(value._history)

    @classmethod
    def default(cls):
        return cls([])

    def append(self, entry):
        for i, h in enumerate(self._history):
            if h.equals(entry):
                del self._history[i]
                break

        self._history.append(entry)
        if len(self._history) > 10:
            del self._history[0]

    def removeInvalid(self, validChannels):
        self._history = [ entry for entry in self._history if entry.cid in validChannels ]

    def getList(self):
        return self._history

    def clear(self):
        self._history = []