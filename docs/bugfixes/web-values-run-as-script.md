# Object names, commands and names from the configuration can run as script in the web app (XSS)

- **Status:** finished (2026-11-17; tested with `tests/test_web_pages.py` and in headless Chrome on a copy of the web app, not on IBM i)
- **Type:** security
- **Priority:** P1
- **Found:** 2026-11-16, analysis of the web front end; partly reproduced in Chrome on a copy of the web app
- **Confidential:** don't publish before the fix is released


## Current situation

Jinja2 escapes values for HTML. In the following places that is not enough, or it's turned off:

| # | Where | Value | Problem | Found by |
|---|---|---|---|---|
| 1 | `onchange="set_source_ready_4_deployment(this, 6, '{{ object['lib'] }}', '{{ object['name'] }}', ...)"`, [show-deployment.html:308](../../webapp/templates/overview/show-deployment.html#L308) | Library, name and type of an object | The value is inside JavaScript inside an HTML attribute. The browser turns `&#39;` back into `'` before it runs the handler: a quote ends the string, the rest runs as script. | reproduced: object `o'brien` → `SyntaxError: missing ) after argument list`, its switch does nothing |
| 2 | `onclick="show_deploy_object_details('{{ row['project'] }}', ...)"`, [list-objects.html:60](../../webapp/templates/overview/list-objects.html#L60) | Project, library, name, type, attribute | As 1 | code review |
| 3 | `{{ cmd['cmd']\|safe }}`, [action_row.html:32](../../webapp/templates/overview/details/action_row.html#L32), [:35](../../webapp/templates/overview/details/action_row.html#L35) | Command of a step. Sub-steps created by scripts contain library and object names, e.g. `CLRPFM {obj.lib}/{obj_name}` ([save_objects.py:99](../../scripts/examples/save_objects.py#L99)) | Escaping is turned off: HTML in a command becomes part of the steps window | code review |
| 4 | Object history: table and title built from strings (`${row[key]}`, `${name}`), [list-objects.html:111](../../webapp/templates/overview/list-objects.html#L111) | All columns of the object history | Inserted as HTML | code review |
| 5 | Processing history: `${item.details}`, `${item.user}`, ..., [show-deployment.html:780](../../webapp/templates/overview/show-deployment.html#L780) | Details of the actions (object names, workflow names, field paths) | Inserted as HTML | code review |
| 6 | Stage names in HTML built with f-strings: `onclick="run_stage(..., '{stage.name}')"`, `<button ...>{stage.name}</button>`, [flowchart.py:54](../../webapp/web_modules/flowchart.py#L54), [:77](../../webapp/web_modules/flowchart.py#L77), [:93](../../webapp/web_modules/flowchart.py#L93); [stage-actions.html:2](../../webapp/templates/overview/details/stage-actions.html#L2); dialog titles `Steps for ${stage_name}` | Stage name of the workflow file | Not escaped at all, then inserted with `flow_html\|safe` | code review |
| 7 | `onclick="delete_role('{{ role }}')"`, `delete_user`, `add_user_workflow`, ... and `<code>${error.message}</code>`, [settings.html:203](../../webapp/templates/admin/settings.html#L203) ff. | Names of roles, users, workflows, stages; error texts of the server | As 1 and 4 | code review |

Who can set these values:

* **1 – 5:** Names and libraries of objects come from the object list of a deployment, which the build writes from the names of the sources. Custom data and the compile list come from the caller of the Web API.
  So a user who can add sources or start a workflow, but may not run stages, can prepare a value.
  The script then runs in the browser of the user who opens the steps window, the object history or the processing history, or who switches the object: with that user's permissions (run a stage, cancel, as administrator change permissions). The CSRF check doesn't help, the request comes from the own page.
* **6, 7:** Workflow files and permissions are maintained by administrators. Here it's a defect of robustness: a `'` or `<` in a name breaks the page (see also [stage names](stage-name-breaks-deployment-page.md)).

A complete attack was not carried out. Number 1 was reproduced up to the broken handler.


## Requirements

1. No value is written into inline JavaScript. Handlers read their values from `data-*` attributes (`element.dataset`). For an attribute value the HTML escaping of Jinja2 is sufficient.
2. No `|safe` for data. Commands are shown as text. The replacement of `&quot;` and `&#39;` in [flowchart.py:163](../../webapp/web_modules/flowchart.py#L163) is removed (a leftover from the time the HTML was put into a JavaScript string).
3. HTML which JavaScript builds from data uses `textContent` or the DOM API, or one helper `escape_html` for every value.
4. Python doesn't build HTML with f-strings from data: templates (escaped automatically) or `markupsafe.escape`.
5. One test deployment for all tests of this file: an object, a library, a stage, a command of a sub-step, an action detail and custom data which contain `'`, `"`, `<`, `>`, `&` and `<img src=x onerror="window.xss=1">`.


## Acceptance criteria

- [x] Test: the deployment page, the steps of a stage and the object list contain these values only escaped (no `<img` from data in the HTML, no value inside an `on...=` attribute or a `<script>`).
- [x] Test: no template uses `|safe` for data. Left: `flow_html`, `flow_javascript`, `run_stage_button`, `reset_stage_button`, which are HTML of `flowchart.py`; it escapes its values now and they are gone with the [stage flow](../features/web-ui-deployment-page.md).
- [x] Manual check in headless Chrome (no [browser tests](../features/web-ui-browser-tests.md) yet): the page, the steps, the object history and the processing history of a deployment with such values: `window.xss` stays undefined, the names are shown as text.
- [x] Manual check in headless Chrome: the switches of the objects `o'brien` and `<img src=x onerror="window.xss=1">` work.
- [x] Changelog entry.


## Decisions

* `escape_html` is in `web.deploy.js`.
* The inline handlers stay until the [scripts](../features/web-ui-scripts.md) step, but read their values with `this.dataset`.
* Not covered by an automatic test: the tables which JavaScript builds (object history, processing history). A test only checks that the scripts call `escape_html`.


## Non-goals

* Restricting the characters of object, stage or user names
* The Content-Security-Policy as second line of defence: [security headers](../features/web-ui-security-headers.md). This fix doesn't wait for it.


## Open questions

None.
