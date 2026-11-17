# Security headers: Content-Security-Policy

- **Status:** draft
- **Type:** security
- **Priority:** P2
- **Source:** [Modernization of the web front end](web-ui-modernization.md), step 9
- **Depends on:** all pages follow the rules of [scripts in files](web-ui-scripts.md#rules) (steps 3 – 8)


## Current situation

The responses of the web app have no security headers, only `Cache-Control` and the session cookie:

```
content-type: text/html; charset=utf-8
set-cookie: session_id=...; HttpOnly; Max-Age=3600; Path=/; SameSite=lax
cache-control: max-age=0
```

* Nothing limits where a page may load scripts from, and every inline script runs. A value which gets into a page as HTML is a script of the page (see [bugfix](../bugfixes/web-values-run-as-script.md)).
* A page of the web app can be shown in a frame of another site. `SameSite=Lax` keeps the session cookie away from frames of foreign sites, but not from other hosts of the same domain.
* The type of a response can be guessed by the browser (`X-Content-Type-Options` is missing).

A Content-Security-Policy is not possible today: every page depends on inline scripts and inline handlers.


## Requirements

1. Every HTML response has

   ```
   Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline';
       img-src 'self' data:; font-src 'self'; connect-src 'self'; media-src 'none'; object-src 'none';
       base-uri 'self'; form-action 'self'; frame-ancestors 'none'
   ```

   * `script-src 'self'`: only script files of the web app. No inline scripts, no handlers in attributes, no `eval`.
   * `style-src 'unsafe-inline'`: SweetAlert2 and bootstrap-table set `style` attributes. Styles can't run code; a stricter value is a non-goal.
2. Every response has `X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin` and `X-Frame-Options: DENY`.
3. `C_CSP_REPORT_ONLY = True` in `etc/settings.py` sends the policy as `Content-Security-Policy-Report-Only`: the browser reports violations in its console, but doesn't block them. For the time an installation needs to move its custom templates. The default is `False`, and the web app logs a warning at its start if it's `True`.
4. `/docs` works with the policy (Swagger UI from local files, see [bugfix](../bugfixes/web-scripts-from-third-party-servers.md)). If it needs an inline script, only this path gets a policy with a nonce.
5. `LEGACY_TEMPLATES` of the rule test is empty and removed.
6. `Strict-Transport-Security` is set by the reverse proxy: an example is added to [installation.md](../installation.md#reverse-proxy), and a line to the [production checklist](../installation.md#production-checklist).


## Acceptance criteria

- [ ] Test: the headers of a page, the login page, an error page, a JSON response, a static file and `/docs`.
- [ ] Test: `C_CSP_REPORT_ONLY = True` → `Content-Security-Policy-Report-Only`, no `Content-Security-Policy`, a warning in the log.
- [ ] Test: no template contains an inline script, an `on...=` attribute or a `javascript:` URL (the rule test without exceptions).
- [ ] Browser test (or manual check of every page with the console open, see [browser tests](web-ui-browser-tests.md)): every page and every dialog (run a stage, logs, custom data, permissions, token, start of a workflow) without a violation of the policy.
- [ ] Browser test (or manual check): a custom template with an inline script is blocked; the example of [scripts.md](../scripts.md#web-app-extensions) with a script file works.
- [ ] Docs: [technik.md](../technik.md) (decision, like `CSRF`), [installation.md](../installation.md), [scripts.md](../scripts.md#web-app-extensions).
- [ ] Changelog, `Before you update`: custom templates need script files; `C_CSP_REPORT_ONLY` for the transition.


## Non-goals

* `style-src` without `'unsafe-inline'`
* An endpoint which collects reports of violations
* `Permissions-Policy`, `Cross-Origin-*` headers


## Open questions

1. `C_CSP_REPORT_ONLY` as a way to keep old custom templates working for a while (**recommended**), or no switch?
2. Question 1 of [scripts in files](web-ui-scripts.md#open-questions) (script files or a nonce for custom templates) decides whether the policy contains a nonce.
