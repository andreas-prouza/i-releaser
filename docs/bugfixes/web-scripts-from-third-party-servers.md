# The web app loads scripts from third-party servers

- **Status:** ready
- **Type:** security
- **Priority:** P1
- **Found:** 2026-11-16, analysis of the web front end; reproduced in Chrome on a copy of the web app
- **Confidential:** don't publish before the fix is released


## Current situation

Some pages load scripts and styles from other servers, although most of the files also exist in `webapp/static/`:

| Page | Loads | From | Where |
|---|---|---|---|
| Deployments (`/`), object list | jQuery **without a version** (always the newest), bootstrap-table 1.22.1 (script, style, 2 extensions), jquery-resizable-columns 0.2.3 | `cdn.jsdelivr.net`, `unpkg.com` | [list-deployments.html:10](../../webapp/templates/overview/list-deployments.html#L10), [:99](../../webapp/templates/overview/list-deployments.html#L99), [list-objects.html:10](../../webapp/templates/overview/list-objects.html#L10), [:83](../../webapp/templates/overview/list-objects.html#L83) |
| Workflows | `run_prettify.js` of `google/code-prettify`, branch `master` (the project is archived) | `cdn.rawgit.com` (shut down in 2019, redirects to `cdn.jsdelivr.net`) | [workflows.html:72](../../webapp/templates/admin/workflows.html#L72) |
| Deployment | `raphael.min.js` 2.3.0 over **`http://`**. Nothing uses it. | `cdnjs.cloudflare.com` | [show-deployment.html:153](../../webapp/templates/overview/show-deployment.html#L153) |
| `/docs`, `/redoc` (logged-in users) | Swagger UI 5, ReDoc 2 (no exact version), fonts, favicon | `cdn.jsdelivr.net`, `fonts.googleapis.com`, `fastapi.tiangolo.com` | Defaults of FastAPI ([initial.py](../../webapp/routes/initial.py)), code review |
| `base2.html` (not used) | AdminLTE 3.2 | `cdn.jsdelivr.net` | [base2.html:18](../../webapp/templates/base2.html#L18) |

Effects:

* A script runs with the session of the user who opens the page. Whoever controls one of these servers or packages (or, for `http://`, the network) can run stages, cancel deployments and, for an administrator, change permissions.
  No version is fixed for jQuery and `code-prettify`, and no integrity check (`integrity="sha384-..."`) is used.
* If the browser can't reach the internet (usual for an IBM i in the intranet), the deployment list and the object list have no sorting, filters or paging: the local copy of bootstrap-table isn't used on these pages.
* A page served with `https://` doesn't load the `http://` script at all (blocked by the browser).
* The servers learn the address of the browser and the host name of the i-Releaser installation.
* jQuery is loaded twice (3.7.1 local, the newest from the CDN), bootstrap-table exists in two versions (1.23.2 local, 1.22.1 CDN).


## Requirements

1. No page of the web app loads anything from another server. This includes `/docs`.
2. The lists use the local bootstrap-table (script, style, filter extension). The resizable extension and `jquery-resizable-columns` are removed: no table turns it on.
3. `raphael.min.js` and `base2.html` are removed. The workflows page highlights JSON with the local Prism (already used by the deployment page) instead of `code-prettify`.
4. `/docs` loads Swagger UI from local files (`swagger-ui-dist`, pinned, see [package review](../technik.md#package-prüfung)). `/redoc` is turned off.
5. Libraries are pinned files in `webapp/static/` (see [static assets](../features/web-ui-static-assets.md)).


## Acceptance criteria

- [ ] Test: every page (`/`, `/list-objects`, `/workflows`, `/settings`, `/user`, `/log/...`, a deployment, login, error, `/docs`) has no `src`, no `href` of a `link`, and no `url(...)` or `@import` which points to another server.
- [ ] Test: no template, script or stylesheet of the web app (libraries excluded) contains `http://` or `https://` in a `script`, `link` or `import`.
- [ ] Test: `/redoc` → 404.
- [ ] The deployment list and the object list sort, filter and page without internet access (browser test or manual check).
- [ ] Changelog entry.


## Non-goals

* A Content-Security-Policy, which forbids such requests in general: [security headers](../features/web-ui-security-headers.md)
* Links to other sites (`<a href>`), e.g. to prouza.at


## Open questions

None. (If `/docs` isn't needed on a server, turning it off is the smaller change. The decision of [API consistency](../features/api-consistency.md) was to keep it.)
