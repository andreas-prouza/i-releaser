from __future__ import annotations
import os, logging

from etc import constants
from modules import meta_file as mf, stages as s
from modules import deploy_action as da


def pre_cmd(meta_file: mf.Meta_File, stage_obj: s.Stage, action: da.Deploy_Action) -> None:
    """
     RSTLIB SAVLIB(PROUZALIB) DEV(*SAVF) SAVF(QGPL/PROUZASAVF) RSTLIB(RSTLIB)
            SELECT((*INCLUDE TEST *PGM) (*INCLUDE TEST *FILE)) 
    """

    logging.info(f"This is a user defined pre function: {meta_file.file_name=}, {stage_obj.get_dict()=}, {action.get_dict()=}")