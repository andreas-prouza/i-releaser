# Execute processing steps in parallel

- **Status:** ready (Implemented. Open: the first run of `scripts/obi.py` on an IBM i, it was only tested with a simulated `cl`.)
- **Type:** improvement


## Current situation

* All steps are executed in sequence
* The order is defined by sequence number


## Requirements

1. I want to define:
   * a group name for processing steps
   * an atribute to define parallel processing within the group name


## Acceptance criteria

- In `scripts/obi.py`, when I call `ibm_i_commands.execute_action`, i-Release checks if parallel processing is set and starts processing async
- All parallel steps are executed in async as long as the first step with no parallel definition is defined or the group name is a different one
- When executing a further processing step without parallel attribute or another grup name, i-Releaser should wait until all executing jobs are finished before execution of next processing step


## Non-goals



## Decisions

* **Where it's defined:** `parallel_group` and `parallel` are attributes of `Deploy_Action`. `execute_action` treats sub-steps and normal steps the same. Normal steps get them from their `step_action` entry, like `fail_on_stderr`.
* **Failure of a parallel step with `check_error`:** steps which are running end normally, steps which haven't started stay `new`, then the stage fails.
* **Limit:** `C_MAX_PARALLEL_STEPS` (default 4) steps per running group. Further steps of the group wait for a free slot.
* **Scripts which depend on the result:** `execute_action` returns before a parallel step has ended, and its failure isn't raised at that line anymore. `wait_for_parallel_actions()` waits for the running steps and raises if one failed. `perform_deployment` uses it per object level.
* **Technology:** threads of the standard library, see [technik.md](../technik.md#parallel-steps).
* **Web app:** no change. It doesn't show the group of a step, and a running step is shown as `new` until it has ended, like before.

