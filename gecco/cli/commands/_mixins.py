import gzip
import io
import itertools
import os
import operator
import typing
from typing import BinaryIO, Container, Iterator, Iterable, Optional, List

from .._utils import ProgressReader, guess_sequences_format
from ._base import Command, CommandExit, InvalidArgument

if typing.TYPE_CHECKING:
    from Bio.SeqRecord import SeqRecord
    from ...model import Cluster, Gene, FeatureTable, GeneTable
    from ...hmmer import HMM
    from ...types import TypeClassifier


class SequenceLoaderMixin(Command):

    format: Optional[str]
    genome: str

    def _load_sequences(self) -> Iterator["SeqRecord"]:
        from Bio import SeqIO

        try:
            # guess format or use the one given in CLI
            if self.format is not None:
                format: Optional[str] = self.format.lower()
                self.info("Using", "user-provided sequence format", repr(format), level=2)
            else:
                self.info("Detecting", "sequence format from file contents", level=2)
                format = guess_sequences_format(self.genome)
                if format is None:
                    raise RuntimeError(f"Failed to detect format of {self.genome!r}")
                self.success("Detected", "format of input as", repr(format), level=2)
            # get filesize and unit
            input_size = os.stat(self.genome).st_size
            total, scale, unit = ProgressReader.scale_size(input_size)
            task = self.progress.add_task("Loading sequences", total=total, unit=unit, precision=".1f")
            # load sequences
            n = 0
            self.info("Loading", "sequences from genomic file", repr(self.genome), level=1)
            with ProgressReader(open(self.genome, "rb"), self.progress, task, scale) as f:
                for record in SeqIO.parse(io.TextIOWrapper(f), format):  # type: ignore
                    yield record
                    n += 1
        except FileNotFoundError as err:
            self.error("Could not find input file:", repr(self.genome))
            raise CommandExit(err.errno) from err
        except ValueError as err:
            self.error("Failed to load sequences:", err)
            raise CommandExit(getattr(err, "errno", 1)) from err
        else:
            self.success("Found", n, "sequences", level=1)


