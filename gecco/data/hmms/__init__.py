import configparser
import glob
import os
import re
import typing
import pkg_resources
from typing import Iterator, List, Optional

if typing.TYPE_CHECKING:
    import pandas


class Hmm(typing.NamedTuple):

    id: str
    version: str
    url: str
    relabel_with: Optional[str] = None

    @property
    def path(self) -> str:
        basename = f"{self.id}.hmm.gz"
        return pkg_resources.resource_filename(__name__, basename)

    def relabel(self, domain: str) -> str:
        if self.relabel_with is None:
            return domain
        before, after = re.match("^s/(.*)/(.*)/$", self.relabel_with).groups()  # type: ignore
        regex = re.compile(before)
        return regex.sub(after, domain)


class ForeignHmm(typing.NamedTuple):

    path: str

    @property
    def id(self) -> str:
        path = self.path
        if self.path.endswith((".gz", ".xz", ".bz2")):
            path, _ = os.path.splitext(path)
        return os.path.splitext(os.path.basename(path))[0]

    @property
    def version(self) -> str:
        return "?"

    def relabel(self, domain: str) -> str:
        return domains.split(".")[0]  # type: ignore


def iter() -> Iterator[Hmm]:
    for ini in glob.glob(pkg_resources.resource_filename(__name__, "*.ini")):
        cfg = configparser.ConfigParser()
        cfg.read(ini)
        yield Hmm(**dict(cfg.items("hmm")))
