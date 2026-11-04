# Permissions

* [Login](#login)
* [Users and roles](#users-and-roles)
* [Permissions](#permissions-1)
* [Configuration file](#configuration-file)
* [API tokens](#api-tokens)


## Login

Users log in with their IBM i user profile and password. The web app checks them with an ODBC connection to the system in `webapp/etc/db_config.py`.

In addition, the user has to be listed in `etc/user_permissions.json`. Users which are not listed can't log in, and i-Releaser doesn't even try: a failed connection counts for the IBM i profile.

After too many failed logins of a user or from a client address, further logins are blocked for some time (see [installation](installation.md#production-checklist)).

A session ends one hour after the last request, and after 12 hours in any case.


## Users and roles

Permissions can be given to users and to roles. A user gets the permissions of their roles in addition to their own.

Each permission can be given on three levels:

| Level | Applies to |
|---|---|
| General | All workflows and stages |
| Workflow | All stages of one workflow |
| Stage | One stage of one workflow (only for permissions which are checked per stage, see below) |

Permissions don't include each other. E.g. a user who may run stages also needs `read` to open the deployment page.

Administrators maintain users, roles and permissions in the web app (`Settings`). Changes of the file are loaded automatically.


## Permissions

| Permission | Allows | Checked per |
|---|---|---|
| `admin` | `Settings`: maintain users, roles and permissions; state of the processing service; logs of the web app (menu `Logs`); errors of workflow files | general |
| `read` | See the deployments and objects of the workflow, its definition, logs and activity history | workflow |
| `start workflow` | Create deployments of the workflow (web app and Web API) | workflow |
| `run` | Run a stage, remove it from the queue of the processing service, reset the status of a stage, reset the last finished stage, reset the status of the deployment, include or exclude objects | stage (reset of the deployment status and objects: workflow) |
| `change check error` | Turn the error check of a step on or off | stage |
| `cancel workflow` | Cancel a deployment | workflow |
| `edit-custom-data` | Edit the [editable fields](workflow.md#editable-custom-fields) of the custom data | workflow |
| `deploy` | Not checked yet | |
| `4-eyes check` | Not checked yet | |

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


## API tokens

Each user can generate a personal API token on the user page (`/user`).
A request with the token acts with the permissions of that user. See [Web API](webapi.md#authentication).

* A user has one token. Generating a new one replaces the old one.
* The token is shown only once. i-Releaser only stores its hash (`webapp/etc/keys.json`).
* The user page shows when it was created and used last.
* Delete the token on the user page when it's not needed anymore.
