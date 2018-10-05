import sys
import os
import warnings
warnings.filterwarnings("ignore", message="numpy.dtype size changed")
warnings.filterwarnings("ignore", message="numpy.ufunc size changed")
GECCO = os.path.abspath(os.path.dirname(os.path.abspath(sys.argv[0])) + "/..")
sys.path.append(GECCO)
import random
import argparse
import pandas as pd
import numpy as np
import multiprocessing
from gecco.crf import ClusterCRF
from gecco.interface import scripts_interface
from gecco.utils import coerce_numeric

### TEST ###
# python /home/fleck/bin/gecco/scripts/gecco_loto.py /home/fleck/scripts/clust/test/test.embed.tsv -o /home/fleck/scripts/clust/test/test

# MAIN
if __name__ == "__main__":
    args = scripts_interface()

    data = args.DATA
    data_base = data.split("/")[-1].split(".")[0]
    out_file = args.out

    threads = args.threads
    if not threads:
        threads = multiprocessing.cpu_count()

    C1 = args.C1
    C2 = args.C2
    weight_col = [coerce_numeric(w) for w in args.w]
    y_col = args.y
    feature_col = args.feat
    group_col = args.group_col
    strat_col = args.strat_col
    split_col = args.split_col
    trunc = args.truncate
    shuffle = args.shuffle
    feature_type = args.feature_type
    overlap = args.overlap
    e_filter = args.e_filter

    print(args)

    data_tbl = pd.read_csv(data, sep="\t", encoding="utf-8")
    data_tbl = data_tbl[data_tbl["i_Evalue"] < e_filter]
    data_tbl = data_tbl.assign(
        domain = data_tbl["domain"].str.replace(r"(PF\d+)\.\d+", lambda m: m.group(1))
    )
    data_tbl = [s for _, s in data_tbl.groupby(split_col)]
    if shuffle:
        random.shuffle(data_tbl)

    crf = ClusterCRF(
        Y_col = y_col,
        feature_cols = feature_col,
        weight_cols = weight_col,
        feature_type = feature_type,
        weights_prefix = f"{out_file}_loto",
        overlap = overlap,
        algorithm = "lbfgs",
        c1 = C1,
        c2 = C2
    )

    # crf = ClusterCRF(
    #     Y_col = y_col,
    #     feature_cols = feature_col,
    #     weight_cols = weight_col,
    #     feature_type = feature_type,
    #     overlap = overlap,
    #     algorithm = "l2sgd",
    #     c2 = C2
    # )

    results = crf.loto_cv(
        data_tbl,
        type_col = strat_col,
        threads = threads,
        trunc = trunc
    )

    result_df = (pd .concat(results)
                    .assign(c1 = C1,
                        c2 = C2,
                        feature_type = feature_type,
                        e_filter = e_filter,
                        overlap = overlap,
                        weight = ",".join(map(str, weight_col)),
                        feature = ",".join(feature_col),
                        truncate = trunc,
                        in_file = data_base,
                        cv_type = "LOTO")
                    .loc[ : , ["BGC", "BGC_id", "protein_id", "domain", "idx",
                        "p_pred", "c1", "c2", "feature_type", "e_filter", "overlap",
                        "weight", "truncate", "cv_type", "cv_round", "in_file"] ])

    # print(result_df)

    # Write results
    ext = "_loto" + ".pred.tsv"
    result_df.to_csv(out_file + ext, sep="\t", index=False, header=False)