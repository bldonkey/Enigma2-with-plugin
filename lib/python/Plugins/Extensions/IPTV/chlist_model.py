# Embedded file name: src/chlist_model.py

try:
    from typing import List, Optional, Tuple
except ImportError:
    pass

from .api import Api, Group, Channel
from .settings_model import PlayState
from .utils import trace

class EmptyListError(Exception):
    pass


class ChannelsModel(object):

    def __init__(self, db, groups = None, lang = 'ALL'):
        super(ChannelsModel, self).__init__()
        self.db = db
        self._lang = lang
        if groups:
            self._full_groups = groups
        else:
            self._full_groups = []
        self._groups = self._full_groups

    def load(self):
        return self.db.getChannels().addCallback(self._setGroups)

    def _setGroups(self, groups):
        self._full_groups = groups

    def filterByLanguage(self, lang):
        if lang == 'ALL':
            self._lang = lang
            self._groups = self._full_groups
            return self.getGroups()
        groups = [ Group(g.id, g.title, g.alias, self._sort(g.channels, lang)) for g in self._full_groups ]
        if len(groups[1].channels) == 0:
            raise EmptyListError()
        self._lang = lang
        self._groups = groups
        return self.getGroups()

    def getGroups(self):
        return self._groups

    def getLanguage(self):
        return self._lang

    def _sort(self, channels, lang):
        """Move channels that have language on top"""
        priority = []
        other = []
        for c in channels:
            if lang in c.audio:
                priority.append(c)
            else:
                other.append(c)

        return priority + other

    def findPath(self, st):
        trace('findPath', st)
        for g_idx, g in enumerate(self._groups):
            if g.id == st.gid:
                break
        else:
            g_idx = 1
            g = self._groups[g_idx]

        for c_idx, c in enumerate(g.channels):
            if c.id == st.cid:
                return (g_idx, c_idx)

        return None