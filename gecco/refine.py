import pandas as pd
import numpy as np
from gecco.bgc import Protein, BGC

class ClusterRefiner(object):

    def __init__(self, threshold=0.4, lower_thresh=0.3, biosynthetic_pfams=5,
            seq_col="sequence_id", prot_col="protein_id",
            p_col="p_pred", domain_col="pfam", weight_col="log_i_Evalue",
            min_domains=1, min_proteins=5, join_width=1):

        self.thresh = threshold
        self.lower_thresh = lower_thresh
        self.n_biopfams = biosynthetic_pfams
        self.n_domains = min_domains
        self.n_proteins = min_proteins
        self.n_proteins = min_proteins
        self.join_width = join_width
        self.seq_col = seq_col
        self.prot_col = prot_col
        self.domain_col = domain_col
        self.weight_col = weight_col
        self.p_col = p_col
        self.grouping = [seq_col, prot_col]

    def find_clusters(self, pfam_df, method="gecco", prefix="cluster"):
        self.prefix = prefix
        if method == "antismash":
            self.lower_thresh = 0.3
            clusters = self._antismash_refine(pfam_df)
            return clusters
        if method == "gecco":
            self.lower_thresh = self.thresh
            clusters = self._gecco_refine(pfam_df)
            return clusters


    def _gecco_refine(self, dataframe):
        """
        So far, this implements a very basic extraction procedure:
        1) Extract segments with p_pred > self.thresh
        ...thats it.
        """
        bgc_list = []
        segments = self.extract_segments(dataframe)
        if not segments:
            return
        for seg in segments:
            bgc = self._extract_cluster(dataframe, seg)
            bgc_list.append(bgc)

        return bgc_list



    def _antismash_refine(self, dataframe):
        """
        This method reimplements the way ClusterFinder hits are refined and
        extracted in antiSMASH:
        1) Extract segments with p_pred > 0.3 (lower_thresh)
        2) Find the proteins spanning this segment
        3) Validate if cluster meets criteria
        """

        bgc_list = []
        segments = self.extract_segments(dataframe)
        if not segments:
            return
        for seg in segments:
            bgc = self._extract_cluster(dataframe, seg)
            if bgc.is_valid(criterion="antismash"):
                bgc_list.append(bgc)

        return bgc_list

    def _extract_cluster(self, dataframe, segment):
        """Takes a DataFrame and a segement and returns a BGC object"""
        cluster_name = segment["cluster_id"].values[0]
        cluster_prots = set(segment[self.prot_col])
        cluster_df = dataframe.loc[dataframe[self.prot_col].isin(cluster_prots)]
        prot_list = []
        for pid, subdf in segment.groupby(self.prot_col, sort=False):
            protein = Protein(
                seq_id = subdf[self.seq_col].values[0],
                start = subdf["start"].min(),
                end = subdf["end"].max(),
                name = pid,
                domains = subdf.get(self.domain_col),
                weights = subdf.get(self.weight_col),
                p = subdf.get(self.p_col)
            )
            prot_list.append(protein)

        return BGC(prot_list, name=cluster_name)

    def extract_segments(self, df):
        """
        Extracts segments from a data frame which are determined by p_col.
        Segments are named with prefix_[cluster_number].
        """
        cluster_num = 1
        cluster_state = False
        cluster_list = []
        for n in range(len(df)):
            row = df.iloc[n]
            if row[self.p_col] >= self.lower_thresh:
                # non-cluster -> cluster
                if not cluster_state:
                    cluster_name = f"{row[self.seq_col]}_cluster_{str(cluster_num)}"
                    row = (pd.DataFrame(row)
                        .transpose())
                    cluster_start = row["start"]
                    cluster_df = row
                    cluster_state = True
                # cluster -> cluster
                else:
                    cluster_df = cluster_df.append(row)
                    # Check if last row
                    if n == range(len(df))[-1]:
                        cluster_list.append(
                            cluster_df.assign(idx=n, cluster_id=cluster_name)
                        )
            else:
                # cluster -> non-cluster
                if cluster_state:
                    cluster_list.append(
                        cluster_df.assign(idx=n, cluster_id=cluster_name)
                    )
                    cluster_num += 1
                    cluster_state = False
                # non-cluster -> non-cluster
                # pass

        if len(cluster_list) > 0:
            return cluster_list
        else:
            return


    def segment(self, df):
        """
        Determines coordinates of segments determined by p_col over
        a lower_thresh.
        """
        cluster_num = 1
        cluster_state = False
        cluster_list = []
        for n in range(len(df)):
            row = df.iloc[n]
            if row[self.p_col] >= self.lower_thresh:
                # non-cluster -> cluster
                if not cluster_state:
                    cluster_dict = {}
                    cluster_dict[self.seq_col] = row[self.seq_col]
                    cluster_dict["cluster_id"] = self.prefix + "_" + str(cluster_num)
                    cluster_dict["start"] = min(row["start"], row["end"])
                    cluster_state = True
                # cluster -> cluster
                # pass
            else:
                # cluster -> non-cluster
                if cluster_state:
                    cluster_dict["end"] = max(row["start"], row["end"])
                    cluster_list.append(cluster_dict)
                    cluster_num += 1
                    cluster_state = False
                # non-cluster -> non-cluster
                # pass
        return pd.DataFrame(cluster_list)