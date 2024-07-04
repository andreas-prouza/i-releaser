from __future__ import annotations
import os

from etc import constants
from modules import meta_file as mf, stages as s
from modules import deploy_action as da


def set_cmd_transfer_to_target(meta_file: mf.Meta_File, stage_obj: s.Stage, processing_step: str) -> None:
    """Transfer all SAVFs to the target system

    Args:
        stage (str): _description_
    Example:
        scp -rp /dir/deployment1 target_server:~/also-a-dir
    """

    actions = stage_obj.actions
    deployment_dir = os.path.dirname(os.path.realpath(meta_file.file_name))

    cmd = f"scp -rp {deployment_dir} {stage_obj.host}:{stage_obj.base_dir}"
    actions.add_action_cmd(
        cmd=cmd,
        environment=da.Command_Type.PASE,
        processing_step=processing_step,
        stage=stage_obj.name,
    )
