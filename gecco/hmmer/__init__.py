"""Compatibility wrapper for HMMER binaries and output.
"""
import collections
import configparser
import contextlib
import csv
import errno
import glob
import os
import subprocess
import tempfile
import typing
from typing import Dict, Optional, Iterable, Iterator, List, Mapping, Type, Sequence

import pandas
import pkg_resources
from Bio import SeqIO

from .._base import BinaryRunner
from ..model import Gene, Domain, Hmm

if typing.TYPE_CHECKING:
    from Bio.SeqRecord import SeqRecord

    _T = typing.TypeVar("_T", bound="DomainRow")


class DomainRow(typing.NamedTuple):
    """A single row in a domain table created by ``hmmsearch``.

    See Also:
        The description of each field in page 48 of the `HMMER manual
        <http://eddylab.org/software/hmmer3/3.1b2/Userguide.pdf>`_.

    """

    target_name: str
    target_accession: Optional[str]
    target_length: int
    query_name: str
    query_accession: Optional[str]
    query_length: int
    evalue: float
    score: float
    bias: float
    domain_number: int
    domain_total: int
    c_evalue: float
    i_evalue: float
    domain_score: float
    domain_bias: float
    hmm_from: int
    hmm_to: int
    ali_from: int
    ali_to: int
    env_from: int
    env_to: int
    post: float
    description: Optional[str]

    @classmethod
    def from_line(cls: Type["_T"], row: str) -> "_T":
        """Extract a `DomainRow` from a single domain table line.
        """
        line = list(filter(None, row.split(" ")))
        values = {}
        for i, (field, ty) in enumerate(cls.__annotations__.items()):
            if isinstance(ty, type):
                values[field] = ty(line[i])
            elif field == "target_accession" or field == "query_accession":
                values[field] = None if line[i] == "-" else line[i]
            elif field == "description":
                values[field] = " ".join(line[i:]) if line[i:] else None
        return cls(**values)


class HMMER(BinaryRunner):
    """A wrapper for HMMER that scans a HMM library against protein sequences.
    """

    BINARY = "hmmsearch"

    def __init__(self, hmm: "Hmm", cpus: Optional[int] = None) -> None:
        """Prepare a new HMMER annotation handler with the given ``hmms``.

        Arguments:
            hmm (str): The path to the file containing the HMMs.
            cpus (int, optional): The number of CPUs to allocate for the
                ``hmmsearch`` command. Give ``None`` to use the default.

        """
        super().__init__()
        self.hmm = hmm
        self.cpus = cpus

    def run(self, genes: Sequence[Gene]) -> Sequence[Gene]:
        """Run HMMER on proteins of ``genes`` and update them with domains.

        Arguments:
            genes (sequence of `~gecco.model.Gene`): A sequence of genes to
                annotate with ``self.hmm``.

        """
        # collect genes and build an index of genes by protein id
        gene_index = {gene.id: gene for gene in genes}

        # create a temporary file to write the input and output to
        seqs_tmp = tempfile.NamedTemporaryFile(prefix="hmmer", suffix=".faa")
        doms_tmp = tempfile.NamedTemporaryFile(prefix="hmmer", suffix=".dom", mode="rt")

        # write protein sequences
        protein_records = (g.protein.to_record() for g in genes)
        SeqIO.write(protein_records, seqs_tmp.name, "fasta")

        # Prepare the command line arguments
        cmd = ["hmmsearch", "--noali", "--domtblout", doms_tmp.name]
        if self.cpus is not None:
            cmd.extend(["--cpu", str(self.cpus)])
        cmd.extend([self.hmm.path, seqs_tmp.name])

        # Run HMMER
        subprocess.run(cmd, stdout=subprocess.DEVNULL).check_returncode()

        # Read the domain table
        lines = filter(lambda line: not line.startswith("#"), doms_tmp)
        rows = map(DomainRow.from_line, lines)

        # update protein domains
        for row in rows:
            gene = gene_index[row.target_name]
            name = self.hmm.relabel(row.query_accession or row.query_name)
            domain = Domain(name, row.env_from, row.env_to, self.hmm.id, row.i_evalue)
            gene.protein.domains.append(domain)

        return genes


def embedded_hmms() -> Iterator[Hmm]:
    """Iterate over the embedded HMMs that are shipped with GECCO.
    """
    for ini in glob.glob(pkg_resources.resource_filename(__name__, "*.ini")):
        cfg = configparser.ConfigParser()
        cfg.read(ini)
        yield Hmm(path=ini.replace(".ini", ".hmm.gz"), **dict(cfg.items("hmm")))