# Embedded file name: src/tvinfo.py

try:
    from typing import Any
except ImportError:
    pass

from Components.ActionMap import ActionMap
from Components.Label import Label
from Screens.Screen import Screen
from .program import Program
from .loc import translate as _

class TVProgramInfo(Screen):

    def __init__(self, session, program):
        super(TVProgramInfo, self).__init__(session)
        self['caption'] = Label(_('Now'))
        self['time'] = Label(program.begin.strftime('%d/%m/%Y %H:%M'))
        self['title'] = Label(program.title)
        self['description'] = Label(program.description)
        self['actions'] = ActionMap(['OkCancelActions', 'TInfoActions'], {'ok': self.close,
         'cancel': self.close,
         'info': self.close})