class TableLoaderMixin(Command):

    genes: str
    features: List[str]

    def _load_genes(self) -> Iterator["Gene"]:
        from ...model import GeneTable

        try:
            # get filesize and unit
            input_size = os.stat(self.genes).st_size
            total, scale, unit = ProgressReader.scale_size(input_size)
            task = self.progress.add_task("Loading genes", total=total, unit=unit, precision=".1f")
            # load gene table
            self.info("Loading", "genes table from file", repr(self.genes))
            with ProgressReader(open(self.genes, "rb"), self.progress, task, scale) as genes_file:
                yield from GeneTable.load(io.TextIOWrapper(genes_file)).to_genes()  # type: ignore
        except OSError as err:
            self.error("Fail to parse genes coordinates: {}", err)
            raise CommandExit(err.errno) from err

    def _load_features(self) -> "FeatureTable":
        from ...model import FeatureTable

        features = FeatureTable()
        for filename in self.features:
            try:
                # get filesize and unit
                input_size = os.stat(filename).st_size
                total, scale, unit = ProgressReader.scale_size(input_size)
                task = self.progress.add_task("Loading features", total=total, unit=unit, precision=".1f")
                # load features
                self.info("Loading", "features table from file", repr(filename))
                with ProgressReader(open(filename, "rb"), self.progress, task, scale) as in_:
                    features += FeatureTable.load(io.TextIOWrapper(in_)) # type: ignore
            except FileNotFoundError as err:
                self.error("Could not find feature file:", repr(filename))
                raise CommandExit(err.errno) from err

        self.success("Loaded", "a total of", len(features), "features", level=1)
        return features

    def _annotate_genes(self, genes: List["Gene"], features: "FeatureTable") -> List["Gene"]:
        from ...model import Domain

        # index genes by protein_id
        gene_index = { gene.protein.id:gene for gene in genes }
        if len(gene_index) < len(genes):
            raise ValueError("Duplicate gene names in input genes")

        # add domains from the feature table
        unit = "row" if len(features) == 1 else "rows"
        task = self.progress.add_task("Annotating genes", total=len(features), unit=unit, precision="")
        for row in typing.cast(Iterable["FeatureTable.Row"], self.progress.track(features, total=len(features), task_id=task)):
            # get gene by ID and check consistency
            gene = gene_index[row.protein_id]
            if gene.source.id != row.sequence_id:
                raise ValueError(f"Mismatched source sequence for {row.protein_id!r}: {gene.source.id!r} != {row.sequence_id!r}")
            elif gene.end - gene.start != row.end - row.start:
                raise ValueError(f"Mismatched gene length for {row.protein_id!r}: {gene.end - gene.start!r} != {row.end - row.start!r}")
            elif gene.start != row.start:
                raise ValueError(f"Mismatched gene start for {row.protein_id!r}: {gene.start!r} != {row.start!r}")
            elif gene.end != row.end:
                raise ValueError(f"Mismatched gene end for {row.protein_id!r}: {gene.end!r} != {row.end!r}")
            elif gene.strand.sign != row.strand:
                raise ValueError(f"Mismatched gene strand for {row.protein_id!r}: {gene.strand.sign!r} != {row.strand!r}")
            elif gene.source.id != row.sequence_id:
                raise ValueError(f"Mismatched sequence ID {row.protein_id!r}: {gene.source.id!r} != {row.sequence_id!r}")
            # add the row domain to the gene
            domain = Domain(
                name=row.domain,
                start=row.domain_start,
                end=row.domain_end,
                hmm=row.hmm,
                i_evalue=row.i_evalue,
                pvalue=row.pvalue,
                probability=row.bgc_probability,
            )
            gene.protein.domains.append(domain)

        # return
        return list(gene_index.values())


class OutputWriterMixin(Command):

    genome: str
    output_dir: str

    def _make_output_directory(self, outputs: List[str]) -> None:
        # Make output directory
        self.info("Using", "output folder", repr(self.output_dir), level=1)
        try:
            os.makedirs(self.output_dir, exist_ok=True)
        except OSError as err:
            self.error("Could not create output directory: {}", err)
            raise CommandExit(err.errno) from err

        # Check if output files already exist
        for output in outputs:
            if os.path.isfile(os.path.join(self.output_dir, output)):
                self.warn("Output folder contains files that will be overwritten")
                break

    def _write_feature_table(self, genes: List["Gene"]) -> None:
        from ...model import FeatureTable

        base, _ = os.path.splitext(os.path.basename(self.genome))
        pred_out = os.path.join(self.output_dir, f"{base}.features.tsv")
        self.info("Writing", "feature table to", repr(pred_out), level=1)
        with open(pred_out, "w") as f:
            FeatureTable.from_genes(genes).dump(f)

    def _write_genes_table(self, genes: List["Gene"]) -> None:
        from ...model import GeneTable

        base, _ = os.path.splitext(os.path.basename(self.genome))
        pred_out = os.path.join(self.output_dir, f"{base}.genes.tsv")
        self.info("Writing", "gene table to", repr(pred_out), level=1)
        with open(pred_out, "w") as f:
            GeneTable.from_genes(genes).dump(f)

    def _write_cluster_table(self, clusters: List["Cluster"]) -> None:
        from ...model import ClusterTable

        base, _ = os.path.splitext(os.path.basename(self.genome))
        cluster_out = os.path.join(self.output_dir, f"{base}.clusters.tsv")
        self.info("Writing", "cluster table to", repr(cluster_out), level=1)
        with open(cluster_out, "w") as out:
            ClusterTable.from_clusters(clusters).dump(out)

    def _write_clusters(self, clusters: List["Cluster"], merge: bool = False) -> None:
        from Bio import SeqIO

        if merge:
            base, _ = os.path.splitext(os.path.basename(self.genome))
            gbk_out = os.path.join(self.output_dir, f"{base}.clusters.gbk")
            records = (cluster.to_seq_record() for cluster in clusters)
            SeqIO.write(records, gbk_out, "genbank")
        else:
            for cluster in clusters:
                gbk_out = os.path.join(self.output_dir, f"{cluster.id}.gbk")
                self.info("Writing", f"cluster [bold blue]{cluster.id}[/] to", repr(gbk_out), level=1)
                SeqIO.write(cluster.to_seq_record(), gbk_out, "genbank")


