# New permissions page

- **Status:** draft
- **Type:** improvement
- **Priority:** P2
- **Source:** [Modernization of the web front end](web-ui-modernization.md), step 7
- **Depends on:** [Layout and styles](web-ui-layout.md), [Scripts in files](web-ui-scripts.md), [bugfix](../bugfixes/permissions-page-names-in-selectors.md)


## Current situation

`Settings` → `Permission` (part of `settings.html`, 478 lines of JavaScript).

* All users and roles on one page, as tables in tables (up to 4 levels). Each level repeats a row of nine permission names with a row of checkboxes below.
* Every click saves at once, and saves **everything**: the page reads all permissions of all users and roles back from its checkboxes and replaces the file (see [bugfix](../bugfixes/permissions-page-names-in-selectors.md)).
  * Two administrators (or two tabs): the one who clicks last overwrites the changes of the other with the old state of their page.
  * A wrong click takes effect immediately. There is no undo.
  * An administrator can remove their own `admin` permission, or that of the last administrator, with one click. Then the file has to be edited on the server.
* After adding or deleting a user, role, workflow or stage the page reloads and shows the tab `General`.
* Every permission can be ticked on every level, also where it's never checked (see [permissions](../permissions.md#permissions-1): e.g. `admin` only counts on the general level, `cancel workflow` not per stage).
* `deploy` and `4-eyes check` can be given, but are not checked anywhere ([four-eyes check](four-eyes-check.md)).
* The page doesn't show what a user may do in the end (own permissions plus those of the roles).
* Permissions of a role for a workflow can't be edited, only its general permissions. The workflows of a role are listed by name.
* `description` and `mail` of a user (`detailed_infos` of the file) are not shown.


## Feature

```
Settings / Permissions                      [Unsaved changes]   [Discard] [Save]

Users            [+]   |  runner
 boss                  |  Description [                    ]  Mail [               ]
 intern                |  Roles  [x] releaser
>runner                |
Roles            [+]   |                    read  start  run  check  cancel  edit
 releaser              |  General            x     .      .     .      .      .
                       |  parallel_example   .     .      x     .      .      .   [remove]
                       |    START                         x     .
                       |    STAGE 2.1                     x     .
                       |    [+ stage]
                       |  deploy_2_test      x     .      .     .      .      .   [remove]
                       |    BUILD                         x     .
                       |  [+ workflow]
                       |                                   (x) from role releaser
                       |  [Delete user]
```

* Own page `/settings/permissions`, with its own entry below `Settings`. A reload stays on it.
* Left: users and roles, with a search. Right: the selected one.
* **One table per user or role:** the rows are `General`, each workflow and its stages; the columns are the permissions. A checkbox only exists where the permission is checked on that level. `admin` is a switch of its own above the table.
* **Effective permissions:** a permission which the user already has from a role or from a higher level is shown as given (grey), with where it comes from.
* **Roles** can have permissions for workflows and stages, as users.
* **Save:** changes are collected in the page. `Unsaved changes` appears with the first change; `Save` sends them, `Discard` reads the saved state again. Leaving the page with unsaved changes asks.
* **No lost changes:** the page sends the version of the permissions it was loaded with. If the file has changed since then, the server answers `409` and the page offers to load the current state.
* **Administrators:** the server rejects a change after which no user has `admin`. Removing the own `admin` permission asks for confirmation.
* **Names:** any name works (the page keeps the permissions as data, not in CSS classes). The server checks new names: not empty, no control characters, at most 64 characters, unique.
* **Delete:** asks once, and says how many users have the role.
* `deploy` and `4-eyes check` are shown with the note `not checked yet`.
* `description` and `mail` can be edited.


## Acceptance criteria

- [ ] Test `save_permissions`: an old version → `409`, nothing changed; the current version → saved.
- [ ] Test: a change which leaves no user with `admin` (own permission, role, deleting the user or the role) → `409`, nothing changed.
- [ ] Test: names with space, `.`, `#`, `$`, `@`, `'` for users, roles, workflows and stages are saved and read unchanged; an empty name and a name which exists are rejected.
- [ ] Test: permissions of a role for a workflow and a stage are saved and count for its users.
- [ ] Test: users without `admin` get `403` for the page and the endpoints.
- [ ] Test: the effective permissions of a user with a role (a function used by the page).
- [ ] Browser tests (or manual checks, see [browser tests](web-ui-browser-tests.md)): change two checkboxes of two users → `Unsaved changes` → `Save` → after a reload both are saved and nothing else changed in `user_permissions.json`; `Discard`; add a workflow and a stage to a user; the conflict message with a second session.
- [ ] Docs: [permissions.md](../permissions.md), [webapi.md](../webapi.md).


## Non-goals

* Checking `deploy` and `4-eyes check`: [four-eyes check](four-eyes-check.md)
* A history of the changes of permissions (who changed what). Today a change is one log line.
* Groups or users from IBM i


## Open questions

1. Explicit `Save` (**recommended**), or save with each click as today (then with the conflict check per change)?
2. `deploy` and `4-eyes check`: shown with a note (**recommended**), or hidden until they are checked?
3. Is editing `description` and `mail` wanted?
