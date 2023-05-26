# Embedded file name: src/kb.py
"""
Virtual Keyboard
"""

from Components.ActionMap import NumberActionMap
from Components.Input import Input
from Components.Label import Label
from Components.Language import language
from Screens.Screen import Screen
from Tools.Directories import resolveFilename, SCOPE_CURRENT_SKIN
from Tools.LoadPixmap import LoadPixmap
from enigma import gFont, getPrevAsciiCode, gRGB
from enigma import ePixmap, eWidget, eLabel, ePoint, eSize
from Components.GUIComponent import GUIComponent
from skin import parseColor
from .utils import trace
from .colors import colors
from .loc import translate as _

def loadLanguages(enabled):
    kbd_languages = {'en_EN': ([['EXIT',
                 '1',
                 '2',
                 '3',
                 '4',
                 '5',
                 '6',
                 '7',
                 '8',
                 '9',
                 '0',
                 'BACKSPACE'],
                ['q',
                 'w',
                 'e',
                 'r',
                 't',
                 'y',
                 'u',
                 'i',
                 'o',
                 'p',
                 '[',
                 ']'],
                ['a',
                 's',
                 'd',
                 'f',
                 'g',
                 'h',
                 'j',
                 'k',
                 'l',
                 ';',
                 "'",
                 'OK'],
                ['SHIFT',
                 'z',
                 'x',
                 'c',
                 'v',
                 'b',
                 'n',
                 'm',
                 ',',
                 '.',
                 '/',
                 '\\'],
                ['-',
                 '_',
                 'SPACE',
                 '@',
                 'LEFT',
                 'RIGHT']], [['EXIT',
                 '!',
                 '@',
                 '#',
                 '$',
                 '%',
                 '^',
                 '&',
                 '*',
                 '(',
                 ')',
                 'BACKSPACE'],
                ['Q',
                 'W',
                 'E',
                 'R',
                 'T',
                 'Y',
                 'U',
                 'I',
                 'O',
                 'P',
                 '{',
                 '}'],
                ['A',
                 'S',
                 'D',
                 'F',
                 'G',
                 'H',
                 'J',
                 'K',
                 'L',
                 ':',
                 '"',
                 'OK'],
                ['SHIFT',
                 'Z',
                 'X',
                 'C',
                 'V',
                 'B',
                 'N',
                 'M',
                 '<',
                 '>',
                 '?',
                 '|'],
                ['+',
                 '=',
                 'SPACE',
                 '@',
                 'LEFT',
                 'RIGHT']]),
     'ru_RU': ([['EXIT',
                 '1',
                 '2',
                 '3',
                 '4',
                 '5',
                 '6',
                 '7',
                 '8',
                 '9',
                 '0',
                 'BACKSPACE'],
                ['\u0439',
                 '\u0446',
                 '\u0443',
                 '\u043a',
                 '\u0435',
                 '\u043d',
                 '\u0433',
                 '\u0448',
                 '\u0449',
                 '\u0437',
                 '\u0445',
                 '\u044a'],
                ['\u0444',
                 '\u044b',
                 '\u0432',
                 '\u0430',
                 '\u043f',
                 '\u0440',
                 '\u043e',
                 '\u043b',
                 '\u0434',
                 '\u0436',
                 '\u044d',
                 'OK'],
                ['SHIFT',
                 '\u044f',
                 '\u0447',
                 '\u0441',
                 '\u043c',
                 '\u0438',
                 '\u0442',
                 '\u044c',
                 '\u0431',
                 '\u044e',
                 '.',
                 '/'],
                ['-',
                 '_',
                 'SPACE',
                 '@',
                 'LEFT',
                 'RIGHT']], [['EXIT',
                 '!',
                 '"',
                 '\u2116',
                 ';',
                 '%',
                 ':',
                 '?',
                 '*',
                 '(',
                 ')',
                 'BACKSPACE'],
                ['\u0419',
                 '\u0426',
                 '\u0423',
                 '\u041a',
                 '\u0415',
                 '\u041d',
                 '\u0413',
                 '\u0428',
                 '\u0429',
                 '\u0417',
                 '\u0425',
                 '\u042a'],
                ['\u0424',
                 '\u042b',
                 '\u0412',
                 '\u0410',
                 '\u041f',
                 '\u0420',
                 '\u041e',
                 '\u041b',
                 '\u0414',
                 '\u0416',
                 '\u042d',
                 'OK'],
                ['SHIFT',
                 '\u042f',
                 '\u0427',
                 '\u0421',
                 '\u041c',
                 '\u0418',
                 '\u0422',
                 '\u042c',
                 '\u0411',
                 '\u042e',
                 ',',
                 '\\'],
                ['+',
                 '=',
                 'SPACE',
                 '@',
                 'LEFT',
                 'RIGHT']])}
    result = []
    for lang in enabled or list(kbd_languages.keys()):
        try:
            result.append((lang, kbd_languages[lang]))
        except KeyError:
            trace('Unknown language', lang)
            continue

    return result