class DomainFilterMixin(Command):

    e_filter: Optional[float]
    p_filter: Optional[float]

    def _filter_domains(self, genes: List["Gene"]) -> List["Gene"]:
        # Filter i-evalue and p-value if required
        if self.e_filter is not None:
            self.info("Excluding", "domains with e-value over", self.e_filter, level=1)
            key = lambda d: d.i_evalue < self.e_filter
            genes = [
                gene.with_protein(gene.protein.with_domains(filter(key, gene.protein.domains)))
                for gene in genes
            ]
        if self.p_filter is not None:
            self.info("Excluding", "domains with p-value over", self.p_filter, level=1)
            key = lambda d: d.pvalue < self.p_filter
            genes = [
                gene.with_protein(gene.protein.with_domains(filter(key, gene.protein.domains)))
                for gene in genes
            ]
        if self.p_filter is not None or self.e_filter is not None:
            count = sum(1 for gene in genes for domain in gene.protein.domains)
            self.info("Using", "remaining", count, "domains", level=1)
        return genes


class AnnotatorMixin(DomainFilterMixin):

    hmm: Optional[List[str]]
    hmm_x: Optional[List[str]]
    jobs: int

    def _custom_hmms(self) -> Iterable["HMM"]:
        from ...hmmer import HMM

        for path in typing.cast(List[str], self.hmm):
            base = os.path.basename(path)
            file: BinaryIO = open(path, "rb")
            if base.endswith(".gz"):
                base, _ = os.path.splitext(base)
                file = gzip.GzipFile(fileobj=file, mode="rb")   # type: ignore
            base, _ = os.path.splitext(base)
            yield HMM(
                id=base,
                version="?",
                url="?",
                path=path,
                size=None,
                exclusive=False,
                relabel_with=r"s/([^\.]*)(\..*)?/\1/"
            )
        for path in typing.cast(List[str], self.hmm_x):
            base = os.path.basename(path)
            file = open(path, "rb")
            if base.endswith(".gz"):
                base, _ = os.path.splitext(base)
                file = gzip.GzipFile(fileobj=file, mode="rb")   # type: ignore
            base, _ = os.path.splitext(base)
            yield HMM(
                id=base,
                version="?",
                url="?",
                path=path,
                size=None,
                exclusive=True,
                relabel_with=r"s/([^\.]*)(\..*)?/\1/"
            )

    def _annotate_domains(self, genes: List["Gene"], whitelist: Optional[Container[str]] = None) -> List["Gene"]:
        from ...hmmer import PyHMMER, embedded_hmms

        self.info("Running", "HMMER domain annotation", level=1)

        # Run all HMMs over ORFs to annotate with protein domains
        hmms = list(self._custom_hmms() if self.hmm else embedded_hmms())
        task = self.progress.add_task(description=f"Annotating domains", unit="HMMs", total=len(hmms), precision="")
        for hmm in self.progress.track(hmms, task_id=task, total=len(hmms)):
            task = self.progress.add_task(description=f"  {hmm.id} v{hmm.version}", total=hmm.size, unit="domains", precision="")
            callback = lambda h, t: self.progress.update(task, advance=1)
            self.info("Starting", f"annotation with [bold blue]{hmm.id} v{hmm.version}[/]", level=2)
            genes = PyHMMER(hmm, self.jobs, whitelist).run(genes, progress=callback)
            self.success("Finished", f"annotation with [bold blue]{hmm.id} v{hmm.version}[/]", level=2)
            self.progress.update(task_id=task, visible=False)

        # Count number of annotated domains
        count = sum(1 for gene in genes for domain in gene.protein.domains)
        self.success("Found", count, "domains across all proteins", level=1)

        # Filter i-evalue and p-value if required
        genes = self._filter_domains(genes)

        # Sort genes
        self.info("Sorting", "genes by coordinates", level=2)
        genes.sort(key=lambda g: (g.source.id, g.start, g.end))
        for gene in genes:
            gene.protein.domains.sort(key=operator.attrgetter("start", "end"))

        return genes


