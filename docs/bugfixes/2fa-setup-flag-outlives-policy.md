# A loosened 2FA policy doesn't count for sessions which have to set it up

- **Status:** finished (2026-11-24; tested with `tests/test_two_factor.py`)
- **Type:** bug
- **Priority:** P3
- **Found:** 2026-11-24, code review (while helping an installation after the update to 4.1.0)


## Current situation

If [two-factor authentication](../features/two-factor-authentication.md) is required for a user who hasn't set it up, the login stores the flag `mfa_setup_required` in the session ([two_factor.py](../../webapp/web_modules/two_factor.py), `after_login`).
The middleware sends every request of this session to the page `My account` while the flag is set ([webmiddleware.py](../../webapp/routes/webmiddleware.py), `check_session`).

The flag was only removed by the setup. If an admin loosened `C_2FA_POLICY` (e.g. to `off` or `optional`) and restarted the web app, or removed the permission `admin` of the user with the policy `admins`,
the session stayed on the setup page until the user logged out and in again.


## Requirements

1. While the flag is set, each request checks again whether the setup is still required (policy, permission `admin`, set up in another session). If not, the flag is removed from the session.
2. Sessions without the flag aren't changed: no additional work for them.


## Acceptance criteria

- [x] Test: login with policy `required` (setup page), restart with `off` and with `optional`: the same session gets the pages, the flag is gone from the session file.


## Non-goals

* The other direction: a policy which is made stricter counts at the next login of a user, not for sessions which exist already (it would need a check of the database for each request). The sessions end after `SESSION_LIFETIME` without request, after `SESSION_MAX_LIFETIME` in any case.
