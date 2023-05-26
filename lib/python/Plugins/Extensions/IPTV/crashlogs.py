# Embedded file name: src/crashlogs.py

try:
    from typing import List, Tuple
except ImportError:
    pass

import os
import re
from glob import glob
import requests
from Components.config import config
from .utils import trace
from .settings_model import settingsRepo

class CrashLogReporter(object):

    def __init__(self):
        self.url = 'http://technic.cf/crashlogs/'
        try:
            self.log_path = config.crash.debug_path.value
        except AttributeError as e:
            trace('error in gettings log path', e)
            self.log_path = '/home/root/logs'

        self.new_logs = []

    def findPendingLogs(self):
        self.new_logs = []
        regexp = re.compile('enigma2_crash_(\\d+).log')
        for filename in glob(os.path.join(self.log_path, 'enigma2_crash_*.log')):
            m = regexp.match(os.path.basename(filename))
            if not m:
                trace('Unknow log', filename)
                continue
            try:
                t = int(m.group(1))
            except ValueError:
                trace('Bad log filename', filename)
                continue

            if t > settingsRepo.last_crashlog:
                trace('New log file', filename)
                self.new_logs.append((t, filename))

        return len(self.new_logs) > 0

    def sendNewLogs(self):
        if not self.new_logs:
            return
        t, filename = sorted(self.new_logs)[-1]
        trace('Sending', filename)
        with open(filename, 'rb') as f:
            response = requests.post(self.url, files={'file': f})
        trace('Log sent:', response, response.content)
        response.raise_for_status()
        settingsRepo.last_crashlog = t
        settingsRepo.storeConfig()