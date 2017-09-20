from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import os
import re
from contextlib import contextmanager
from os.path import join
from subprocess import STDOUT, CalledProcessError, TimeoutExpired, check_output

import git

from jerjerrod.caching import OUTGOING_EXPIRY, PROJECT_EXPIRY
from jerjerrod.config import get_singles, get_workspaces

HOME = os.environ['HOME']
# allow up to 10 seconds to contact a remote HG server
HG_REMOTE_TIMEOUT = 10


@contextmanager
def gc_(*things):
    """Context manager that calls .__del__() on all arguments when it finishes"""
    yield things
    for thing in things:
        thing.__del__()


def cmd2lines(*args, **kwargs):
    output = check_output(*args, **kwargs)
    for line in output.decode('utf-8').split('\n'):
        line = line.rstrip()
        if len(line):
            yield line


class Inspector(object):
    outgoingexpensive = True

    def __init__(self, path):
        self._path = path


class GitInspector(Inspector):
    _statuslines = None
    outgoingexpensive = False

    def getbranch(self):
        with gc_(git.Repo(self._path)) as (repo,):
            try:
                return repo.active_branch.name
            except TypeError:
                # might be a detached head
                return None

    def statuslines(self):
        changedregex = re.compile(r'^(?!  )[RMADU ]{2} ')
        if self._statuslines is None:
            changed = []
            untracked = []
            lines = cmd2lines(['git', 'status', '--short'], cwd=self._path)
            for line in lines:
                if changedregex.match(line[:3]):
                    changed.append(line[3:])
                elif line[:3] in (' ? ', '?? '):
                    untracked.append(line[3:])
                else:
                    raise Exception("Unexpected: %r" % line)
            self._statuslines = (changed, untracked)
        return self._statuslines

    def getchanged(self):
        return self.statuslines()[0]

    def getuntracked(self):
        with gc_(git.Repo(self._path)) as (repo,):
            return repo.untracked_files

    def getoutgoing(self):
        outgoing = []

        print(self._path)
        with gc_(git.Repo(self._path)) as (repo,):
            localonly = {}
            for head in repo.branches:
                # ignore our git-wip backups
                if '.WIP.BACKUP-' in head.name:
                    continue

                # does the local branch have an upstream? Are there any outgoing changes?
                upstream = head.tracking_branch()

                if not (upstream and upstream.is_valid()):
                    localonly[head.commit.binsha] = head
                    continue

                if head.commit == upstream.commit:
                    continue
                if not repo.is_ancestor(head.commit, upstream.commit):
                    outgoing.append(head)

            # NOTE: the repo object can check if one commit is ancestor of another using is_ancestor()
            # put all the remote refs in a dict so we can look for local commits that aren't part of any of them
            remote_refs = set()

            for remote in repo.remotes:
                # now go through remote refs and see if our locals have been merged into any of them yet?
                for ref in remote.refs:
                    # forget about the local head that pointed at this commit - we know it exists on the remote already
                    localonly.pop(ref.commit.binsha, None)
                    remote_refs.add(ref)

            for head in localonly.values():
                pushed = False
                for ref in remote_refs:
                    if repo.is_ancestor(head, ref):
                        pushed = True
                        break
                if not pushed:
                    outgoing.append(head)

        return len(outgoing)

    def getstashcount(self):
        cmd = ['git', 'stash', 'list']
        return len(list(cmd2lines(cmd, cwd=self._path)))


class HgInspector(Inspector):
    _statuslines = None

    def getbranch(self):
        output = check_output(['hg', 'branch'], cwd=self._path).strip()
        assert len(output)
        return output

    def statuslines(self):
        changedregex = re.compile(r'^[MADR!] ')
        if self._statuslines is None:
            changed = []
            untracked = []
            lines = cmd2lines(['hg', 'status'], cwd=self._path)
            for line in lines:
                if changedregex.match(line):
                    changed.append(line[2:])
                elif line[:2] == '? ':
                    untracked.append(line[2:])
                else:
                    raise Exception("Unexpected: %s" % line)
            self._statuslines = (changed, untracked)
        return self._statuslines

    def getchanged(self):
        return self.statuslines()[0]

    def getuntracked(self):
        return self.statuslines()[1]

    def getoutgoing(self):
        """
        Returns one of:
        - An integer showing how many changes are outgoing (possibly 0)
        - A string describing how many unchanges are outgoing
        - "-" if the remote host couldn't be contacted
        FIXME: would be nice to show something like '3+' if we can't contact
        the remote server, but know there are 3 draft commits
        """
        try:
            cmd = ['hg', 'outgoing']
            check_output(cmd, stderr=STDOUT, cwd=self._path,
                         timeout=HG_REMOTE_TIMEOUT)
        except TimeoutExpired:
            return '?'
        except CalledProcessError as err:
            if err.output.endswith(
                    b'abort: error: nodename nor servname provided'
                    b', or not known\n'):
                return '-'
            if err.output.endswith(
                    b'abort: no suitable response from remote hg!\n'):
                return '-'
            if err.output.endswith(b'no changes found\n'):
                return 0
            print(err.output)
            raise

        return '1+'

    def getstashcount(self):
        lines = cmd2lines(['hg', 'shelve', '--list'], cwd=self._path)
        return len(list(lines))


