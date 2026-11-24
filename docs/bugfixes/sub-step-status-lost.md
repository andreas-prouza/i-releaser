# A finished parallel sub-step can stay `in process`

- **Status:** finished (2026-11-24; tested with `tests/test_parallel_steps.py`, not on IBM i)
- **Type:** bug
- **Priority:** P2
- **Found:** 2026-11-24, by the test `test_sub_steps_are_stored_once` which failed once in five parallel runs of the whole test suite (30 sub-steps of a script, 8 at the same time)


## Current situation (before)

A `SCRIPT` step adds sub-steps (e.g. one per library) and runs them in a [parallel group](../workflow.md#parallel-steps). A new sub-step isn't in the database yet: when it ends, its thread saves the whole deployment (`Meta_File.save`), which inserts all new sub-steps, also the ones which still run in other threads.

`actions_data._add_action` ([actions_data.py](../../modules/db/actions_data.py)) read the values of a step twice: once for the `INSERT`, and once afterwards as the saved values (`saved_values`, the base of the next save, see [lost updates on save](lost-updates-on-save.md)). When a sub-step ended between the two reads (in its own thread):

1. the `INSERT` stored it `in process`;
2. the saved values said `finished`;
3. the next save of the sub-step (`save_step` by its own thread) found no change and wrote nothing.

The sub-step stayed `in process` in the database for good, although it had finished: the deployment page showed it as running, `Continue` ran it again.


## Requirements

1. The values which are inserted are the saved values (one snapshot). A change after the snapshot is written by the next save.


## Acceptance criteria

- [x] Test: a sub-step which ends while another thread inserts it is stored `finished` after the save of its own thread (`test_sub_step_which_ends_while_it_is_inserted_is_stored_finished`: an SQLite trace callback ends the sub-step exactly during its `INSERT`; it failed before the fix every time).
- [x] The tests of the parallel steps pass, also in the parallel run of the whole suite.


## Decisions (2026-11-24)

* Only `_add_action` had the second read. The other places take the snapshot right after an object is loaded from the database, before another thread can see the object. The run history of a step is inserted by its own thread and remembers no values, so the next save writes all its columns.
* `save_action_status` (`in process` at the start of a step) runs outside of the lock of the saves. It can only write `in process` before the step's own end is saved, and its change of the saved values can only cause one more write: not changed.
