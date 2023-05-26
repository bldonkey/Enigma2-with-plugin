# Embedded file name: src/videos_model.py

try:
    from typing import List
except ImportError:
    pass

from .loc import translate as _

class Caption(object):

    def __init__(self, title):
        self._lang = 'ALL'
        self._parts = [title, _('Videos')]

    def setLang(self, lang):
        self._lang = lang
        if lang:
            self._parts[1] = '%s (%s)' % (_('Videos'), lang)
        else:
            self._parts[1] = _('Videos')

    def append(self, element):
        return self._parts.append(element)

    def pop(self):
        return self._parts.pop()

    def __str__(self):
        return ' / '.join(self._parts)

    def __add__(self, items):
        result = Caption('')
        result._lang = self._lang
        result._parts = self._parts + items
        return result