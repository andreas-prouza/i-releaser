# Version numbers of deployments have gaps and can collide

- **Status:** finished
- **Type:** bug
- **Priority:** P2
- **Found:** 2026-10-23, code review


## Current situation

`get_next_deploy_version` ([deploy_version.py:26](../../modules/deploy_version.py#L26)) uses

```sql
SELECT MAX(id) FROM deploy_versions WHERE project = ?
```

`id` is the global key over all projects, not the version. With more than one project, versions jump (e.g. project A: 1, 2, 3, then 7).

`SELECT` and `INSERT` don't run in one write transaction. Two deployments of the same project created at the same time
(e.g. in two gunicorn workers) get the same version, and one of them fails because of `UNIQUE(project, version)`.


## Requirements

1. The next version of a project is the highest version of that project + 1.
2. Reading the highest version and inserting the new one is atomic (e.g. `BEGIN IMMEDIATE`), also across processes.
3. Existing versions aren't changed.


## Acceptance criteria

- [x] Unit test: deployments of two projects created alternately → each project gets 1, 2, 3, ...
- [x] Unit test: 10 deployments of one project created in parallel (threads or processes) → 10 different, consecutive versions, no error.
- [x] Unit test: with existing versions 1, 2, 7, the next one is 8.


## Non-goals

* Renumbering existing deployments
