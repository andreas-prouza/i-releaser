from __future__ import annotations
import os, logging

from etc import constants
from modules import meta_file as mf
from modules import deploy_action as da
from scripts import save_objects, target_prepare, transfer, backup_old_objects, target_deployment


def generate_commands(meta_file: mf.Meta_File, stage: str, processing_step:str) -> None:

  processing_steps = meta_file.stages.get_stage(stage).processing_steps

  steps_cmd = {
    'prepare-save': [
      save_objects.set_init_cmds_for_save,
    ],
    'save': [
      save_objects.set_cmd_object_to_savf
    ],
    'transfer': [
      transfer.set_cmd_transfer_to_target
    ],
    'target-prepare': [
        target_prepare.set_init_cmds_for_deployment
      ],
    'backup-old-objects': [
      backup_old_objects.set_cmd_backup_objects_on_target
    ],
    'perform-deployment': [
      target_deployment.set_cmd_restore_objects_on_target
    ]
  }

  for step in steps_cmd:

    # Check if step from steps_cmd is in processing_step list of given stage
    if step not in processing_steps:
      logging.info(f"Step {step} not in list of steps")
      continue

    # Execute the commands of this step
    for cmd in steps_cmd[step]:
      logging.info(f"Execute cmd {cmd} of step {step} (stage {stage})")
      cmd(meta_file, stage, step)



