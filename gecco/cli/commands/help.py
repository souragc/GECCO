"""Implementation of the ``gecco run`` subcommand.
"""

import csv
import logging
import multiprocessing
import os
import pickle
import random
import sys
import textwrap
import typing
from typing import Any, Dict, Mapping, List, Optional, TextIO

import rich.console

from ._base import Command
from ._main import Main


class Help(Command):  # noqa: D101

    summary = "display the help message of another subcommand."
    doc = f"""
    gecco help - {summary}

    Usage:
        gecco help (-h | --help)
        gecco help [<cmd>]

    Arguments:
        <cmd>                      a command to get the help message of.

    Parameters:
        -h, --help                 show the message for ``gecco`` or
                                   for a given subcommand.
    """

    def __call__(self) -> int:  # noqa: D102
        # Get the subcommand class
        if self.args["<cmd>"] is not None:
            subcmd_cls = Main._get_subcommand(self.args["<cmd>"])
        else:
            subcmd_cls = None

        # Exit if no known command was found
        if self.args["<cmd>"] is not None and subcmd_cls is None:
            self.error("Unknown subcommand", repr(self.args["<cmd>"]))
            return 1

        # Render the help message
        doc = Main.doc if subcmd_cls is None else subcmd_cls.doc
        rich.print(textwrap.dedent(doc).lstrip(), file=self._stream)
        return 0
