import os.path
import glob
from os.path import join

_WORKSPACES = None
_SINGLES = None


HOME = os.environ['HOME']
RCFILE = join(HOME, '.config', 'jerjerrod', 'jerjerrod.conf')


def _readcfg():
    global _WORKSPACES, _SINGLES
    if _WORKSPACES is not None:
        return

    _WORKSPACES = []
    _SINGLES = []

    if not os.path.exists(RCFILE):
        return

    with open(RCFILE, 'r') as f:
        number = 0
        for line in f:
            number += 1
            stripped = line.strip()
            if len(stripped):
                _readcfgline(number, stripped)


def _readcfgline(number, line):
    global _WORKSPACES, _SINGLES
    keyword, path, *flags = line.split(' ')
    path = os.path.expandvars(path)
    path = os.path.expanduser(path)
    for flag in flags:
        if flag.startswith('IGNORE='):
            continue
        raise Exception("Invalid CFG flag on line %d: %r" % (number, flag))
    if keyword == 'WORKSPACE':
        for match in glob.glob(path):
            _WORKSPACES.append((os.path.basename(match), match, flags))
        return
    if keyword == 'PROJECT':
        for match in glob.glob(path):
            _SINGLES.append((os.path.basename(match), match, flags))
        return
    raise Exception("Invalid CFG line %d: %s" % (number, line))


def get_workspaces():
    _readcfg()
    return _WORKSPACES


def get_singles():
    _readcfg()
    return _SINGLES
