# Permissions page: can't save, or removes permissions, if a name contains special characters

- **Status:** ready
- **Type:** bug (data loss)
- **Priority:** P1
- **Found:** 2026-11-16, analysis of the web front end; reproduced in Chrome on a copy of the web app


## Current situation

`Settings` → `Permission` saves with every click on a checkbox. To do so, it reads **all** permissions of all users and roles back from the page ([settings.html:544](../../webapp/templates/admin/settings.html#L544)) and sends them to `/api/save_permissions`, which replaces the file.

The page finds the checkboxes with CSS classes built from the names:

```js
document.querySelectorAll(`.user-${user}-workflow-${workflowName}-stage-${stageName}:checked`)
```

A name is not a valid part of a selector if it contains a space, `.`, `#`, `$`, `@`, a quote, ...:

| Name | Example | Result | Found by |
|---|---|---|---|
| Space followed by a digit | Stage `STAGE 2.1` of the shipped example [parallel_example.json](../../etc/examples/workflows/parallel_example.json) | `querySelectorAll` throws `SyntaxError: ... is not a valid selector`. **No change on the whole page is saved any more.** The checkbox looks changed, the error is only in the browser console. | reproduced: user with a permission for the stage `STAGE 2.1` |
| Space, `.` | Stage `Create object list`, workflow `my.workflow`, user `a.b` | The selector is valid, but finds nothing. The permissions of this stage, workflow or user are missing in what is sent: **they are removed from `user_permissions.json` with the next click on any checkbox**, also one of another user. | code review |
| `#`, `$`, `@` (allowed in IBM i user profiles) | User `dev#1` | As the first or the second row, depending on the position | code review |

Permissions are only removed, never added. An administrator can remove their own `admin` permission this way.


## Requirements

1. Users, roles, workflows and stages with any name can be maintained.
   The page reads names from `data-*` attributes and compares them in JavaScript, or uses `CSS.escape()`.
2. If reading or saving fails, the administrator sees an error, and the page shows the saved state again.
3. `/api/save_permissions` doesn't remove a user or role by accident: they are only deleted if the request names them as deleted, not because they are missing in it.


## Acceptance criteria

- [ ] Test: `/api/save_permissions` without a user who exists → the user is kept. Deleting a user or a role in the page still works.
- [ ] Browser test (or manual check, see [browser tests](../features/web-ui-browser-tests.md)): users `a.b` and `dev#1`, workflow `my.workflow`, stages `STAGE 2.1` and `Create object list`, each with permissions. Change one checkbox of another user → `user_permissions.json` contains all permissions as before, plus the change.
- [ ] Browser test (or manual check): `/api/save_permissions` answers with an error → an error message is shown.
- [ ] Changelog entry.


## Non-goals

* The new permissions page (explicit save, changes of two administrators, last administrator): [permissions page](../features/web-ui-permissions-page.md)


## Open questions

None.
