from __future__ import annotations
import os

from etc import constants
from modules import meta_file as mf
from modules import deploy_action as da


def set_cmd_transfer_to_target(meta_file: mf.Meta_File, stage: str) -> None:
    """Transfer all SAVFs to the target system

    Args:
        stage (str): _description_
    Example:
        scp -rp /dir/deployment1 target_server:~/also-a-dir
    """

    current_stage = meta_file.current_stages.get_stage(stage)
    actions = meta_file.actions
    deployment_dir = os.path.dirname(os.path.realpath(meta_file.file_name))

    cmd = f"scp -rp {deployment_dir} {current_stage.host}:{current_stage.base_dir}"
    actions.add_action_cmd(
        cmd=cmd,
        environment=da.Command_Type.PASE,
        processing_step=da.Processing_Step.TRANSFER,
        stage=stage,
    )
