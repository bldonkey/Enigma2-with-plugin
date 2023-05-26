# Embedded file name: src/layer.py
""" Abstraction layer for DMM and open enigma2 """

from enigma import eTimer as eTimerEnigma
if hasattr(eTimerEnigma, 'callback'):
    print('[IPTV] enigma2 SigC')
    enigma2Qt = False
    eTimer = eTimerEnigma
else:
    print('[IPTV] enigma2 Qt')
    enigma2Qt = True

    class eTimer(eTimerEnigma):

        def __init__(self):
            eTimerEnigma.__init__(self)
            self.callback = []
            self.conn = self.timeout.connect(self.fire)

        def fire(self):
            for f in self.callback:
                f()


try:
    from enigma import BT_SCALE as SCALE
except ImportError as e:
    print('[IPTV]', e)
    try:
        from enigma import SCALE_ASPECT as SCALE
    except ImportError as e:
        print('[IPTV]', e)
        SCALE = 0