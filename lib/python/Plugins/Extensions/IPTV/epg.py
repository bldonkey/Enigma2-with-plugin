# Embedded file name: src/epg.py

from datetime import datetime, timedelta
from .api import Api
from .base import trapException
from .layer import eTimer
from .updater import fatalError
from .utils import trace
from .program import EpgCache, Program
from .common import CallbackReceiver, safecb
try:
    from typing import Dict, List, Callable, Optional
except ImportError:
    pass

class LiveEpgCache(CallbackReceiver):
    """
    Provides live program information for all channels
    """

    def __init__(self, db):
        super(LiveEpgCache, self).__init__()
        self.db = db
        self.onUpdate = []
        self._cache = {}
        self._timer = eTimer()
        self._timer.callback.append(self.startUpdate)

    def startUpdate(self):
        self.resumeCallbacks()
        t = datetime.now()
        self.trace('startUpdate at', t)
        if self._cache:
            to_update = [ cid for cid, cache in list(self._cache.items()) if not cache.isActive(t) ]
        else:
            to_update = list(self.db.channels.keys())
        self.db.getEpgChannels(to_update, t).addCallback(self._applyUpdate).addErrback(self._error).addErrback(fatalError)

    @safecb
    def _applyUpdate(self, values):
        new_values = {cid:EpgCache(programs) for cid, programs in list(values.items())}
        self._cache.update(new_values)
        times = [ ps.expireTime() for ps in list(self._cache.values()) if ps.cache ]
        if times:
            next_update = min(times)
        else:
            next_update = datetime.now() + timedelta(minutes=15)
        diff = int((next_update + timedelta(seconds=1) - datetime.now()).total_seconds() * 1000)
        self._timer.start(max(60000, min(3600000, diff)), True)
        for f in self.onUpdate:
            f(list(new_values.keys()))

    def getCurrent(self, cid, time):
        try:
            return self._cache[cid].findCurrent(time)
        except KeyError:
            return None

        return None

    def getCurrentFollowing(self, cid, time):
        try:
            return self._cache[cid].findCurrentFollowing(time)
        except KeyError:
            return []

    def stop(self):
        self._timer.callback.remove(self.startUpdate)
        self._timer.stop()
        self.stopCallbacks()

    def suspend(self):
        self._timer.stop()
        self.stopCallbacks()

    @safecb
    def _error(self, err):
        e = trapException(err)
        self.trace('error', e)

    @staticmethod
    def trace(*args):
        trace('EpgCache:', ' '.join(map(str, args)))