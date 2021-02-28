"""Implementation of the main ``gecco`` command.
"""

import contextlib
import signal
import sys
import textwrap
import typing
import warnings
from typing import Mapping, Optional, Type

import docopt
import operator
import pkg_resources
import rich.traceback

from ... import __version__
from .._utils import in_context, patch_showwarnings
from . import __name__ as __parent__
from ._base import Command, CommandExit, InvalidArgument


class Main(Command):
    """The *main* command launched before processing subcommands.
    """

    @classmethod
    def _get_subcommand_names(cls) -> Mapping[str, Type[Command]]:
        return [cmd.name for cmd in pkg_resources.iter_entry_points(__parent__)]

    @classmethod
    def _get_subcommands(cls) -> Mapping[str, Type[Command]]:
        commands = {}
        for cmd in pkg_resources.iter_entry_points(__parent__):
            try:
                commands[cmd.name] = cmd.load()
            except pkg_resources.DistributionNotFound as err:
                pass
        return commands

    @classmethod
    def _get_subcommand_by_name(cls, name: str) -> Optional[Type[Command]]:
        for cmd in pkg_resources.iter_entry_points(__parent__):
            if cmd.name == name:
                return cmd.load()
        return None

    # --

    @classmethod
    def doc(cls, fast=False):  # noqa: D102
        if fast:
            commands = (f"    {cmd}" for cmd in cls._get_subcommand_names())
        else:
            commands = (
                "    {:12}{}".format(name, typing.cast(Command, cmd).summary)
                for name, cmd in sorted(
                    cls._get_subcommands().items(), key=operator.itemgetter(0)
                )
            )
        return (
            textwrap.dedent(
                """
        gecco - Gene Cluster Prediction with Conditional Random Fields

        Usage:
            gecco [-v | -vv | -q | -qq] <cmd> [<args>...]
            gecco --version
            gecco --help [<cmd>]

        Commands:
        {commands}

        Parameters:
            -h, --help                 show the message for ``gecco`` or
                                       for a given subcommand.
            -q, --quiet                silence any output other than errors
                                       (-qq silences everything).
            -v, --verbose              increase verbosity (-v is minimal,
                                       -vv is verbose, and -vvv shows
                                       debug information).
            -V, --version              show the program version and exit.

        """
            )
            .lstrip()
            .format(commands="\n".join(commands))
        )

    _options_first = True

    # --

    def execute(self, ctx: contextlib.ExitStack) -> int:
        # Run the app, elegantly catching any interrupts or exceptions
        try:
            # check arguments and enter context
            self._check()
            ctx.enter_context(patch_showwarnings(self._showwarnings))

            # Get the subcommand class
            subcmd_name = self.args["<cmd>"]
            try:
                subcmd_cls = self._get_subcommand_by_name(subcmd_name)
            except pkg_resources.DistributionNotFound as dnf:
                self.error("The", repr(subcmd_name), "subcommand requires package", dnf.req)
                return 1

            # exit if no known command was found
            if subcmd_name is not None and subcmd_cls is None:
                self.error("Unknown subcommand", repr(subcmd_name))
                return 1
            # if a help message was required, delegate to the `gecco help` command
            if (
                self.args["--help"]
                or "-h" in self.args["<args>"]
                or "--help" in self.args["<args>"]
            ):
                subcmd = typing.cast(Type[Command], self._get_subcommand_by_name("help"))(
                    argv=["help"] + [subcmd_name],
                    stream=self._stream,
                    options=self.args,
                    config=self.config,
                )
            # print version information if `--version` in flags
            elif self.args["--version"]:
                self.console.print("gecco", __version__)
                return 0
            # initialize the command if is valid
            else:
                subcmd = typing.cast(Type[Command], subcmd_cls)(
                    argv=[self.args["<cmd>"]] + self.args["<args>"],
                    stream=self._stream,
                    options=self.args,
                    config=self.config,
                )
                subcmd.verbose = self.verbose
                subcmd.quiet = self.quiet
                subcmd.progress.disable = self.quiet > 0
            # run the subcommand
            return subcmd.execute(ctx)
        except CommandExit as sysexit:
            return sysexit.code
        except KeyboardInterrupt:
            self.error("Interrupted")
            return -signal.SIGINT
        except Exception as e:
            self.error(
                "An unexpected error occurred. Consider opening"
                " a new issue on the bug tracker"
                " (https://github.com/zellerlab/GECCO/issues/new) if"
                " it persists, including the traceback below:"
            )
            traceback = rich.traceback.Traceback.from_exception(type(e), e, e.__traceback__)
            self.console.print(traceback)
            # return errno if exception has any
            return typing.cast(int, getattr(e, "errno", 1))