class Project(object):
    _cache = None
    _scanning = False

    def __init__(self, name, path):
        self._name = name
        self._path = path

    @property
    def project_path(self):
        return self._path

    def setcache(self, cache):
        self._cache = cache

    def getname(self):
        return self._name

    def isscanning(self):
        return self._scanning


class Repo(Project):
    _info = None
    _newinfo = None

    def __init__(self, name, path, inspector):
        super(Repo, self).__init__(name, path)
        self._insp = inspector

    def _getinfo(self, caninspect):
        if self._info is not None:
            return self._info

        self._info = self._cache.getcache(self._path, PROJECT_EXPIRY)
        if self._info is not None:
            return self._info

        # get the old value
        old = self._cache.getcache(self._path, 10000000000)

        if not caninspect:
            return old

        info = {}
        info['branch'] = self._insp.getbranch()
        info['changed'] = list(self._insp.getchanged())
        info['untracked'] = list(self._insp.getuntracked())

        # NOTE: do we need to use a separate cache for outgoing status?
        outgoing = self._cache.getcache(self._path + '...outgoing',
                                        OUTGOING_EXPIRY)
        if outgoing is None or not self._insp.outgoingexpensive:
            outgoing = self._insp.getoutgoing()
            if outgoing == '?' and old is not None:
                outgoing = old['outgoing']
            else:
                self._cache.setcache(self._path + '...outgoing', outgoing)

        info['outgoing'] = outgoing
        info['stashes'] = self._insp.getstashcount()
        self._cache.setcache(self._path, info)
        self._info = info
        return info

    def getstatus(self, caninspect):
        info = self._getinfo(caninspect)
        if info is None:
            return 'JERJERROD:UNKNOWN'

        if info['changed'] or info['stashes']:
            return 'JERJERROD:CHANGED'
        if info['untracked']:
            return 'JERJERROD:UNTRACKED'
        if info['outgoing']:
            return 'JERJERROD:UNPUSHED'
        return 'JERJERROD:CLEAN'

    def containspath(self, path):
        return os.path.realpath(path).startswith(self._path)


class Workspace(Project):
    def __init__(self, name, path, ignore):
        super(Workspace, self).__init__(name, path)
        # TODO: find repos
        self._repos = []
        self._garbage = []
        self._ignore = ignore
        self._scan()

    def setcache(self, cache):
        super(Workspace, self).setcache(cache)
        for repo in self._repos:
            repo.setcache(cache)

    def _scan(self):
        # is there a virtualenv inside this workspace?
        has_venv = os.path.exists(os.path.join(self._path, 'bin', 'activate'))
        ignore = self._ignore
        if has_venv:
            ignore = list(self._ignore)
            ignore += [
                'bin',
                'include',
                'share',
                'lib',
                'lib64',
                'pip-selfcheck.json'
            ]

        for name in os.listdir(self._path):
            subpath = join(self._path, name)
            inspector = None
            if os.path.isdir(join(subpath, '.git')):
                inspector = GitInspector(subpath)
            elif os.path.isdir(join(subpath, '.hg')):
                inspector = HgInspector(subpath)
            if inspector is not None:
                # create a Repo object
                self._repos.append(Repo(name, subpath, inspector))
            else:
                # do we need to ignore this thing?
                if name not in ignore:
                    self._garbage.append(name)

    def getstatus(self, caninspect):
        # return the worst status
        all_ = set((repo.getstatus(caninspect) for repo in self._repos))
        for status in ('JERJERROD:UNKNOWN', 'JERJERROD:CHANGED',
                       'JERJERROD:UNTRACKED', 'JERJERROD:UNPUSHED'):
            if status in all_:
                return status
        if len(self._garbage):
            return 'JERJERROD:GARBAGE'
        return 'JERJERROD:CLEAN'

    def getgarbage(self):
        return self._garbage

    def containspath(self, path):
        return os.path.realpath(path).startswith(self._path)


def get_all_projects(diskcache, memcache):
    for name, path, flags in get_workspaces(memcache):
        ignore = []
        for flag in flags:
            if flag.startswith('IGNORE='):
                ignore.append(flag[7:])

        project = Workspace(name, path, ignore=ignore)
        project.setcache(diskcache)
        yield project
    for name, path, flags in get_singles(memcache):
        assert not len(flags)
        # what type of inspector?
        if os.path.isdir(join(path, '.git')):
            inspector = GitInspector(path)
        elif os.path.isdir(join(path, '.hg')):
            inspector = HgInspector(path)
        else:
            raise Exception("Bad project path %s" % path)  # noqa
        project = Repo(name, path, inspector)
        project.setcache(diskcache)
        yield project