class KeyboardButton(object):

    def __init__(self, parent, png_bg, png_frame, text):
        self.instance = eWidget(parent)
        self.active = None
        self.col = parseColor('#00c1c4d8')
        self.col_bg = parseColor('#0035374c')
        self.col_bgsel = parseColor('#aa544f56')
        self.png_frame = png_frame
        self.frame = None
        size = png_bg.size()
        self.instance.resize(size)
        self.instance.setTransparent(1)
        icon = ePixmap(self.instance)
        icon.setPixmap(png_bg)
        icon.setAlphatest(2)
        icon.setScale(0)
        icon.resize(size)
        self.icon = icon
        txt = eLabel(self.instance)
        txt.setForegroundColor(self.col)
        txt.setBackgroundColor(self.col_bg)
        txt.setVAlign(txt.alignCenter)
        txt.setHAlign(txt.alignCenter)
        txt.setText(text.encode('utf-8'))
        txt.resize(eSize(png_bg.size().width() - 4, png_bg.size().height() - 4))
        self.txt = txt
        self.setActive(False)
        return

    def setActive(self, active):
        if self.active == active:
            return
        self.active = active
        if active:
            self.txt.setFont(gFont('TVSansSemi', 25))
            self.txt.setBackgroundColor(self.col_bgsel)
            self.txt.setForegroundColor(gRGB(colors['white']))
            self.txt.setTransparent(1)
            self.frame = ePixmap(self.instance)
            self.frame.setAlphatest(2)
            self.frame.setPixmap(self.png_frame)
            self.frame.resize(self.png_frame.size())
            self.frame.setBackgroundColor(self.col_bgsel)
            self.frame.setTransparent(1)
        else:
            self.txt.setFont(gFont('TVSansSemi', 25))
            self.txt.setBackgroundColor(self.col_bg)
            self.txt.setForegroundColor(self.col)
            self.txt.setTransparent(1)
            del self.frame


class Keyboard(GUIComponent):
    GUI_WIDGET = eWidget

    def __init__(self):
        GUIComponent.__init__(self)
        self.key_bg = LoadPixmap(path=resolveFilename(SCOPE_CURRENT_SKIN, 'IPTV/kb/button.png'))
        self.key_sel = LoadPixmap(path=resolveFilename(SCOPE_CURRENT_SKIN, 'IPTV/kb/frame.png'))
        self.key_images = {}
        for key in ['BACKSPACE',
         'EXIT',
         'OK',
         'SHIFT',
         'SPACE',
         'LEFT',
         'RIGHT']:
            self.key_images[key] = LoadPixmap(resolveFilename(SCOPE_CURRENT_SKIN, 'IPTV/kb/%s.png' % key.lower()))

        frames = {'BACKSPACE': 'big',
         'OK': 'big',
         'SPACE': 'space'}
        self.key_frames = {}
        for key, val in list(frames.items()):
            self.key_frames[key] = LoadPixmap(resolveFilename(SCOPE_CURRENT_SKIN, 'IPTV/kb/%s_frame.png' % val))

        self.key_widths = {'SPACE': 7}
        self.keys_list = []
        self.keyboard = []
        self.row = 0
        self.column = 0

    def setKeys(self, keys_list):
        self.keys_list = keys_list
        if self.instance:
            self.postWidgetCreate(self.instance)

    def postWidgetCreate(self, instance):
        self.keyboard = []
        y = 0
        h = self.key_bg.size().height()
        for keys in self.keys_list:
            x = 0
            row = []
            for key in keys:
                png_bg = self.key_images.get(key, self.key_bg)
                png_frame = self.key_frames.get(key, self.key_sel)
                button = KeyboardButton(self.instance, png_bg, png_frame, len(key) == 1 and key or '')
                button.instance.move(ePoint(x, y))
                row.append(button)
                x += png_bg.size().width()

            self.keyboard.append(row)
            y += h

        self.row = 0
        self.column = 0
        if self.keyboard:
            self.setActive(True)

    def preWidgetRemove(self, instance):
        self.keyboard = []

    def getSelected(self):
        return self.keys_list[self.row][self.column]

    def setActive(self, active):
        self.keyboard[self.row][self.column].setActive(active)

    def right(self):
        self.setActive(False)
        self.column = (self.column + 1) % len(self.keyboard[self.row])
        self.setActive(True)

    def left(self):
        self.setActive(False)
        self.column = (self.column - 1) % len(self.keys_list[self.row])
        self.setActive(True)

    def up(self):
        self.setActive(False)
        x1 = 0
        for key in self.keys_list[self.row][:self.column]:
            x1 += self.key_widths.get(key, 1)

        x1 += self.key_widths.get(self.keys_list[self.row][self.column], 1) / 2
        self.row = (self.row - 1) % len(self.keys_list)
        x2 = 0
        for self.column, key in enumerate(self.keys_list[self.row]):
            x2 += self.key_widths.get(key, 1)
            if x2 > x1:
                break

        self.setActive(True)

    def down(self):
        self.setActive(False)
        x1 = 0
        for key in self.keys_list[self.row][:self.column]:
            x1 += self.key_widths.get(key, 1)

        x1 += self.key_widths.get(self.keys_list[self.row][self.column], 1) / 2
        self.row = (self.row + 1) % len(self.keys_list)
        x2 = 0
        for self.column, key in enumerate(self.keys_list[self.row]):
            x2 += self.key_widths.get(key, 1)
            if x2 > x1:
                break

        self.setActive(True)

    def goToKey(self, key):
        for row, keys in enumerate(self.keys_list):
            for column, k in enumerate(keys):
                if k == key:
                    self.setActive(False)
                    self.row = row
                    self.column = column
                    self.setActive(True)
                    break


