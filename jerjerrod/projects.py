from __future__ import (
    absolute_import, division, unicode_literals, print_function)
from subprocess import check_output, STDOUT, CalledProcessError, TimeoutExpired
import re
import os
from os.path import join

from jerjerrod.caching import PROJECT_EXPIRY, OUTGOING_EXPIRY
from jerjerrod.config import get_workspaces, get_singles


HOME = os.environ['HOME']
# allow up to 10 seconds to contact a remote HG server
HG_REMOTE_TIMEOUT = 10


def cmd2lines(*args, **kwargs):
    output = check_output(*args, **kwargs)
    for line in output.decode('utf-8').split('\n'):
        line = line.rstrip()
        if len(line):
            yield line


class Inspector(object):
    _proc = None
    _callback = None

    outgoingexpensive = True

    def __init__(self, path):
        self._path = path

    def checkproc(self):
        # closes off the background process if it is still running
        if self._proc:
            retval = self._proc.poll()
            if retval is not None:
                try:
                    assert retval == 0
                    stdout = self._proc.stdout.read()
                    alllines = (line.rstrip()
                                for line in stdout.decode('utf-8').split('\n'))
                    self._callback(line for line in alllines if len(line))
                finally:
                    self._proc = None
                    self._callback = None

        return self._proc is not None


class GitInspector(Inspector):
    _statuslines = None
    outgoingexpensive = False

    def getbranch(self):
        lines = list(cmd2lines(['git', 'branch'], cwd=self._path))
        for line in lines:
            if line.startswith('* ') and len(line) > 2:
                return line[2:]
        return '__NO_BRANCH__'

    def statuslines(self):
        if self._statuslines is None:
            changed = []
            untracked = []
            lines = cmd2lines(['git', 'status', '--short'], cwd=self._path)
            for line in lines:
                if line[:3] in ('M  ', 'A  ', 'D  ', ' M '):
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
        return self.statuslines()[1]

    def getoutgoing(self):
        known = set()
        found = set()
        wip = set()
        cmd = ['git', 'branch', '--verbose', '--all']
        regex = re.compile(
            r'^(\* (?:\(HEAD detached.*?\)|\w+)|  \S+)\s+(\w+|->)')
        for line in cmd2lines(cmd, cwd=self._path):
            match = regex.match(line)
            if match is None:
                raise Exception("Did not understand %r" % line)
            #lead = match.group(1)[:2]
            branch = match.group(1)[2:]
            revhash = match.group(2)
            if branch.startswith('(HEAD detached'):
                found.add(revhash)
                continue
            if branch.startswith('remotes/') and branch.endswith('/HEAD'):
                continue
            assert revhash != '->'
            known.add(revhash)
            # if the branch starts with remotes/, we want to mark the rev
            # as found
            if branch.startswith('remotes/'):
                if branch.endswith('.WIP'):
                    wip.add(revhash)
                elif '.WIP' not in branch:
                    found.add(revhash)

        # manually check to see if there are revhashes not contained in any
        # remote branches
        for revhash in known - found:
            cmd = ['git', 'branch', '--all', '--contains', revhash]
            revfound = False
            for match in cmd2lines(cmd, cwd=self._path):
                assert match[:2] in ('  ', '* ')
                branch = re.split(r'\s+', match[2:])[0]
                if branch.startswith('remotes/origin/'):
                    revfound = True
                    break
            if not revfound:
                return '1+'

        return 0

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
        if self._statuslines is None:
            changed = []
            untracked = []
            lines = cmd2lines(['hg', 'status'], cwd=self._path)
            for line in lines:
                if line[:2] in ('M ', 'A ', 'D ', 'R '):
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
            if err.output.endswith(b'no changes found\n'):
                return 0
            raise

        return '1+'

    def getstashcount(self):
        lines = cmd2lines(['hg', 'shelve', '--list'], cwd=self._path)
        return len(list(lines))


class Project(object):
    _cache = None
    _scanning = False

    def setcache(self, cache):
        self._cache = cache

    def getname(self):
        return self._name

    def isscanning(self):
        return self._scanning


class Repo(Project):
    _info = None
    _proc = None
    _newinfo = None

    def __init__(self, name, path, inspector):
        super(Repo, self).__init__()
        self._name = name
        self._path = path
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


class Workspace(Project):
    def __init__(self, name, path, ignore):
        super(Workspace, self).__init__()
        # TODO: find repos
        self._name = name
        self._path = path
        self._repos = []
        self._garbage = []
        self._ignore = ignore
        self._scan()

    def setcache(self, cache):
        super(Workspace, self).setcache(cache)
        for repo in self._repos:
            repo.setcache(cache)

    def _scan(self):
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
                if name not in self._ignore:
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


def get_all_projects(cache):
    for name, path, flags in get_workspaces():
        ignore = []
        for flag in flags:
            if flag.startswith('IGNORE='):
                ignore.append(flag[7:])

        project = Workspace(name, path, ignore=ignore)
        project.setcache(cache)
        yield project
    for name, path, flags in get_singles():
        assert not len(flags)
        # what type of inspector?
        if os.path.isdir(join(path, '.git')):
            inspector = GitInspector(path)
        elif os.path.isdir(join(path, '.hg')):
            inspector = HgInspector(path)
        else:
            raise Exception("Bad project path %s" % path)  # noqa
        project = Repo(name, path, inspector)
        project.setcache(cache)
        yield project
