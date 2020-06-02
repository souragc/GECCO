"""Generic protocol for ORF detection in DNA sequences.
"""

import abc
import io
import os
import subprocess
import tempfile
import typing
from typing import Iterable, Iterator, List, Optional

import Bio.SeqIO
import pyrodigal
from Bio.Alphabet import ProteinAlphabet
from Bio.Seq import Seq
from Bio.SeqRecord import SeqRecord

from ._base import BinaryRunner

if typing.TYPE_CHECKING:
    from Bio.SeqRecord import SeqRecord


class ORFFinder(metaclass=abc.ABCMeta):
    """An abstract base class to provide a generic ORF finder.
    """

    @abc.abstractmethod
    def find_proteins(self, sequences: Iterable["SeqRecord"],) -> Iterable["SeqRecord"]:
        """Find all proteins from a list of DNA sequences.
        """
        return NotImplemented  # type: ignore


class PyrodigalFinder(ORFFinder):
    """An `ORFFinder` that uses the Pyrodigal bindings to PRODIGAL.

    PRODIGAL is a fast and reliable protein-coding gene prediction for
    prokaryotic genomes, with support for draft genomes and metagenomes.

    See Also:
        .. [PMC2848648] https://www.ncbi.nlm.nih.gov/pmc/articles/PMC2848648/

    """

    def __init__(self, metagenome: bool = True) -> None:
        """Create a new `PyrodigalFinder` instance.

        Arguments:
            metagenome (bool): Whether or not to run PRODIGAL in metagenome
                mode, defaults to `True`.

        """
        super().__init__()
        self.metagenome = metagenome
        self.pyrodigal = pyrodigal.Pyrodigal(meta=metagenome)

    def find_proteins(
        self, sequences: Iterable["SeqRecord"],
    ) -> Iterator["SeqRecord"]:  # noqa: D102
        for i, dna_sequence in enumerate(sequences):
            # find all genes in the given DNA sequence
            genes = self.pyrodigal.find_genes(str(dna_sequence.seq))
            for j, gene in enumerate(genes):
                # translate the gene to a protein sequence
                seq = Seq(gene.translate(), ProteinAlphabet())
                protein = SeqRecord(seq)
                # convert the gene to a biopython `SeqRecord` with the same
                # content as the PRODIGAL record description that's expected
                # in the rest of the program
                protein.id = protein.name = f"{dna_sequence.id}_{j+1}"



                protein.description = " # ".join(map(str, [
                    protein.id,
                    gene.begin,
                    gene.end,
                    gene.strand,
                    f"ID={i+1}_{j+1};partial={int(gene.partial_begin)}{int(gene.partial_end)};"
                    f"start_type={gene.start_type};rbs_motif={gene.rbs_motif};"
                    f"rbs_spacer={gene.rbs_spacer};gc_cont={gene.gc_cont:0.3f}"
                ]))

                yield protein


class ProdigalFinder(BinaryRunner, ORFFinder):
    """An `ORFFinder` that wraps the PRODIGAL binary.

    PRODIGAL is a fast and reliable protein-coding gene prediction for
    prokaryotic genomes, with support for draft genomes and metagenomes.

    See Also:
        .. [PMC2848648] https://www.ncbi.nlm.nih.gov/pmc/articles/PMC2848648/

    """

    BINARY = "prodigal"

    def __init__(self, metagenome: bool = True) -> None:
        """Create a new `ProdigalFinder` instance.

        Arguments:
            metagenome (bool): Whether or not to run PRODIGAL in metagenome
                mode, defaults to `True`.

        """
        super().__init__()
        self.metagenome = metagenome

    def find_proteins(
        self, sequences: Iterable["SeqRecord"],
    ) -> Iterator["SeqRecord"]:  # noqa: D102
        with tempfile.NamedTemporaryFile(
            "w+", prefix=self.BINARY, suffix=".faa"
        ) as tmp:
            # write a FASTA buffer to pass as PRODIGAL input
            buffer = io.TextIOWrapper(io.BytesIO())
            Bio.SeqIO.write(sequences, buffer, "fasta")
            # build the command line
            cmd: List[str] = [self.BINARY, "-q", "-a", tmp.name]
            if self.metagenome:
                cmd.extend(["-p", "meta"])
            # run the program
            completed = subprocess.run(
                cmd, input=buffer.detach().getbuffer(), stdout=subprocess.DEVNULL
            )
            completed.check_returncode()
            yield from Bio.SeqIO.parse(tmp, "fasta")