class VirtualKB(Screen):

    def __init__(self, session, languages, title = '', text = ''):
        Screen.__init__(self, session)
        self.setTitle(title)
        self.keys_list = []
        self.shiftkeys_list = []
        lang = language.getLanguage()
        self.lang_list = loadLanguages(languages)
        self.lang_idx = 0
        try:
            self.lang_idx = [ l[0] for l in self.lang_list ].index(lang)
        except ValueError:
            self.lang_idx = 0

        self.shiftMode = False
        self['list'] = self.kb = Keyboard()
        self['header'] = Label(title)
        self['red'] = Label(_('Cancel'))
        self['green'] = Label(_('OK'))
        self['country'] = Label()
        self['blue'] = Label(_('CapsLock'))
        self['text'] = Input(text)
        self['actions'] = NumberActionMap(['OkCancelActions',
         'WizardActions',
         'ColorActions',
         'KeyboardInputActions',
         'InputBoxActions',
         'InputAsciiActions'], {'gotAsciiCode': self.keyGotAscii,
         'ok': self.okClicked,
         'cancel': self.exit,
         'left': self.kb.left,
         'right': self.kb.right,
         'up': self.kb.up,
         'down': self.kb.down,
         'red': self.exit,
         'green': self.ok,
         'yellow': self.switchLang,
         'blue': self.shiftClicked,
         'deleteBackward': self.backClicked,
         'deleteForward': self.forwardClicked,
         'back': self.exit,
         'pageUp': self.cursorRight,
         'pageDown': self.cursorLeft,
         '1': self.keyNumberGlobal,
         '2': self.keyNumberGlobal,
         '3': self.keyNumberGlobal,
         '4': self.keyNumberGlobal,
         '5': self.keyNumberGlobal,
         '6': self.keyNumberGlobal,
         '7': self.keyNumberGlobal,
         '8': self.keyNumberGlobal,
         '9': self.keyNumberGlobal,
         '0': self.keyNumberGlobal}, -2)
        self.setLang()
        self.onExecBegin.append(self.setKeyboardModeAscii)
        self.onLayoutFinish.append(self.buildKeyboard)

    def setLang(self):
        lang = self.lang_list[self.lang_idx]
        self['country'].setText(_('Language') + ' (%s)' % lang[0])
        self.keys_list, self.shiftkeys_list = lang[1]

    def buildKeyboard(self):
        if self.shiftMode:
            self.kb.setKeys(self.shiftkeys_list)
        else:
            self.kb.setKeys(self.keys_list)

    def switchLang(self):
        if len(self.lang_list) <= 1:
            return
        self.lang_idx = (self.lang_idx + 1) % len(self.lang_list)
        self.setLang()
        self.buildKeyboard()

    def backClicked(self):
        self['text'].deleteBackward()

    def forwardClicked(self):
        try:
            self['text'].deleteForward()
        except AttributeError as e:
            trace('Error', e)

    def shiftClicked(self):
        self.smsChar = None
        self.shiftMode = not self.shiftMode
        self.buildKeyboard()
        self.kb.goToKey('SHIFT')
        return

    def okClicked(self):
        text = self.kb.getSelected()
        if text == 'EXIT':
            self.close(None)
        elif text == 'BACKSPACE':
            self['text'].deleteBackward()
        elif text == 'ALL':
            self['text'].markAll()
        elif text == 'CLEAR':
            self['text'].deleteAllChars()
        elif text == 'SHIFT':
            self.shiftClicked()
        elif text == 'SPACE':
            self.addChar(' ')
        elif text == 'OK':
            self.ok()
        elif text == 'LEFT':
            self['text'].left()
        elif text == 'RIGHT':
            self['text'].right()
        else:
            self.addChar(text)
        return

    def ok(self):
        self.close(self['text'].getText())

    def exit(self):
        self.close(None)
        return

    def cursorRight(self):
        self['text'].right()

    def cursorLeft(self):
        self['text'].left()

    def keyNumberGlobal(self, number):
        key = chr(48 + number)
        self.kb.goToKey(key)
        self.addChar(key)

    def keyGotAscii(self):
        key = str(chr(getPrevAsciiCode()).encode('utf-8'))
        self.kb.goToKey(key)
        self.addChar(key)

    def addChar(self, char):
        self['text'].handleAscii(ord(char))