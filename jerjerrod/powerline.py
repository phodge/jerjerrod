from __future__ import (
    absolute_import, division, unicode_literals, print_function)
import time
import subprocess

from jerjerrod.caching import DiskCache
from jerjerrod.projects import get_all_projects


# expire project list after 1 second
_SUB = None
_SUBTIME = None
_SUBEXPIRE = 60 * 60


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

    _SUB = subprocess.Popen(['jerjerrod', 'namesbystatus', 'JERJERROD:CHANGED'])


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


def wsnames(pl, category):
    assert category in ('JERJERROD:CHANGED', 'JERJERROD:UNTRACKED',
                        'JERJERROD:UNPUSHED', 'JERJERROD:UNKNOWN')
    names = []
    for proj in get_all_projects(DiskCache()):
        status = proj.getstatus(False)
        if status == 'JERJERROD:UNKNOWN' and _SUB is None:
            _refresh(True)
        if status == category:
            names.append(proj.getname())

    ret = []
    if len(names):
        ret.append({
            'contents': ' '.join(names),
            'highlight_groups': [category],
            'divider_highlight_group': 'JERJERROD:SEPARATOR',
        })
    return ret
