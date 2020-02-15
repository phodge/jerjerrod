import os
from typing import TYPE_CHECKING, List, Optional

import click

if TYPE_CHECKING:
    from typing_extensions import Literal

    StyleName = Literal['s_clean', 's_unpushed', 's_changed', 's_untracked']

HOME = os.getenv("HOME", "")


def _shortpath(pathstr):
    if HOME and pathstr.startswith(HOME):
        return "~" + pathstr[len(HOME):]
    return pathstr


def print_workspace_title(project):
    click.secho(':: %s ++' % _shortpath(project._path), fg="blue", bold=True)
    #sys.stdout.write(style_wspath(_shortpath(project._path)))
    #sys.stdout.write(style_wstitle("] ::") + "\n")


def _getfilesstr(files: List[str]) -> str:
    if len(files) == 0:
        return ""

    # can we fit the names of all the things changed into one 40-character
    # string?
    joined = ', '.join(files)
    if len(joined) <= 40:
        return joined

    # if we just take the folder name of each changed thing and compress
    # it, do we get a list that's short enough to print? (under 40 chars)
    shortjoined = ', '.join([name.split("/", 1)[0] + "/..." for name in files])
    if len(shortjoined) <= 40:
        return shortjoined

    # otherwise all we can do is return a count
    return str(len(files))


def style(stylename: "Optional[str]", text: str) -> str:
    if stylename == 's_changed':
        return click.style(text, fg="red", bold=True)

    if stylename == 's_unpushed':
        return click.style(text, fg="yellow", bold=False)

    if stylename == 's_untracked':
        return click.style(text, fg="red", bold=False)

    return click.style(text, fg='green', bold=False)


class RepoSummary:
    _main_style: "Optional[StyleName]" = None

    def __init__(self, repo, indent: int) -> None:
        self._repo = repo
        self._indent: str = ' ' * indent

        info = repo._getinfo(True)

        self._branch: str = info['branch']
        self._files_changed = info['changed']
        self._files_untracked = info['untracked']
        # when inspecting HG repos, outgoing might be a string
        self._outgoing_info = "" if info['outgoing'] == 0 else info['outgoing']
        self._num_stashes: int = info['stashes']

        if len(self._files_changed):
            self._main_style = 's_changed'
        elif self._outgoing_info:
            self._main_style = 's_unpushed'
        elif len(self._files_untracked) or self._num_stashes:
            self._main_style = 's_untracked'

    def _printtitle(self):
        click.echo(style(self._main_style, "%s> %s" % (self._indent, _shortpath(self._repo._path))))

    def printnow(self):
        self._printtitle()

        # make a collection of stats to print (if needed)
        stats: List[str] = []

        changes = _getfilesstr(self._files_changed)
        if changes:
            stats.append(style("s_changed", 'Changed: ' + changes))

        if self._outgoing_info:
            stats.append(style("s_unpushed", 'Outgoing: %s' % (self._outgoing_info, )))

        untracked = _getfilesstr(self._files_untracked)
        if untracked:
            stats.append(style("s_untracked", 'Untracked: ' + untracked))

        if self._num_stashes:
            stats.append(style("s_untracked", 'Stashes: %d' % self._num_stashes))

        if len(stats):
            pipe = click.style(' | ', fg="black", dim=True)
            oneline = pipe.join(stats)
            if len(oneline) <= 80:
                click.echo("%s  %s" % (self._indent, oneline))
            else:
                for stat in stats:
                    click.echo("%s  %s" % (self._indent, stat))
