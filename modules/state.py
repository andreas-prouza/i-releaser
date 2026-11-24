"""
The allowed changes of a status (docs/features/core-redesign.md, step 1).

A status is only changed by a transition: one conditional statement in the database
(`UPDATE … SET status = ? WHERE id = ? AND status IN (<allowed from>)`). A run whose copy of the deployment is outdated,
or another process, can't overwrite a newer status: the transition fails and the caller gets the current status.
A change to the same status is always allowed (e.g. a stage which is claimed is set to `in process` again).
"""
from modules.job_status import Status as Job_Status
from modules.meta_file_status import Meta_file_status as Deployment_Status
from modules.stage_status import Status as Stage_Status


# to -> the statuses it can be reached from
STAGE: dict[Stage_Status, set[Stage_Status]] = {
    # The previous stage is finished (activate_stage), or it has been reset (reset_last_finished_stage)
    Stage_Status.READY: {Stage_Status.NEW, Stage_Status.IN_PROCESS, Stage_Status.FINISHED},
    # Run (claim_stage), also again after a failed run
    Stage_Status.IN_PROCESS: {Stage_Status.READY, Stage_Status.FAILED},
    Stage_Status.FINISHED: {Stage_Status.IN_PROCESS},
    Stage_Status.FAILED: {Stage_Status.IN_PROCESS},
    # The previous stage has been reset
    Stage_Status.NEW: {Stage_Status.READY, Stage_Status.FAILED},
}


DEPLOYMENT: dict[Deployment_Status, set[Deployment_Status]] = {
    Deployment_Status.READY: {Deployment_Status.NEW, Deployment_Status.IN_PROCESS, Deployment_Status.FAILED},
    Deployment_Status.IN_PROCESS: {Deployment_Status.READY, Deployment_Status.FAILED},
    Deployment_Status.FAILED: {Deployment_Status.READY, Deployment_Status.IN_PROCESS},
    # A deployment is finished once (claim_finished) and then canceled never
    Deployment_Status.FINISHED: {Deployment_Status.NEW, Deployment_Status.READY, Deployment_Status.IN_PROCESS, Deployment_Status.FAILED},
    Deployment_Status.CANCELED: {Deployment_Status.NEW, Deployment_Status.READY, Deployment_Status.IN_PROCESS, Deployment_Status.FAILED},
}


JOB: dict[Job_Status, set[Job_Status]] = {
    Job_Status.RUNNING: {Job_Status.QUEUED},
    Job_Status.FINISHED: {Job_Status.QUEUED, Job_Status.RUNNING},
    Job_Status.FAILED: {Job_Status.QUEUED, Job_Status.RUNNING},
    Job_Status.CANCELED: {Job_Status.QUEUED},
}


# The statuses in which a stage runs. The only place which defines them.
STAGE_RUNNING = [Stage_Status.IN_PROCESS, Stage_Status.IN_PREPERATION, Stage_Status.PREPARE]

# A stage in one of these statuses can be run
STAGE_RUNNABLE = [Stage_Status.READY, Stage_Status.FAILED]

DEPLOYMENT_ENDED = [Deployment_Status.FINISHED, Deployment_Status.CANCELED]



def allowed_from(table: dict, to) -> list[str]:
    """The values (text) of the statuses from which `to` can be reached, including `to` itself"""

    return sorted({to.value, *(status.value for status in table.get(to, set()))})



def is_allowed(table: dict, current, to) -> bool:
    return current == to or current in table.get(to, set())
