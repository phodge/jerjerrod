from __future__ import absolute_import, division, print_function, unicode_literals

import sys
from os.path import dirname, exists, join, realpath

import click

from jerjerrod import __version__
from jerjerrod.caching import DiskCache
from jerjerrod.cli.utils import RepoSummary, print_workspace_title, style
from jerjerrod.projects import get_all_projects


@click.group(invoke_without_command=True)
@click.pass_context
@click.version_option(__version__, prog_name="jerjerrod")
def cli(ctx):
    if ctx.invoked_subcommand is None:
        click.secho(
            "No subcommand specified. Clearing cache and presenting summary",
            fg="yellow",
        )
        do_clearcache(".", False)
        present_summary(".")
        sys.exit(2)


# TODO: which commands need to be fast?
# WS name PATH
# WS names
# WS status NAME
# WS changed NAME
# WS untracked NAME
# WS stashes NAME
# WS outgoing NAME

# TODO: make the following invocations work:
# WS summary
# WS names
# WS name PATH
# WS status NAME
# WS changed NAME
# WS untracked NAME
# WS stashes NAME
# WS outgoing NAME


@cli.command()
@click.argument("STATUS", nargs=-1)
def namesbystatus(status):
    """
    Names returned will be one of the following:
    - names of workspaces that match the given STATUS
    - names of other repos that match the given STATUS

    Status can be one of:
      JERJERROD:UNKNOWN
      JERJERROD:CHANGED
      JERJERROD:UNTRACKED
      JERJERROD:UNPUSHED
      JERJERROD:CLEAN
    """
    assert len(status)
    assert isinstance(status, tuple)
    # use the disk cache
    for proj in get_all_projects(DiskCache(), {}):
        if proj.getstatus(True) in status:
            print(proj.getname())


@cli.command()
@click.argument("NAME_OR_PATH")
def summary(name_or_path):
    present_summary(name_or_path)


def present_summary(name_or_path):
    # use the disk cache
    cache = DiskCache()

    project = None
    for proj in get_all_projects(cache, {}):
        if proj.getname() == name_or_path:
            project = proj
            break
        if proj.containspath(name_or_path):
            project = proj
            break

    if not project:
        raise Exception("No project {}".format(name_or_path))

    if hasattr(project, "_repos"):
        print_workspace_title(project)
        # TODO: summarise workspace
        indent = 2
        for repo in project._repos:
            rs = RepoSummary(repo, indent)
            rs.printnow()
        garbage = project.getgarbage()
        if len(garbage) == 1:
            click.echo(
                style("s_untracked", "%sGARBAGE: %s" % (" " * indent, garbage[0]))
            )
        elif len(garbage):
            click.echo(style("s_untracked", "%sGARBAGE:" % (" " * indent,)))
            for g in garbage:
                click.echo(style("s_untracked", "%s  %s" % (" " * indent, g)))
    else:
        rs = RepoSummary(project, 0)
        rs.printnow()


@cli.command()
@click.argument("NAMES_AND_PATHS", nargs=-1)
def nottoday(names_and_paths):
    """Tell jerjerrod not to report about certain projects until tomorrow."""
    # use the disk cache
    cache = DiskCache()

    # grab the current ignore list
    ignore = cache.getignorelist()

    for proj in get_all_projects(cache, {}):
        for name_or_path in names_and_paths:
            if proj.getname() == name_or_path or proj.containspath(name_or_path):
                ignore.add(proj.project_path)

    # save the new ignore list
    cache.setignorelist(ignore)


@cli.command()
@click.argument("PATH", nargs=-1, type=click.Path(exists=True))
@click.option(
    "--local", is_flag=True, help="Don't touch the expensive 'hg outgoing' cache"
)
def clearcache(path, local):
    """clear all caches associated with PATH"""
    do_clearcache(path, local)


def do_clearcache(path, local):
    cache = DiskCache()

    def _checkandclear(path):
        if exists(join(path, ".git")) or exists(join(path, ".hg")):
            cache.clearcache(path)
            if not local:
                cache.clearcache(path + "...outgoing")

    for trypath in map(realpath, path):
        while len(trypath) > 2:
            _checkandclear(trypath)
            # shorten the path and try again
            trypath = dirname(trypath)


if __name__ == "__main__":
    cli()
