# Object list: any file on the server can be given

- **Status:** finished
- **Type:** security
- **Priority:** P3
- **Found:** 2026-10-23, code review
- **Confidential:** don't publish before the fix is released


## Current situation

`GET /api/create_deployment/{wf_name}/{commit}/{obj_list}` (or `?obj_list=`) stores a path on the server as object list.
The step `load_object_list` reads that file ([meta_file.py:933](../../modules/meta_file.py#L933)), whatever directory it's in.

* A user with `start workflow` can make i-Releaser read any file its user profile can read.
* A line which isn't an object (e.g. of `/etc/passwd`) fails at `int(...)`, and the error message (in the step log) contains the beginning of the line.
* The file has to be on the i-Releaser server. The API gives no way to upload an object list.


## Requirements

1. The object list has to be in an allowed directory: the `build_dir` of the workflow's stages, or a configured directory (e.g. `C_OBJECT_LIST_DIRS`). Paths are resolved (`realpath`) before the check.
2. Invalid lines are reported with their line number, not their content.
3. Optional: the object list can be sent in the body of the request (see open questions).


## Acceptance criteria

- [x] Unit test: `/etc/passwd`, `../../x` and a symlink out of the allowed directory are rejected when the deployment is created.
- [x] Unit test: a list in the `build_dir` is imported as before.
- [x] Unit test: an invalid line gives `line 3 is invalid` without its content.


## Non-goals

* Changing the format of the object list


## Decisions

* Upload of the list through the API? **Not now.**
