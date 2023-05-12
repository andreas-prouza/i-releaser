from __future__ import annotations
import os

from etc import constants
from modules import meta_file as mf
from modules import deploy_action as da


def pre_cmd(meta_file: mf.Meta_File, stage: str, processing_step: str) -> None:
    """
     RSTLIB SAVLIB(PROUZALIB) DEV(*SAVF) SAVF(QGPL/PROUZASAVF) RSTLIB(RSTLIB)
            SELECT((*INCLUDE TEST *PGM) (*INCLUDE TEST *FILE)) 
    """

    print(f"This is a user defined pre function: {meta_file.file_name} in stage '{stage}, processing step {processing_step}'")