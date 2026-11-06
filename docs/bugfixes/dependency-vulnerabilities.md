# Known vulnerabilities in dependencies

- **Status:** ready (only the install on IBM i is open)
- **Type:** security
- **Priority:** P1
- **Found:** 2026-11-01, `pip-audit -r requirements.txt`
- **Confidential:** don't publish before the fix is released


## Current situation

`pip-audit` reported 14 known vulnerabilities in `starlette 0.45.3` (pinned by `fastapi==0.115.8`). The audit job in `.github/workflows/tests.yml` failed.


## Decision (2026-11-05)

`pydantic` 2 doesn't install on IBM i (`pydantic-core` needs Rust), so FastAPI 0.162 is out.
Upgrade to `fastapi` 0.125.0, the newest with `pydantic` 1, and pin `starlette` 0.50.0.
The 5 advisories left are checked and ignored in the CI, the one which applies is mitigated in our code.
Details: [technik.md](../technik.md#known-vulnerabilities).


## Requirements

1. Upgrade FastAPI and `starlette` as far as `pydantic` 1 allows.
2. Check which of the remaining vulnerabilities apply to i-Releaser, and mitigate those.
3. All tests pass. Check the web app in a browser.


## Acceptance criteria

- [x] `pip-audit` reports only the 5 checked advisories, the CI ignores them with a reason.
- [x] PYSEC-2026-249: the login form is only read up to 4 KB and with a known length (`test_large_login_form_is_not_read`, `test_login_form_without_length_is_not_read`).
- [x] PYSEC-2026-161: fixed in [host-header-skips-login-check](host-header-skips-login-check.md).
- [x] All tests pass.
- [ ] The packages install on IBM i (`fastapi` 0.125.0 adds `annotated-doc`, pure Python).
- [ ] Web app checked in a browser.


## Non-goals

* Other changes of the web app
* Replacing FastAPI with plain Starlette (the way out if this line gets new advisories)


## Open questions

* ~~Can `pydantic` 2 be installed on IBM i?~~ No (checked 2026-11-04).
