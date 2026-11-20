# Static files: local, pinned, cleaned up

- **Status:** finished (2026-11-17; tested with `tests/test_web_pages.py`, every page and dialog looked at in headless Chrome on a copy of the web app, not on IBM i)
- **Type:** improvement
- **Priority:** P2
- **Source:** [Modernization of the web front end](web-ui-modernization.md), step 1
- **Depends on:** [Scripts from third-party servers](../bugfixes/web-scripts-from-third-party-servers.md)


## Current situation

`webapp/static` has 35 MB in 186 tracked files. The pages use less than 2 MB of it.

| What | Size | Used |
|---|---|---|
| Font Awesome 7.2.0 (`css`, `js`, `metadata`, `scss`, `webfonts`) | 22 MB | 3 icons: `fa-plus`, `fa-trash`, `fa-ban` (10 places) |
| Bootstrap 5.3.3: all variants (`grid`, `reboot`, `utilities`, `rtl`, not minified, source maps) | 9.2 MB | `bootstrap.min.css`, `bootstrap.bundle.min.js`, Bootstrap Icons, bootstrap-table |
| Fonts: Uni Sans, Open Sans, icomoon | 2.6 MB | no |
| `rist.css` (11,335 lines), `mobile.css`, `tablet.css`, `desktop.css`, `scrollbar/` | 0.3 MB | no |
| `flowchart.min.js`, `raphael.min.js`, `bootstrap-table-de.js`, `bootstrap-table-en.js` | 0.2 MB | no |
| `json.js` | – | loaded by the deployment page, never called |
| `popper.min.js` | – | loaded on every page, but `bootstrap.bundle.min.js` contains Popper |
| `bootstrap-table-resizable.min.js` | – | loaded, but no table turns it on, and the library it needs isn't there |
| Images `inspect2.png`, `logo-2.png`, `logo-3.png`, `run-red.png` | – | no |
| `global.css`: `.blueTable`, `.divTable` (64 of 99 lines) | – | no |
| Templates `base2.html`, `overview/details/quotes.html` | – | no |

Other findings:

* The libraries in use were never checked against the criteria of [architektur.md](../architektur.md): the [package review](../technik.md#package-prüfung) only lists Python packages.
* SweetAlert2 11.7.20 contains code which has nothing to do with dialogs: for browsers with a Russian language setting on `.ru`, `.su`, `.by` and `.рф` hosts it blocks the page after three days and plays audio from another server (in `sweetalert2.all.min.js`, search for `swal-initiation`). It has no effect on other installations.
* `sweetalert2.all.min.js` adds its stylesheet with a `<style>` element at run time, which matters for the [Content-Security-Policy](web-ui-security-headers.md).
* Icons exist in three kinds: Bootstrap Icons (font), Font Awesome (font), and the same Bootstrap Icons copied as inline SVG into the templates.


## Requirements

1. `webapp/static` only contains files which a page uses. The files and templates of the table above are removed.
2. One icon set: Bootstrap Icons. The three Font Awesome icons are replaced (`bi-plus-lg`, `bi-trash`, `bi-slash-circle`), Font Awesome is removed.
3. Each library exists once: the minified file and its license. `popper.min.js` is not loaded any more.
4. SweetAlert2 is loaded as `sweetalert2.min.js` and `sweetalert2.min.css` (no `<style>` at run time).
5. The paths of the files which stay don't change. Custom templates use them (e.g. `assets/img/undo.png`, `assets/js/web.deploy.js`).
6. [technik.md](../technik.md#package-prüfung) gets a table of the front end libraries: name, version, used for, license, repository, stars, forks, result. Numbers of 2026-11-16:

   | Library | Version today | Repository | Stars | Forks | License |
   |---|---|---|---|---|---|
   | Bootstrap | 5.3.3 | `twbs/bootstrap` | 175,072 | 79,484 | MIT |
   | Bootstrap Icons | 1.11.3 | `twbs/icons` | 8,184 | 1,122 | MIT |
   | bootstrap-table | 1.23.2 | `wenzhixin/bootstrap-table` | 11,812 | 4,330 | MIT |
   | jQuery (needed by bootstrap-table) | 3.7.1 | `jquery/jquery` | 59,898 | 20,685 | MIT |
   | SweetAlert2 | 11.7.20 | `sweetalert2/sweetalert2` | 18,103 | 1,615 | MIT |
   | Prism | 1.30.0 | `PrismJS/prism` | 13,070 | 1,411 | MIT |

   The note about SweetAlert2 above is part of its result.
7. [technik.md](../technik.md) describes how a library is updated: where the file comes from, which files are replaced, the table.
8. The libraries are updated to the newest patch version of their line (Bootstrap 5.3.x, bootstrap-table 1.x, SweetAlert2 11.x), if the pages work unchanged.


## Acceptance criteria

- [x] Test: every file a rendered page refers to (`src`, `href`) exists in `webapp/static`.
- [x] Test: every file in `webapp/static` is referred to by a template, a stylesheet or a script. Exceptions are a list in the test (files kept for custom templates, licenses).
- [x] Test: no template uses a `fa-` class.
- [x] `webapp/static` is smaller than 2 MB, without Swagger UI: 1.3 MB, plus 1.9 MB of Swagger UI for `/docs` (came with the [bugfix](../bugfixes/web-scripts-from-third-party-servers.md) after this criterion was written). Before: 35 MB.
- [x] All pages look and work as before: manual check in headless Chrome of every page, sorting, filters and paging of the tables, and the dialogs (run a stage, logs, token, permissions). No error in the console.
- [x] Docs: [technik.md](../technik.md). Changelog: removed files, for owners of custom templates.


## Decisions

* Versions now: Bootstrap 5.3.9, Bootstrap Icons 1.13.2, bootstrap-table 1.28.0, SweetAlert2 11.26.25; jQuery 3.7.1 and Prism 1.30.0 were current.
* SweetAlert2 11.26.25 doesn't contain the code for Russian hosts any more (checked in the file).
* SweetAlert2 is loaded in `<head>`: scripts inside the content of a page (also custom templates) use `Swal` while the page is read.
* The stylesheet of the icons is `bootstrap-icons.min.css` (the only path which changed). `sweetalert2.all.min.js` is replaced by `sweetalert2.min.js`: custom templates which load it themselves have to remove that line, `Swal` comes from `base.html`.
* Licenses of the libraries: `webapp/static/assets/licenses/`.
* SweetAlert2 11.26 resolves a dialog as dismissed (without `dismiss` reason) when another dialog replaces it; 11.7 never resolved it. The steps window of the deployment page reset its state then, so it didn't open again after a log. Found by the [browser tests](web-ui-browser-tests.md) on 2026-11-19 and fixed: `show_stage_steps` ignores this case.


## Non-goals

* New styles and layout: [layout](web-ui-layout.md)
* Caching of static files in the browser. Today every file is asked for again on each page (`Cache-Control: max-age=0`, [webmiddleware.py:36](../../webapp/routes/webmiddleware.py#L36)). Possible later with a version in the URL.
* Replacing SweetAlert2 or jQuery


## Open questions

None.
