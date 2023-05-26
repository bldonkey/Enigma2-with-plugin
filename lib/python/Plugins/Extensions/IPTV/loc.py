# Embedded file name: src/loc.py
"""
Localization
"""
from Components.Language import language
from Tools.Directories import resolveFilename, SCOPE_PLUGINS
import os
import gettext

def localeInit():
    lang = language.getLanguage()[:2]
    os.environ['LANGUAGE'] = lang
    gettext.bindtextdomain('IPTV', resolveFilename(SCOPE_PLUGINS, 'Extensions/IPTV/locale'))


def translate(txt):
    t = gettext.dgettext('IPTV', txt)
    if t == txt:
        t = gettext.gettext(txt)
    return t


def ngettext(singluar, plural, n):
    return gettext.dngettext('IPTV', singluar, plural, n)


localeInit()
language.addCallback(localeInit)