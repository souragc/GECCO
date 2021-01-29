<img align="left" width="100" height="100" src="static/gecco-square.png">

# Hi, I'm GECCO!

[![GitLabCI](https://img.shields.io/gitlab/pipeline/grp-zeller/GECCO/master?gitlab_url=https%3A%2F%2Fgit.embl.de&logo=gitlab&style=flat-square&maxAge=600)](https://git.embl.de/grp-zeller/GECCO)
[![License](https://img.shields.io/badge/license-GPLv3-blue.svg?style=flat-square&maxAge=2678400)](https://choosealicense.com/licenses/gpl-3.0/)
[![Source](https://img.shields.io/badge/source-GitHub-303030.svg?maxAge=2678400&style=flat-square)](https://github.com/zellerlab/GECCO/)
[![Mirror](https://img.shields.io/badge/mirror-EMBL-009f4d?style=flat-square&maxAge=2678400)](https://git.embl.de/grp-zeller/GECCO/)
[![Changelog](https://img.shields.io/badge/keep%20a-changelog-8A0707.svg?maxAge=2678400&style=flat-square)](https://github.com/zellerlab/GECCO/blob/master/CHANGELOG.md)
<!-- [![Coverage](https://img.shields.io/codecov/c/gh/zellerlab/GECCO?style=flat-square&maxAge=3600)](https://codecov.io/gh/zellerlab/GECCO/) -->
<!-- [![PyPI](https://img.shields.io/pypi/v/GECCO.svg?style=flat-square&maxAge=3600)](https://pypi.org/project/gecco-bgc) -->
<!-- [![Wheel](https://img.shields.io/pypi/wheel/GECCO.svg?style=flat-square&maxAge=3600)](https://pypi.org/project/gecco-bgc/#files) -->
<!-- [![Python Versions](https://img.shields.io/pypi/pyversions/gecco-bgc.svg?style=flat-square&maxAge=3600)](https://pypi.org/project/gecco-bgc/#files) -->
<!-- [![GitHub issues](https://img.shields.io/github/issues/zellerlab/GECCO.svg?style=flat-square&maxAge=600)](https://github.com/zellerlab/GECCO/issues) -->
<!-- [![Docs](https://img.shields.io/readthedocs/gecco/latest?style=flat-square&maxAge=600)](https://gecco.readthedocs.io) -->
<!-- [![Downloads](https://img.shields.io/badge/dynamic/json?style=flat-square&color=303f9f&maxAge=86400&label=downloads&query=%24.total_downloads&url=https%3A%2F%2Fapi.pepy.tech%2Fapi%2Fprojects%2Fgecco)](https://pepy.tech/project/GECCO) -->


## 🦎 ️Overview

GECCO (Gene Cluster prediction with Conditional Random Fields) is a fast and
scalable method for identifying putative novel Biosynthetic Gene Clusters (BGCs)
in genomic and metagenomic data using Conditional Random Fields (CRFs).


## 🔧 Installing GECCO

GECCO is implemented in [Python](https://www.python.org/), and supports [all
versions](https://endoflife.date/python) from Python 3.6. It requires
additional libraries that can be installed directly from
PyPI, the Python Package Index.

Use `pip` to install GECCO on your machine:
```console
$ pip install https://github.com/zellerlab/GECCO/archive/master.zip
```

This will download GECCO, its dependencies, and the data needed to run
predictions. Once done, you will have a ``gecco`` command in your $PATH.

*Note that GECCO uses [HMMER3](http://hmmer.org/), which can only run
on PowerPC and and recent x86-64 machines running a POSIX operating system.
Therefore, Linux and OSX are supported platforms, but GECCO will not be able
to run on Windows.*


## 🧬 Running GECCO

Once `gecco` is installed, you can run it from the terminal by giving it a
FASTA or GenBank file with the genomic sequence you want to analyze, as
well as an output directory:

```console
$ gecco run --genome some_genome.fna -o some_output_dir
```

Additional parameters of interest are:

- `--jobs`, which controls the number of threads that will be spawned by
  GECCO whenever a step can be parallelized. The default, *0*, will
  autodetect the number of CPUs on the machine using
  [`multiprocessing.cpu_count`](https://docs.python.org/3/library/multiprocessing.html#multiprocessing.cpu_count).
- `--cds`, controlling the minimum number of consecutive genes a BGC region
  must have to be detected by GECCO (default is 3).
- `--threshold`, controlling the minimum probability for a gene to be
  considered part of a BGC region. Using a lower number will increase the
  number (and possibly length) of predictions, but reduce accuracy.

<!-- ## 📖 Documentation -->

## 💭 Feedback

### ⚠️ Issue Tracker

Found a bug ? Have an enhancement request ? Head over to the [GitHub issue
tracker](https://github.com/zellerlab/GECCO/issues) if you need to report
or ask something. If you are filing in on a bug, please include as much
information as you can about the issue, and try to recreate the same bug
in a simple, easily reproducible situation.

### 🏗️ Contributing

Contributions are more than welcome! See [`CONTRIBUTING.md`](https://github.com/althonos/pyhmmer/blob/master/CONTRIBUTING.md)
for more details.

## ⚖️ License

This software is provided under the [GNU General Public License v3.0 *or later*](https://choosealicense.com/licenses/gpl-3.0/). GECCO is developped by the [Zeller Team](https://www.embl.de/research/units/scb/zeller/index.html)
at the [European Molecular Biology Laboratory](https://www.embl.de/) in Heidelberg.
