# Permissions

* [Login](#login)
* [Users and roles](#users-and-roles)
* [Permissions](#permissions-1)
* [Configuration file](#configuration-file)
* [API tokens](#api-tokens)


## Login

Users log in with their IBM i user profile and password. The web app checks them with an ODBC connection to the system in `webapp/etc/db_config.py`.

In addition, the user has to be listed in `etc/user_permissions.json`. Users which are not listed can't log in, and i-Releaser doesn't even try: a failed connection counts for the IBM i profile.

After too many failed logins further logins are blocked: those of a user until an admin unblocks them (`Administration` → `Security` → `Blocked logins`), those of a client address for some time (see [installation](installation.md#production-checklist)).

A session ends one hour after the last request, and after 12 hours in any case. Log out with the button in the navigation.


## Two-factor authentication

The login can also need a code of an authenticator app (Microsoft Authenticator, Google Authenticator, FreeOTP, ...), see [feature](features/two-factor-authentication.md).

* **Set up:** `My account` → `Two-factor authentication` → `Set up`: scan the QR code with the app, enter the code it shows. You get 10 recovery codes: each logs in once without the app (e.g. a lost phone). Keep them in a safe place.
* **Log in:** user, password and the current code of the app (or a recovery code) in the field `Code`. The code is checked before the password goes to the IBM i: a wrong code doesn't count for `QMAXSIGN`.
* **Policy** `C_2FA_POLICY` in `etc/settings.py`: `off`, `optional` (each user decides, the default of existing installations), `admins` (required for users with `admin`, the default of new installations), `required` (all users). A user who needs it and hasn't set it up can only set it up after the login.
* **Confirm with a code:** creating an API token, changing permissions or settings, unblocking a login and resetting the two-factor authentication of a user need a code entered in the last `C_2FA_STEP_UP_MINUTES` (10). The page asks for it.
* **Lost phone and recovery codes:** an admin resets the two-factor authentication of the user (`Administration` → `Security` → `Two-factor authentication` → `Reset`). The user can log in with the password and sets it up again.
* After `C_2FA_MAX_FAILURES` (5) wrong codes within `C_LOGIN_BLOCK_MINUTES` no code of the user is accepted for this time.


## Users and roles

Permissions can be given to users and to roles. A user gets the permissions of their roles in addition to their own.

Each permission can be given on three levels:

| Level | Applies to |
|---|---|
| General | All workflows and stages |
| Workflow | All stages of one workflow |
| Stage | One stage of one workflow (only for permissions which are checked per stage, see below) |

Permissions don't include each other. E.g. a user who may run stages also needs `read` to open the deployment page.

Administrators maintain users, roles and permissions in the web app (`Administration` → `Permissions`): one table per user or role, with a row for `General`, each workflow and its stages. Changes of the file are loaded automatically.

* Each change is saved at once. If the permissions have been changed meanwhile (another administrator, an edit of the file), nothing is saved and the page offers to load the current state.
* A change after which no user would have `admin` (own, or from a role) is refused.
* Roles can have permissions for workflows and stages, like users. A permission a user has from a role or from a higher level (`General`, the workflow) is shown grey, with where it comes from.
* Names of workflows and stages are compared without case.


## Permissions

| Permission | Allows | Checked per |
|---|---|---|
| `admin` | `Administration`: maintain users, roles and permissions; state of the processing service; logs of the web app (menu `Logs`); errors of workflow files | general |
| `read` | See the deployments and objects of the workflow, its definition, logs and activity history | workflow |
| `start workflow` | Create deployments of the workflow (web app and Web API) | workflow |
| `run` | Run a stage, [schedule](processing-service.md#scheduled-runs) its run or cancel a scheduled run (also one of another user), remove it from the queue of the processing service, reset the status of a stage, reset the last finished stage, reset the status of the deployment, include or exclude objects | stage (reset of the deployment status and objects: workflow) |
| `change check error` | Turn the error check of a step on or off | stage |
| `cancel workflow` | Cancel a deployment | workflow |
| `edit-custom-data` | Edit the [editable fields](workflow.md#editable-custom-fields) of the custom data | workflow |
| `4-eyes check` | Approve a stage with `four_eyes_check` before it runs ([four-eyes check](#four-eyes-check)) | general, workflow, stage |

`start workflow` and `edit-custom-data` let users set custom data. If your steps use custom data, limit it with [`create_fields`](workflow.md#create-fields) and only give these permissions to trusted users (see [DB deployment](db-deployment.md#security)).


## Configuration file

`etc/user_permissions.json`. User, workflow and stage names are in **lower case**.

```json
{
  "users": {
    "anna": {
      "roles": ["developer"],
      "permissions": {
        "general": ["read"],
        "workflows": {
          "erp_release": {
            "general": ["start workflow", "cancel workflow"],
            "stages": {
              "prod": ["run", "change check error"]
            }
          }
        }
      },
      "detailed_infos": {"description": "Release manager", "mail": "anna@example.com", "extra": {}}
    },
    "admin1": {
      "roles": ["admin"],
      "permissions": {"general": [], "workflows": {}}
    }
  },
  "roles": {
    "developer": {
      "permissions": {
        "general": ["read", "start workflow"],
        "workflows": {
          "erp_release": {
            "general": [],
            "stages": {
              "build": ["run"],
              "test": ["run", "change check error"]
            }
          }
        }
      }
    },
    "admin": {
      "permissions": {
        "general": ["admin", "read", "start workflow", "run", "change check error", "cancel workflow", "edit-custom-data"]
      }
    }
  }
}
```

In this example, `anna` can create deployments of `erp_release` (own permission) and of all workflows (role `developer`),
run the stages `build` and `test` (role) and `prod` (own permission), and read all deployments.

`detailed_infos.mail` (field *Mail* on the permissions page) is the e-mail address of the user for the [notifications](features/notifications.md) (`@creator`, `@runner`, `@role:<name>`). Users without it get no mail.


## Four-eyes check

A stage with `four_eyes_check: true` in the [workflow](workflow.md#stage-attributes) only runs after a second person has approved it (button `Approve` on the deployment page, or `POST /api/approve_stage/{id}/{stage_id}`).

* Approve: permission `4-eyes check` for the stage, not the user who created the deployment.
* Run (also schedule): not the user who approved it.
* The approval is for the deployment as it is: a change of the object list, the selection of objects or the custom data makes it invalid (history entry `approval_invalid`). After the stage has finished, a new run needs a new approval.

The permission `deploy` of older versions has no effect and isn't offered anymore.


## Audit log

`Administration` → `Audit` (permission `admin`) shows who did what: logins (also failed and blocked ones), logouts, API tokens, two-factor authentication, permission changes (what has been added and removed), settings, viewed logs, and the actions on deployments. Export as CSV.
The entries can't be changed without notice: each contains a hash of the one before, the page shows a warning if an entry has been changed or deleted.
`C_AUDIT_RETENTION_DAYS` (730) keeps them; `C_AUDIT_FILE` writes each event as a JSON line into a file too, e.g. for a SIEM. See [feature](features/audit-log.md).


## API tokens

Each user can create personal API tokens on the user page (`My account`, `/user`). It also shows the roles of the user and the permissions they have in the end.
A request with a token acts with the permissions of that user. See [Web API](webapi.md#authentication).

* A user can have several tokens (at most 20), one per client: e.g. `OBI extension` and `Nightly pipeline`. Deleting one doesn't stop the others.
* Each token has a **name** (unique per user), a **scope** and an **expiry**:
  * Scope `write`: everything the user may do. Scope `read`: only reading requests, e.g. for a dashboard, a monitor or the OBI extension when it only shows deployments (`GET`, and the reads of the Web API v1 with `POST`: `get_meta_file_json`, `list_deployments`).
  * Expires after the days given at its creation, at most `C_TOKEN_MAX_DAYS` (365, `0`: never).
* Tokens are only created in the web app (not with a token), with a recent code of the [two-factor authentication](#two-factor-authentication).
* A token is shown only once, with a button to copy it. i-Releaser only stores its hash (table `api_tokens` of `var/app.sqlite`). New tokens start with `irt_`, so you recognize them in logs and secret scanners.
* The user page shows when each token was created, used last and when it expires. Tokens of older versions expire `C_TOKEN_MAX_DAYS` after their first use with this version; tokens of the format before 2026-10 show a warning and won't be accepted by the next major version.
* Delete a token on the user page when it's not needed anymore. Admins can revoke the tokens of any user (`Administration` → `Security` → `API tokens`).
* Removing a user deletes the tokens and the two-factor authentication of the user.
* Tokens of versions before 2026-11 (`webapp/etc/keys.json`, one per user) are taken over into the database at the start of the web app, with the name `API token` and the scope `write`; the file is renamed to `keys.json.migrated`.
