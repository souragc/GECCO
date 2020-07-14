#!/usr/bin/env python
# -*- coding: utf-8 -*-

import configparser
import glob
import gzip
import hashlib
import io
import math
import os
import re
import shutil
import sys
import tarfile
import urllib.request
from functools import partial

import setuptools
from setuptools.command.build_py import build_py as _build_py
from setuptools.command.sdist import sdist as _sdist

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None


class ResponseProgressBar(object):

    def __init__(self, inner, tqdm=tqdm, **kwargs):
        self.inner = inner
        self.total = total = int(inner.headers['Content-Length'])

        if tqdm is not None:
            self.pbar = tqdm(
                total=total,
                leave=True,
                unit='iB',
                unit_scale=True,
                unit_divisor=1024,
                file=sys.stdout,
                **kwargs
            )
            self.update = self.pbar.update
            self.refresh = self.pbar.refresh
        else:
            self.pbar = None
            self.current = 0
            self.next_p = 5
            self.desc = kwargs.get("desc")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if sys.version_info >= (3,):
            self.inner.__exit__(exc_type, exc_value, traceback)
        if self.pbar is not None:
            self.pbar.__exit__(exc_type, exc_value, traceback)
        else:
            print()
        return False

    def read(self, n=None):
        chunk = self.inner.read(n)
        self.update(len(chunk))
        return chunk

    def update(self, n):
        self.current = c = self.current + n
        p = int(float(c) * 100.0 / self.total)
        if p >= self.next_p:
            self.next_p = p + 5
            print(
                "{} : {:>{}}B / {}B [{: 3}%]".format(
                    self.desc,
                    c,
                    int(math.ceil(math.log10(self.total))),
                    self.total,
                    p
                ),
                end="\r"
            )
            sys.stdout.flush()

    def refresh(self):
        pass


class sdist(_sdist):
    """An extension to the `sdist` command that generates a `pyproject.toml`.
    """

    def run(self):
        # build `pyproject.toml` from `setup.cfg`
        c = configparser.ConfigParser()
        c.add_section("build-system")
        c.set("build-system", "requires", str(self.distribution.setup_requires))
        c.set("build-system", 'build-backend', '"setuptools.build_meta"')
        with open("pyproject.toml", "w") as pyproject:
            c.write(pyproject)

        # run the rest of the packaging
        _sdist.run(self)


class update_model(setuptools.Command):
    """A custom command to update the internal CRF model.
    """

    description = 'update the CRF model embedded in the source'
    user_options = [
      ('model=', 'm', 'the path to the new CRF model to use'),
      ('domain=', 'd', 'the path to the new domain composition table'),
    ]

    def initialize_options(self):
        self.model = None
        self.domain = None

    def finalize_options(self):
        if self.model is None:
            raise ValueError("--model argument must be given")
        elif not os.path.exists(self.model):
            raise FileNotFoundError(self.model)
        if self.domain is None:
            raise ValueError("--domain argument must be given")
        elif not os.path.exists(self.domain):
            raise FileNotFoundError(self.domain)

    def info(self, msg):
        self.announce(msg, level=2)

    def run(self):
        import gecco.data

        # Copy the file to the new in-source location and compute its hash.
        hasher = hashlib.md5()
        self.info("Copying the model to the in-source location")
        with open(self.model, "rb") as src:
            with open(gecco.data.realpath("model/crf.model"), "wb") as dst:
                read = lambda: src.read(io.DEFAULT_BUFFER_SIZE)
                for chunk in iter(read, b''):
                    hasher.update(chunk)
                    dst.write(chunk)

        # Write the hash to the signature file next to the model
        self.info("Writing the MD5 signature file")
        with open(gecco.data.realpath("model/crf.model.md5"), "w") as sig:
            sig.write(hasher.hexdigest())

        # Update the domain composition table
        self.info("Copying the domain composition table to the in-source location")
        with open(gecco.data.realpath("knn/training_matrix.tsv.gz"), "wb") as dst:
            with open(self.domain, "rb") as src:
                shutil.copyfileobj(src, dst)


class build_py(_build_py):

    @staticmethod
    def _flush_progress_bar(pbar):
        if not sys.stdout.isatty():
            pbar.refresh()
            sys.stdout.flush()
            sys.stdout.write('\n\033[F')

    user_options = _build_py.user_options + [
        ("hmms=", "H", "directory containing HMM metadata")
    ]

    def initialize_options(self):
        _build_py.initialize_options(self)
        section = type(self).__name__
        self._cfg = configparser.ConfigParser()
        self._cfg.read_dict({section: {
            'hmms': os.path.join("gecco", "data", "hmms"),
        }})
        self._cfg.read(self.distribution.find_config_files())
        self.hmms = self._cfg.get(section, 'hmms')

    def finalize_options(self):
        _build_py.finalize_options(self)
        self.ensure_dirname('hmms')

    def run(self):
        _build_py.run(self)
        for in_ in glob.glob(os.path.join(self.hmms, "*.ini")):
            cfg = configparser.ConfigParser()
            cfg.read(in_)
            out = os.path.join(self.build_lib, in_.replace('.ini', '.hmm.gz'))
            try:
                self.make_file([in_], out, self.download, [out, dict(cfg.items('hmm'))])
            except:
                if os.path.exists(out):
                    os.remove(out)
                raise

    def download(self, output, options):
        base = "https://github.com/althonos/GECCO/releases/download/v{version}/{id}.hmm.gz"
        url = base.format(id=options["id"], version=self.distribution.get_version())
        self.announce("fetching {}".format(url), level=2)
        with ResponseProgressBar(urllib.request.urlopen(url), desc=os.path.basename(output)) as src:
            with open(output, "wb") as dst:
                shutil.copyfileobj(src, dst)


if __name__ == "__main__":
    setuptools.setup(
        cmdclass={
            "build_py": build_py,
            "sdist": sdist,
            "update_model": update_model,
        },
    )
