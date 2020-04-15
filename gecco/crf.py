import csv
import functools
import operator
import math
import multiprocessing.pool
import numbers
import random
import warnings
from typing import List, Optional

import numpy
import pandas
import tqdm
from sklearn.model_selection import PredefinedSplit
from sklearn_crfsuite import CRF

from . import preprocessing
from .cross_validation import LotoSplit, n_folds, n_folds_partial, StratifiedSplit


class ClusterCRF(object):
    """A wrapper for `sklearn_crfsuite.CRF` taking `~pandas.DataFrame` inputs.

    `ClusterCRF` enables prediction and cross-validation for dataframes. This
    is handy to use with feature tables obtained from `~gecco.hmmer.HMMER`. It
    supports arbitrary column names that can be changed on initialisation.
    """

    _EXTRACT_FEATURES_METHOD = {
        "single": "_extract_single_features",
        "group": "_extract_group_features",
        "overlap": "_extract_overlapping_features"
    }

    def __init__(
            self,
            Y_col: Optional[str] = None,
            feature_cols: Optional[List[str]] = None,
            weight_cols=None,
            group_col="protein_id",
            feature_type="single",
            algorithm="lbsgf",
            overlap=2,
            **kwargs
    ) -> None:
        """Create a new `ClusterCRF` instance.

        Arguments:
            Y_col (`str`): The name of the column containing class labels. Must
                be given if the model is going to be trained, but not needed
                when only making predictions.
            feature_cols (list of `str`): The name of the column(s) with
                categorical features.
            weight_cols (list of `str`): The name of the column(s) with
                weights for categorical features. *These are applied locally
                and don't correspond to the actual weights the model learns.*
                See also the `~sklearn_crfsuite.CRFSuite` documentation.
            group_col (str): In case of `feature_type = "group"`,  defines the
                grouping column to use.
            feature_type (str): Defines how features should be extracted. The
                following values are accepted:

                - ``single``: features are extracted on a domain/row level
                - ``overlap``: features are extracted in overlapping windows
                - ``group``: features are extracted in groupings determined
                  by a column in the data frame. *This is most useful when
                  dealing with proteins, but can handle arbitrary grouping
                  levels*.

            algorithm (str): The optimization algorithm for the model. See
                https://sklearn-crfsuite.readthedocs.io/en/latest/api.html
                for available values.
            overlap (int): In case of `feature_type = "overlap"`, defines the
                sliding window size to use.

        Any additional keyword argument is passed as-is to the internal
        `~sklearn_crfsuite.CRF` constructor.
        """
        if feature_type not in self._EXTRACT_FEATURES_METHOD:
            raise ValueError(f"unexpected feature type: {feature_type!r}")

        self.Y_col = Y_col
        self.features = feature_cols or []
        self.weights = weight_cols or []
        self.groups = group_col
        self.feature_type = feature_type
        self.overlap = overlap
        self.algorithm = algorithm
        self.model = CRF(
            algorithm = algorithm,
            all_possible_transitions = True,
            all_possible_states = True,
            **kwargs
        )

    def fit(self, data, threads=None):
        """Fits the model to the given data.

        Arguments:
            data (iterable of `~pandas.DataFrame`): An iterable of data frames
                to use to fit the model. If must contain the following columns
                (as defined on `ClusterCRF` initialisation): *weight_cols*,
                *feature_cols* and *Y_col*, as well as *feature_cols* if the
                feature extraction is ``group``.
            threads (`int`, optional): The number of threads to use when
                extracting the features from the input data.

        """
        X, Y = self._extract_features(data, threads=threads)
        self.model.fit(X, Y)

    def predict_marginals(self, data, threads=None):
        """Predicts marginals for your data.

        Arguments:
            data (iterable of `~pandas.DataFrame`): An iterable of data frames
                to use to fit the model. If must contain the following columns
                (as defined on `ClusterCRF` initialisation): *weight_cols* and
                *feature_cols*, as well as *feature_cols* if the
                feature extraction is ``group``.
            threads (`int`, optional): The number of threads to use when
                extracting the features from the input data.

        """
        # convert data to `CRFSuite` format
        X, _ = self._extract_features(data, threads=threads, X_only=True)

        # Extract cluster (1) probabilities from marginal
        marginal_probs = self.model.predict_marginals(X)
        cluster_probs = [
            numpy.array([d.get("1", 0) for d in sample])
            for sample in marginal_probs
        ]

        # check if any sample has P(1) == 0
        if any(not prob.all() for prob in cluster_probs):
            warnings.warn(
                """
                Cluster probabilities of test set were found to be zero.
                Something may be wrong with your input data.
                """
            )

        # Merge probs vector with the input dataframe. This is tricky if we are
        # dealing with protein features as length of vector does not fit to dataframe
        # To deal with this, we merge by protein_id
        # --> HOWEVER: this requires the protein IDs to be unique among all samples
        if self.feature_type == "group":
            results = [self._merge(df, p_pred=p) for df, p in zip(data, cluster_probs)]
            return pandas.concat(results)
        else:
            return pandas.concat(data).assign(p_pred=numpy.concatenate(cluster_probs))

    # --- Cross-validation ---------------------------------------------------

    def cv(self, data, strat_col=None, k=10, threads=1, trunc=None):
        """Runs k-fold cross-validation using a stratification column.

        Arguments:
            data (`~pandas.DataFrame`): A domain annotation table.
            k (int): The number of cross-validation fold to perform.
            threads (int): The number of threads to use.
            trunc (int, optional): The maximum number of rows to use in the
                training data, or to `None` to use everything.
            strat_col (str, optional): The name of the column to use to split
                the data, or `None` to perform a predefined split.

        Returns:
            `list` of `~pandas.DataFrame`: The list containing one table of
            results for each cross-validation fold.

        Todo:
            * Fix multiprocessing but within `sklearn` to launch each fold in
              a separate `~multiprocessing.pool.ThreadPool`.
            * Make progress bar configurable.
        """
        if strat_col is not None:
            types = [s[strat_col].values[0].split(",") for s in data]
            cv_split = StratifiedSplit(types, n_splits=k)
        else:
            folds = n_folds(len(data), n=k)
            cv_split = PredefinedSplit(folds)

        # Not running in parallel because sklearn has issues managing the
        # temporary files in multithreaded mode
        pbar = tqdm.tqdm(cv_split.split(), total=k, leave=False)
        return [
             self._single_fold_cv(
                data,
                train_idx,
                test_idx,
                round_id=f"fold{i}",
                trunc=trunc,
                threads=threads
            )
            for i, (train_idx, test_idx) in enumerate(pbar)
        ]

    def loto_cv(self, data, strat_col, threads=1, trunc=None):
        """Run LOTO cross-validation using a stratification column.

        Arguments:
            data (`~pandas.DataFrame`): A domain annotation table.
            strat_col (str): The name of the column to use to split the data.
            threads (int): The number of threads to use.
            trunc (int, optional): The maximum number of rows to use in the
                training data, or to `None` to use everything.

        Returns:
            `list` of `~pandas.DataFrame`: The list containing one table for
            each cross-validation fold.

        Todo:
            * Fix multiprocessing but within `sklearn` to launch each fold in
              a separate `~multiprocessing.pool.ThreadPool`.
            * Make progress bar configurable.
        """
        labels = [s[strat_col].values[0].split(",") for s in data]
        cv_split = LotoSplit(labels)

        # Not running in parallel because sklearn has issues managing the
        # temporary files in multithreaded mode
        pbar = tqdm.tqdm(list(cv_split.split()), leave=False)
        return [
            self._single_fold_cv(data, train_idx, test_idx, label, trunc)
            for train_idx, test_idx, label in pbar
        ]

    def _single_fold_cv(self, data, train_idx, test_idx, round_id=None, trunc=None, threads=None):
        """Performs a single CV round with the given indices.
        """
        # Extract the fold from the complete data using the provided indices
        train_data = [data[i].reset_index() for i in train_idx]
        if trunc is not None:
            # Truncate training set from both sides to desired length
            train_data = [
                preprocessing.truncate(df, trunc, self.Y_col, self.groups)
                for df in train_data
            ]

        # Fit the model
        self.fit(train_data, threads=threads)

        # Predict marginals on test data and return predictions
        test_data = [data[i].reset_index() for i in test_idx]
        marginals = self.predict_marginals(data=test_data, threads=threads)
        return marginals.assign(cv_round=round_id)

    # --- Feature extraction -------------------------------------------------

    def _currify_extract_function(self, X_only=False):
        if self.feature_type == "group":
            extract = functools.partial(
                preprocessing.extract_group_features,
                group_cols=self.groups,
            )
        elif self.feature_type == "single":
            extract = preprocessing.extract_single_features
        elif self.feature_type == "overlap":
            extract = functools.partial(
                preprocessing.extract_overlapping_features,
                overlap=self.overlap
            )
        else:
            raise ValueError(f"invalid feature type: {self.feature_type!r}")
        return functools.partial(
            extract,
            feature_cols=self.features,
            weight_cols=self.weights,
            Y_col=None if X_only else self.Y_col,
        )

    def _extract_features(self, data, threads=None, X_only=False):
        """Convert a data list to `CRF`-compatible wrappers.

        Arguments:
            data (`list` of `~pandas.DataFrame`): A list of samples to
                extract features and class labels from.
            threads (`int`, optional): The number of parallel threads to
                launch to extract features.
            X_only (`bool`, optional): If `True`, only return the features,
                and ignore class labels.

        Warning:
            This method spawns a `multiprocessing.pool.Pool` in the background
            to extract features in parallel.
        """
        # Filter the columns to reduce the amount of data passed to the
        # different processes
        columns = self.features + [self.groups]
        columns.extend(filter(lambda w: isinstance(w, str), self.weights))
        if not X_only:
            columns.append(self.Y_col)
        col_filter = operator.itemgetter(columns)
        # Extract features to CRFSuite format
        _extract = self._currify_extract_function(X_only=X_only)
        with multiprocessing.pool.Pool(threads) as pool:
            samples = pool.map(_extract, map(col_filter, data))
            X = numpy.array([x for x, _ in samples])
            Y = numpy.array([y for _, y in samples])
        # Only return Y if requested
        return X, None if X_only else Y

    # --- Utils --------------------------------------------------------------

    def _merge(self, df, **cols):
        unidf = pandas.DataFrame(cols)
        unidf[self.groups] = df[self.groups].unique()
        return df.merge(unidf)

    def save_weights(self, basename: str) -> None:
        with open(f"{basename}.trans.tsv", "w") as f:
            writer = csv.writer(f, dialect="excel-tab")
            writer.writerow(["from", "to", "weight"])
            for labels, weight in self.model.transition_features_.items():
                writer.writerow([*labels, weight])
        with open(f"{basename}.state.tsv", "w") as f:
            writer = csv.writer(f, dialect="excel-tab")
            writer.writerow(["attr", "label", "weight"])
            for attrs, weight in self.model.state_features_.items():
                writer.writerow([*attrs, weight])
