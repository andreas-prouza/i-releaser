# Known vulnerabilities in dependencies

- **Status:** draft
- **Type:** security
- **Priority:** P1
- **Found:** 2026-11-01, `pip-audit -r requirements.txt`
- **Confidential:** don't publish before the fix is released


## Current situation

`pip-audit` reports 14 known vulnerabilities in one package: `starlette 0.45.3` (PYSEC-2026-161, -248, -249, -1941, -1942, -2280, -2281). The fixes are in versions 0.47.2 to 1.3.1.

`starlette` is pinned by `fastapi==0.115.8`. Upgrading it means upgrading FastAPI, which may need a newer `pydantic` than the pinned `1.10.21`.

The audit job in `.github/workflows/tests.yml` fails until this is fixed.


## Requirements

1. Upgrade FastAPI and with it `starlette`, so `pip-audit -r requirements.txt` reports nothing.
2. Check which of the vulnerabilities apply to i-Releaser, to decide how urgent it is.
3. All tests pass. Check the web app in a browser.


## Acceptance criteria

- [ ] `.venv/bin/pip-audit -r requirements.txt` reports no vulnerabilities.
- [ ] All tests pass.
- [ ] The packages still install on IBM i (`pydantic` 2 needs a compiled package, `pydantic-core`).


## Non-goals

* Other changes of the web app


## Open questions

* Can `pydantic` 2 be installed on IBM i? If not, which is the newest FastAPI which works with `pydantic` 1?
