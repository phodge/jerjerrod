from __future__ import (
    absolute_import, division, unicode_literals, print_function)
import os
import time
import subprocess

from jerjerrod.config import RCFILE
from jerjerrod.caching import DiskCache
from jerjerrod.projects import get_all_projects


# expire project list after 1 second
_SUB = None
_SUBTIME = None
_SUBEXPIRE = 60 * 60

# we want a cache for the config stuff
_CFGCACHE = {}
_CFGTIME = None


def _refresh(force):
    global _SUB, _SUBTIME
    if _SUB:
        # TODO: garbage-collect the thing if it's finished
        retval = _SUB.poll()
        if retval is not None:
            _SUB = None if retval == 0 else False
            _SUBTIME = time.time()
        return

    if _SUB is False:
        return

    # if its expired, start a new one
    if (_SUBTIME is not None
            and (time.time() - _SUBTIME) < _SUBEXPIRE
            and not force):
        return

    cmd = ['jerjerrod', 'namesbystatus', 'JERJERROD:CHANGED']
    _SUB = subprocess.Popen(cmd)


def wsscancount(pl):
    _refresh(False)

    ret = []
    if _SUB is not None:
        ret.append({
            'contents': '!!!' if _SUB is False else '***',
            'highlight_groups': ['JERJERROD:SCANNING'],
            #'divider_highlight_group': 'JERJERROD:SEPARATOR',
        })
    return ret


_CFGCHECKTIME = None
# check the config file's mtime at most once very 3 seconds
_CFGCHECKFREQ = 3


def _expirecfgcache():
    global _CFGCHECKTIME, _CFGCACHE, _CFGTIME

    if (_CFGCHECKTIME is not None
            and (time.time() - _CFGCHECKTIME) < _CFGCHECKFREQ):
        return

    # we're going to stat the RCFILE to see if it has changed
    _CFGCHECKTIME = time.time()
    mtime = os.stat(RCFILE).st_mtime

    # if the file's mtime is different to last time, we want to destroy our
    # cache
    if mtime != _CFGTIME:
        _CFGTIME = mtime
        _CFGCACHE = {}


def wsnames(pl, category):
    _expirecfgcache()
    assert category in ('JERJERROD:CHANGED', 'JERJERROD:UNTRACKED',
                        'JERJERROD:UNPUSHED', 'JERJERROD:UNKNOWN')
    names = []
    for proj in get_all_projects(DiskCache(), _CFGCACHE):
        status = proj.getstatus(False)
        if status == 'JERJERROD:UNKNOWN' and _SUB is None:
            _refresh(True)
        if status == category:
            names.append(proj.getname())

    # never show more than 5 names in the 'unknown' category
    count = len(names)
    if category == 'JERJERROD:UNKNOWN' and count > 5:
        names = names[:5]
        names.append('(+{} more)'.format(count - 5))

    ret = []
    if len(names):
        ret.append({
            'contents': ' '.join(names),
            'highlight_groups': [category],
            'divider_highlight_group': 'JERJERROD:SEPARATOR',
        })
    return ret
