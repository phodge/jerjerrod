import base64
import json
import os
import time
from datetime import date, datetime
from os.path import exists, join
from subprocess import check_call


HOME = os.environ['HOME']
CACHEDIR = join(HOME, '.config', 'jerjerrod', 'cache')
# re-check projects on the hour
PROJECT_EXPIRY = 60 * 60
# only check outgoing every 4 hours
OUTGOING_EXPIRY = 60 * 60 * 4

IGNORE_PATH = join(HOME, '.config', 'jerjerrod', 'ignore.json')


def _getcachepath(path):
    if ':' in path:
        return base64.b64encode(path)
    return path.replace('/', ':')


class DiskCache(object):
    def getcache(self, path, expiry):
        sanepath = join(CACHEDIR, _getcachepath(path))

        # convert path to something sane that doesn't include slashes
        if not exists(sanepath):
            return
        if (os.stat(sanepath).st_mtime + expiry) < time.time():
            os.unlink(sanepath)
            return
        with open(sanepath, 'r') as f:
            return json.loads(f.read())

    def setcache(self, path, info):
        data = json.dumps(info)
        if not exists(CACHEDIR):
            check_call(['mkdir', '-p', CACHEDIR])
        sanepath = join(CACHEDIR, _getcachepath(path))
        with open(sanepath, 'w') as f:
            f.write(data)

    def clearcache(self, path):
        sanepath = join(CACHEDIR, _getcachepath(path))
        if exists(sanepath):
            os.unlink(sanepath)

    def getignorelist(self):
        if not exists(IGNORE_PATH):
            return set()

        # is the file dated earlier than today?
        today = date.today()
        dt = datetime(today.year, today.month, today.day)
        if os.stat(IGNORE_PATH).st_mtime < dt.timestamp():
            os.unlink(IGNORE_PATH)
            return set()

        with open(IGNORE_PATH) as f:
            return set(json.load(f))

    def setignorelist(self, sequence):
        things = [str(name) for name in sequence]
        with open(IGNORE_PATH, 'w') as f:
            json.dump(things, f)
