#!/usr/bin/env python

#########################################################################################
#                                                                                       #
#                                           ORION                                       #
#                           predicting biosynthetic gene clusters                       #
#                              using conditional random fields                          #
#                                                                                       #
#                                       MAIN SCRIPT                                     #
#                                                                                       #
#   Author: Jonas Simon Fleck (jonas.simon.fleck@gmail.com)                             #
#                                                                                       #
#########################################################################################

import os
import sys
import pickle
import argparse
import warnings
import subprocess
warnings.filterwarnings("ignore", message="numpy.dtype size changed")
warnings.filterwarnings("ignore", message="numpy.ufunc size changed")
import numpy as np
import pandas as pd
from orion.hmmer import HMMER
from orion.orf import ORFFinder
from orion.crf import ClusterCRF
from orion.knn import ClusterKNN
from orion.refine import ClusterRefiner
from orion.interface import main_interface

# CONST
SCRIPT_DIR = os.path.abspath(os.path.dirname(os.path.abspath(sys.argv[0])))
PFAM = open(os.path.join(SCRIPT_DIR, "data/db_config.txt")).readlines()[0].strip()
MODEL = os.path.join(SCRIPT_DIR, "data/model/f5_eval_p_t50.crf.model")
TRAINING_MATRIX = os.path.join(SCRIPT_DIR, "data/knn/domain_composition.tsv")
LABELS = os.path.join(SCRIPT_DIR, "data/knn/type_labels.tsv")

# MAIN
if __name__ == "__main__":

    # PARAMS
    args = main_interface()
    log_file = args.log
    sys.stderr = log_file

    log_file.write("Running ORION with these parameters:" + "\n")
    log_file.write(str(args) + "\n")

    fasta = args.FASTA
    base = ".".join(os.path.basename(fasta).split(".")[:-1])

    out_dir = args.out
    if not os.path.exists(out_dir):
        os.makedirs(out_dir)

    e_filter = min(1, args.e_filter)
    threads = args.threads
    if not threads:
        threads = multiprocessing.cpu_count()


    # PRODIGAL
    log_file.write("Running ORF prediction using PRODIGAL..." + "\n")

    prodigal_out = os.path.join(out_dir, "prodigal/")
    if not os.path.exists(prodigal_out):
        os.makedirs(prodigal_out)

    prodigal = ORFFinder(fasta, prodigal_out, method="prodigal")
    orf_file = prodigal.run()


    # HMMER
    log_file.write("Running Pfam domain annotation..." + "\n")

    hmmer_out = os.path.join(out_dir, "hmmer/")
    if not os.path.exists(hmmer_out):
        os.makedirs(hmmer_out)

    hmmer = HMMER(orf_file, hmmer_out, hmms=PFAM)
    pfam_df = hmmer.run()

    # Filter i-Evalue
    pfam_df = pfam_df[pfam_df["i_Evalue"] < e_filter]
    pfam_df["protein_id"] = pd.Categorical(
                pfam_df["protein_id"], pfam_df["protein_id"].unique())

    # Write feature table to file
    feat_out = os.path.join(out_dir, base + ".features.tsv")
    pfam_df.to_csv(feat_out, sep="\t", index=False)


    # CRF
    log_file.write("Running cluster prediction..." + "\n")

    with open(MODEL, "rb") as f:
        crf = pickle.load(f)

    ### TEMPORARY HACK, HAVE TO REPLACE MODEL ###
    crf.weights = [1]
    #############################################

    pfam_df = [pfam_df]
    pfam_df = crf.predict_marginals(data=pfam_df)

    # Write predictions to file
    pred_out = os.path.join(out_dir, base + ".pred.tsv")
    pfam_df.to_csv(pred_out, sep="\t", index=False)


    # REFINE
    log_file.write("Extracting and refining clusters..." + "\n")

    refiner = ClusterRefiner(threshold=args.thresh)
    clusters = refiner.find_clusters(
        pfam_df,
        method = args.post,
        prefix = base
    )

    del pfam_df

    if not clusters:
        log_file.write("Unfortunately, no clusters were found. Exiting now.")
        sys.exit()


    # KNN
    log_file.write("Running cluster type prediction..." + "\n")

    ### This part should go into ClusterKNN object ###
    train_df = pd.read_csv(TRAINING_MATRIX, sep="\t", encoding="utf-8")
    train_comp = train_df.iloc[:,1:].values
    id_array = train_df["BGC_id"].values
    pfam_array = train_df.columns.values[1:]

    types_df = pd.read_csv(LABELS, sep="\t", encoding="utf-8")
    types_array = types_df["cluster_type"].values
    subtypes_array = types_df["subtype"].values

    new_comp = np.array(
        [c.domain_composition(all_possible=pfam_array) for c in clusters]
    )
    ##################################################

    knn = ClusterKNN(metric=args.dist, n_neighbors=args.k)
    knn_pred = knn.fit_predict(train_comp, new_comp, y=types_array)

    cluster_out = os.path.join(out_dir, base + ".clusters.tsv")
    with open(cluster_out, "wt") as f:
        for c, t in zip(clusters, knn_pred):
            c.type = t
            c.write_to_file(f)

    log_file.write("DONE." + "\n")
