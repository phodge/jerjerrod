import base64
import simplejson
import os
import time
from subprocess import check_call
from os.path import join


HOME = os.environ['HOME']
CACHEDIR = join(HOME, '.config', 'jerjerrod', 'cache')
# re-check projects on the hour
PROJECT_EXPIRY = 60 * 60
# only check outgoing every 4 hours
OUTGOING_EXPIRY = 60 * 60 * 4


def _getcachepath(path):
    if ':' in path:
        return base64.b64encode(path)
    return path.replace('/', ':')


class DiskCache(object):
    def getcache(self, path, expiry):
        sanepath = join(CACHEDIR, _getcachepath(path))

        # convert path to something sane that doesn't include slashes
        if not os.path.exists(sanepath):
            return
        if (os.stat(sanepath).st_mtime + expiry) < time.time():
            os.unlink(sanepath)
            return
        with open(sanepath, 'r') as f:
            return simplejson.loads(f.read())

    def setcache(self, path, info):
        data = simplejson.dumps(info)
        if not os.path.exists(CACHEDIR):
            check_call(['mkdir', '-p', CACHEDIR])
        sanepath = join(CACHEDIR, _getcachepath(path))
        with open(sanepath, 'w') as f:
            f.write(data)

    def clearcache(self, path):
        sanepath = join(CACHEDIR, _getcachepath(path))
        if os.path.exists(sanepath):
            os.unlink(sanepath)
