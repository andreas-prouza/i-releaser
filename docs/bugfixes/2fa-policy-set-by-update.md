# The update to 4.1.0 can turn on two-factor authentication

- **Status:** finished (2026-11-24; tested with `tests/test_two_factor.py`)
- **Type:** bug
- **Priority:** P2
- **Found:** 2026-11-24, on an installation after the update to 4.1.0


## Current situation

The [two-factor authentication](../features/two-factor-authentication.md) decided: `optional` in `etc/constants.py` for existing installations, `admins` in the template `etc/examples/settings.py` for new ones.

`setup3.13.sh` copies each template which doesn't exist yet in `etc/`. It can't tell a new installation from an update:
an existing installation without `etc/settings.py` (it's optional) got the template with `C_2FA_POLICY = 'admins'` during the update.
Each admin then had to set up 2FA at the next login, although the changelog said that existing installations keep `optional`.


## Requirements

1. The template sets no policy: the line is a comment with the recommendation `admins`.
2. `installation.md` (production checklist) and the changelog say that the default is `optional`, also with the template.


## Acceptance criteria

- [x] Test: `etc/examples/settings.py` doesn't set `C_2FA_POLICY` (`tests/test_two_factor.py`).


## Decisions (2026-11-24)

* New installations start with `optional` too. The production checklist of `installation.md` asks to set `admins` or `required`. This replaces the decision "`admins` in the template" of [two-factor authentication](../features/two-factor-authentication.md#decisions-2026-11-23).
