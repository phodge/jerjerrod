import os.path
import glob
from os.path import join

HOME = os.environ['HOME']
RCFILE = join(HOME, '.config', 'jerjerrod', 'jerjerrod.conf')


def _populateconfig(cache):
    if 'WORKSPACES' in cache:
        return

    cache['WORKSPACES'] = {}
    cache['SINGLES'] = []

    if not os.path.exists(RCFILE):
        return

    with open(RCFILE, 'r') as f:
        number = 0
        for line in f:
            number += 1
            stripped = line.strip()
            if len(stripped):
                _readcfgline(number, stripped, cache)


def _readcfgline(number, line, cache):
    if line.startswith('#'):
        return
    keyword, path, *flags = line.split(' ')
    path = os.path.expandvars(path)
    path = os.path.expanduser(path)
    for flag in flags:
        if flag.startswith('IGNORE='):
            continue
        raise Exception("Invalid CFG flag on line %d: %r" % (number, flag))
    if keyword == 'WORKSPACE':
        for match in glob.glob(path):
            name = os.path.basename(match)
            cache['WORKSPACES'][name] = (match, flags)
        return
    if keyword == 'PROJECT':
        for match in glob.glob(path):
            cache['SINGLES'].append((os.path.basename(match), match, flags))
        return
    if keyword == 'FORGET':
        for thing in list(cache['SINGLES']):
            if thing[1] == path:
                cache['SINGLES'].remove(thing)
                break
        return
    raise Exception("Invalid CFG line %d: %s" % (number, line))


def get_workspaces(cache):
    _populateconfig(cache)
    for name, (path, flags) in cache['WORKSPACES'].items():
        yield name, path, flags


def get_singles(cache):
    _populateconfig(cache)
    return cache['SINGLES']