class PredictorMixin(Command):

    model: Optional[str]
    no_pad: bool
    threshold: float
    postproc: str
    cds: int
    edge_distance: int

    def _predict_probabilities(self, genes: List["Gene"]) -> List["Gene"]:
        from ...crf import ClusterCRF

        if self.model is None:
            self.info("Loading", "embedded CRF pre-trained model", level=1)
        else:
            self.info("Loading", "CRF pre-trained model from", repr(self.model), level=1)
        crf = ClusterCRF.trained(self.model)

        self.info("Predicting", "cluster probabilitites with the CRF model", level=1)
        unit = "genes" if len(genes) > 1 else "gene"
        task = self.progress.add_task("Predicting marginals", total=len(genes), unit=unit, precision="")
        return list(crf.predict_probabilities(
            self.progress.track(genes, task_id=task, total=len(genes)),
            pad=not self.no_pad,
        ))

    def _extract_clusters(self, genes: List["Gene"]) -> List["Cluster"]:
        from ...refine import ClusterRefiner

        self.info("Extracting", "predicted biosynthetic regions", level=1)
        refiner = ClusterRefiner(
            threshold=self.threshold,
            criterion=self.postproc,
            n_cds=self.cds,
            edge_distance=self.edge_distance
        )

        total = len({gene.source.id for gene in genes})
        unit = "contigs" if total > 1 else "contig"
        task = self.progress.add_task("Extracting clusters", total=total, unit=unit, precision="")

        clusters: List["Cluster"] = []
        gene_groups = itertools.groupby(genes, lambda g: g.source.id)  # type: ignore
        for _, gene_group in self.progress.track(gene_groups, task_id=task, total=total):
            clusters.extend(refiner.iter_clusters(list(gene_group)))

        return clusters

    def _load_type_classifier(self) -> "TypeClassifier":
        from ...types import TypeClassifier

        self.info("Loading", "type classifier from internal model", level=2)
        return TypeClassifier.trained(self.model)

    def _predict_types(self, clusters: List["Cluster"], classifier: "TypeClassifier") -> List["Cluster"]:
        from ...model import ProductType

        self.info("Predicting", "BGC types", level=1)

        unit = "cluster" if len(clusters) == 1 else "clusters"
        task = self.progress.add_task("Predicting types", total=len(clusters), unit=unit, precision="")

        clusters_new = []
        for cluster in self.progress.track(clusters, task_id=task):
            clusters_new.extend(classifier.predict_types([cluster]))
            if cluster.type:
                name = "/".join(f"[bold blue]{name}[/]" for name in cluster.type.names)
                prob = "/".join(f"[bold purple]{cluster.type_probabilities[name]:.0%}[/]" for name in cluster.type.names)
                self.success(f"Predicted type of [bold blue]{cluster.id}[/] as {name} ({prob} confidence)")
            else:
                ty = max(cluster.type_probabilities, key=cluster.type_probabilities.get)   # type: ignore
                prob = f"[bold purple]{cluster.type_probabilities[ty]:.0%}[/]"
                name = f"[bold blue]{ty}[/]"
                self.warn(f"Couldn't assign type to [bold blue]{cluster.id}[/] (maybe {name}, {prob} confidence)")

        return clusters_new


# class PredictorMixin(Command):