# Scripts and extensions

* [Your own steps (SCRIPT)](#your-own-steps-script)
* [Run commands from a script](#run-commands-from-a-script)
  * [Run commands in parallel](#run-commands-in-parallel)
* [Example scripts](#example-scripts)
* [Hooks](#hooks)
* [Web app extensions](#web-app-extensions)


## Your own steps (SCRIPT)

A `SCRIPT` step calls a Python function of a file in `scripts/`:

```python
# scripts/notify.py
import logging

from modules.meta_file import Meta_File
from modules.stages import Stage
from modules.deploy_action import Deploy_Action


def ticket_check(meta_file: Meta_File, stage_obj: Stage, action: Deploy_Action) -> None:

    ticket = (meta_file.custom_data or {}).get('ticket')
    if not ticket:
        raise Exception("No ticket in the custom data of the deployment")

    logging.info(f"Deployment {meta_file.project} {meta_file.deploy_version} for ticket {ticket}")
```

Map it to a processing step (`etc/default_step_action.json` or `step_action` of the workflow) and use the step in a stage:

```json
{"processing_step": "ticket_check", "environment": "SCRIPT", "execute": "notify.ticket_check", "check_error": true}
```

* The step fails if the function raises an exception.
* Its output (`print`, `logging`) and errors are stored with the step. `logging` entries below the log level of `etc/logger_config.py` and `webapp/etc/logger_config.py` are not stored.
* A file of `scripts/` is loaded when a step or hook uses it the first time (the processing service loads all at its start).
  **Restart the web app and the processing service after a change.** A file which can't be loaded only fails the steps and hooks which use it (the error is in the step and in the log).
* Only functions of files in `scripts/` can be called: `filename.function_name`, no other modules, no names starting with `_`.
* `scripts/` is not tracked by git: your scripts stay when you update i-Releaser.

Useful attributes:

| Object | Attributes |
|---|---|
| `meta_file` (the deployment) | `id`, `project`, `deploy_version`, `status`, `commit`, `release_branch`, `custom_data`, `meta_dir` (directory for files of this deployment), `main_deploy_lib`, `backup_deploy_lib`, `remote_deploy_lib`, `deploy_objects`, `workflow`, `save()`, `get_compile_list()` |
| `stage_obj` | `name`, `host`, `build_dir`, `remote_dir`, `execute_remote`, `processing_steps`, `lib_mapping` |
| `action` (the step) | `processing_step`, `check_error`, `sub_actions` |

### Compile list

`meta_file.get_compile_list()` returns the compile list the deployment was [created](webapi.md#create-a-deployment) with (`compiles` of an OBI build list), or `None`.

```python
for level in meta_file.get_compile_list() or []:
    for source in level['sources']:
        ...
```

* It's stored in `compile-list.json` in `meta_dir`. Deployments created before have it in `custom_data['compiles']`, `get_compile_list()` returns that too.
* Its values come from the user who created the deployment. Check them like custom data before you use them in commands or paths.


## Run commands from a script

A script can add sub-steps and run them. Each sub-step is shown with its own status and log on the deployment page.
This is how the example scripts work, e.g. one `CRTSAVF` per library:

```python
from modules import deploy_action as da
from modules import ibm_i_commands


def create_savfs(meta_file, stage_obj, action) -> None:

    cmd = ibm_i_commands.IBM_i_commands(meta_file)

    for lib in meta_file.deploy_objects.get_lib_list_from_prod():

        sub_step = action.sub_actions.add_action(da.Deploy_Action(
            cmd=f"CRTSAVF {meta_file.main_deploy_lib}/{lib}",
            environment=da.Command_Type.QSYS,
            processing_step=action.processing_step,
            stage=stage_obj.name,
            check_error=action.check_error
        ))
        # Raises an exception if the sub-step fails and has the error check on
        cmd.execute_action(stage=stage_obj, action=sub_step)
```

The commands of sub-steps can use [placeholders](workflow.md#placeholders) too. If a script builds a command from custom data itself, it has to check or quote the values.

`QSYS` commands reach `cl` unchanged. Don't escape anything for the shell, e.g. `$` in object names.

### Run commands in parallel

Sub-steps with `parallel` run at the same time as the sub-steps before them with the same `parallel_group`. The rules are the same as for [parallel steps](workflow.md#parallel-steps) of a stage.
E.g. all objects of a level at once, and the next level after that:

```python
from itertools import groupby

from modules import deploy_action as da
from modules import ibm_i_commands
from modules.object_status import Status as Obj_Status


def restore_objects(meta_file, stage_obj, action) -> None:

    cmd = ibm_i_commands.IBM_i_commands(meta_file)

    for level, objects in groupby(meta_file.deploy_objects.get_obj_list_sorted_by_level(), key=lambda obj: obj.level):

        objects = list(objects)

        for obj in objects:

            sub_step = action.sub_actions.add_action(da.Deploy_Action(
                cmd=f"RSTOBJ OBJ({obj.name}) SAVLIB({obj.lib}) DEV(*SAVF) SAVF({meta_file.remote_deploy_lib}/{obj.lib}) RSTLIB({obj.prod_lib})",
                environment=da.Command_Type.QSYS,
                processing_step=action.processing_step,
                stage=stage_obj.name,
                check_error=action.check_error,
                parallel_group=f"level-{level}",
                parallel=True
            ))
            cmd.execute_action(stage=stage_obj, action=sub_step)

        # Raises an exception if a sub-step failed and has the error check on
        cmd.wait_for_parallel_actions()

        for obj in objects:
            obj.deploy_status = Obj_Status.FINISHED

        meta_file.save()
```

* `execute_action` returns while the sub-step is still running. Everything which depends on its result has to come after `wait_for_parallel_actions()`.
* The failure of a sub-step isn't raised by its own `execute_action`. It's raised by the next one which has to wait, by `wait_for_parallel_actions()`, or at the end of the script: the script step fails in all three cases.
* The script step has ended when all of its sub-steps have ended, even if the script fails before.
* The sub-steps of a script don't affect the group of the stage, also if a script step itself runs in parallel. All parts of a script share the same group, no matter how many `IBM_i_commands` objects it creates.


## Example scripts

`setup3.13.sh` copies them from `scripts/examples/` to `scripts/`. Their step actions are in `etc/examples/default_step_action.json`.
They are examples: check and adapt them to your system before you use them.

| Processing step | Function | What it does |
|---|---|---|
| `pre` | `pre.pre_cmd` | Only writes a log entry. Template for your own function. |
| `post` | Shell command | Only prints a text. Replace it with your own step. |
| `clean_current_commit` | `build.clean_current_commit` | Resets the repository in `build_dir` to the release branch of the deployment (`origin/{release branch}`) |
| `create_compile_script` | `build.create_compile_script` | Creates the release branch from the commit of the deployment and runs the build scripts `cleanup.sh`, `reset.sh` and `create_build_script.sh`, which your repository has to have in `make/scripts/` |
| `git_save_changes` | `build.git_save_changes` | Commits and pushes the build result |
| `load_object_list` | `build.load_object_list` | Imports the [object list](workflow.md#object-list) |
| `save-prepare` | `save_objects.init_save` | Creates the main deployment library and a save file per library |
| `save` | `save_objects.save_objects_to_savf` | Saves the objects into the save files and copies them to the IFS. Leaves out the tables of a [DB deployment](db-deployment.md). |
| `transfer` | `transfer.transfer_to_target` | Copies the files of the deployment with `scp` to `remote_dir` on `host` |
| `target-prepare` | `target_prepare.init_deployment` | Creates the backup and remote deployment libraries and save files on the target |
| `backup-old-objects` | `backup_old_objects.backup_objects_on_target` | Saves the objects which are going to be replaced into the backup library |
| `perform-deployment` | `target_deployment.restore_objects_on_target` | Restores the objects with `RSTLIB`. Leaves out the tables which have been replaced by a [DB deployment](db-deployment.md), and fails if its cut-over hasn't been done yet. |
| `db-prepare`, `db-copy`, `db-cutover`, `db-cleanup` | `db_deployment.*` | [DB deployment](db-deployment.md) |
| `jira_successful` (optional) | `jira.report_stage` | [Jira integration](jira.md#as-a-processing-step) |

`jira.on_event` is a [hook](#hooks) for the Jira integration.


## Hooks

Hooks are functions in `scripts/` too, but they are called on events of a deployment (created, stage finished, ...) instead of as a step.
See [workflow configuration](workflow.md#hooks).


## Web app extensions

| Extension | How |
|---|---|
| Own routes (pages or API endpoints) | Python files in `webapp/custom/routes/`. They are loaded when the web app starts, after the routes of the web app: a path of the web app can't be used (the start stops with a message). A file with an error is left out and shown on the settings page. Example: [`docs/examples/custom-routes/test.py`](examples/custom-routes/test.py) adds `/custom_test/{test}` when it is copied to `webapp/custom/routes/`. |
| Own HTML on the deployment page | `webapp/templates/custom_templates/deployment_status.html` is included in the deployment page, if it exists. E.g. a button which starts a rollback workflow for this deployment, see [below](#scripts-of-custom-templates). |
| Own scripts and files for the pages | `webapp/static/custom/`, served as `/static/custom/...` |

A custom route:

```python
# webapp/custom/routes/hello.py
from fastapi import Request
from index import app


async def hello(request: Request, name: str):
    return {"message": f"Hello {name}"}


app.add_api_route('/custom/hello/{name}', hello, methods=['GET'])
```

Custom routes need a login like all other routes, but they don't check [permissions](permissions.md) by themselves.
Use `permission_config.check_user_permission(...)` like the routes in `webapp/routes/routes.py`.

These directories are not tracked by git.

### Own pages

A custom route can show a page in the layout of the web app: a template which extends `base.html`, rendered with the navigation data.

```python
# webapp/custom/routes/releases.py
from fastapi import Request
from index import app
from routes import routes
from web_modules import http_functions


def releases(request: Request):
    return http_functions.get_html_response(request, 'custom_templates/releases.html',
                                            sidebar=routes.get_sidebar_data(request), releases=['6', '7'])


app.add_api_route('/custom/releases', releases, methods=['GET'])
```

```html
<!-- webapp/templates/custom_templates/releases.html -->
{% extends 'base.html' %}
{% from 'components/ui.html' import page_header, empty_state %}

{% block title %}Releases{% endblock %}
{% block nav_active %}deployments{% endblock %}
{% block page_header %}{{ page_header('Releases', breadcrumb=[('Deployments', '/'), ('Releases', None)]) }}{% endblock %}

{% block content %}
  {% for release in releases %}<p>{{ release }}</p>{% else %}{{ empty_state('No releases') }}{% endfor %}
{% endblock %}

{% block scripts %}<script type="module" src="{{ url_for('static', path='custom/releases.js') }}"></script>{% endblock %}
```

| Block of `base.html` | Content |
|---|---|
| `title` | Name of the page in the browser tab (`<title> · i-Releaser`) |
| `nav_active` | Entry of the navigation which is marked: `deployments`, `objects`, `workflows`, `settings`, `logs`, `user`. Empty: none |
| `page_header` | Breadcrumb, the one `<h1>` of the page and its actions: macro `page_header(title, breadcrumb, meta, status)` |
| `css` | More stylesheets |
| `content`, `no_form_content` | The content. Neither is inside a `<form>` |
| `scripts` | Scripts at the end of the page. `Swal`, jQuery and Bootstrap are already loaded |

* `sidebar=routes.get_sidebar_data(request)` shows the navigation, `sidebar=None` a page without it.
* The macros of [`templates/components/ui.html`](../webapp/templates/components/ui.html): `page_header`, `status_pill`, `icon_button`, `kv_list`, `section`, `empty_state`, `code_block`. Filters: `datetime`, `duration`, `or_dash`.
* Colours from the tokens of `static/assets/css/app.css` (`var(--ir-text)`, `var(--ir-success)`, ...), so the page works in the dark mode too.

### Scripts of custom templates

Put JavaScript of a custom template into a file in `webapp/static/custom/`, not into the template:

* No `<script>` with code and no `onclick="..."` in the template. Values for the script go into `data-*` attributes; the script finds its elements by them.
* The template loads the file with `<script type="module" src="{{ url_for('static', path='custom/<name>.js') }}"></script>`.
* Actions use `POST`. With a login session the web app rejects actions with `GET` (`405`), see [Web API](webapi.md).
* `Swal` (SweetAlert2), jQuery and Bootstrap are available on every page. The helpers of the web app are ES modules, see below.

The web app sends a [Content-Security-Policy](technik.md#content-security-policy): the browser doesn't run inline scripts and `onclick` of a template. `C_CSP_REPORT_ONLY = True` in `etc/settings.py` only reports them in the console of the browser, for the time you move your templates.

Helpers (`webapp/static/assets/js/app/`). A script in `webapp/static/custom/` imports them with a relative path:

```js
import { post_json } from '../assets/js/app/api.js';
```

| Module | Function | |
|---|---|---|
| `api.js` | `get_json(url)`, `post_json(url, data)` | Request with JSON. A response with an error status throws an `Api_Error` with the `message` of the server (and `status`). An ended session (`401`) shows `Your session has ended` with a button to log in again |
| `dialogs.js` | `confirm_action({title, text, confirm, cancel, danger, action})` | One dialog for an action which can't be undone. `action` (async) runs when it's confirmed; the dialog waits and shows its error. Returns the result of `action`, `null` if canceled |
| | `choose({title, text, options})` | One of two ways (`options: [{value, label}, {value, label}]`), `null` if canceled |
| | `toast(message)`, `reload_with_toast(message)` | The result of an action: a short message which disappears (after a reload) |
| | `show_error(error)` | An error which stays until it's closed |
| `dom.js` | `on_action(name, handler)`, `on_change(name, handler)` | Click or change of elements with `data-action="<name>"`, also of elements added later |
| | `read_json(id)` | The data of `<script type="application/json" id="...">` |
| | `element(tag, text)`, `escape_html(text)` | Elements with text; HTML only where the DOM can't be used |

The old global functions `postData`, `async_postData`, `http_post`, `http_get` and `http_getData` (`web.deploy.js`) are removed. Use `post_json` and `get_json`.

Example: a button which starts the workflow `rollback_deployment` for a finished deployment. [`docs/examples/rollback/`](examples/rollback/) has both files, tested in `tests/test_web_browser.py`.

```html
<!-- webapp/templates/custom_templates/deployment_status.html -->
{% if deployment_dict['general']['status'] == 'finished' %}
  <button type="button" class="btn btn-sm btn-outline-secondary" data-rollback
          data-project="{{ deployment_dict['general']['project'] }}"
          data-version="{{ deployment_dict['general']['deploy_version'] }}">Roll back</button>
  <script type="module" src="{{ url_for('static', path='custom/rollback.js') }}"></script>
{% endif %}
```

```js
// webapp/static/custom/rollback.js
import { post_json } from '../assets/js/app/api.js';
import { confirm_action } from '../assets/js/app/dialogs.js';

document.addEventListener('click', async (event) => {
    const button = event.target.closest('[data-rollback]');
    if (!button) {
        return;
    }
    const {project, version} = button.dataset;
    const data = await confirm_action({
        title: 'Roll back this deployment?',
        text: `Starts the workflow rollback_deployment for ${project}, version ${version}.`,
        confirm: 'Roll back', cancel: 'Keep it', danger: true,
        action: () => post_json('/api/start_workflow/rollback_deployment', {project, version}),
    });
    if (data) {
        location.href = `/show_details/${data.meta_file.general.id}`;
    }
});
```

`deployment_status.html` is shown in the header of the deployment page, beside its actions (`History`, `Cancel deployment`). Its context: `deployment_dict` (the data of [`/api/get_meta_file_json`](webapi.md): `general`, `custom_data`, `deploy_libs`, ...).

Moving an old custom template:

| Before | After |
|---|---|
| `<img onclick="rollback_deployment('{{ project }}', {{ version }})">` | `<button data-rollback data-project="{{ project }}" data-version="{{ version }}">` |
| `<script> function rollback_deployment(...) {...} </script>` in the template | The function in `webapp/static/custom/rollback.js`, started by a `click` listener |
| `http_getData('/api/start_workflow/...?project=...')` (`GET`) | `post_json('/api/start_workflow/...', {...})` of `app/api.js` (or `fetch` with `method: 'POST'`) |
| `Rollback started!` before the server has answered | `confirm_action` waits for the answer and shows its error |

If the workflow has [`create_fields`](workflow.md#create-fields), they have to contain the fields the button sends (`$.project`, `$.version`).
