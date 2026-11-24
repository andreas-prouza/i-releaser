# API tokens outlive their user

- **Status:** finished (2026-11-23; tested with `tests/test_review_2026_11.py`, `tests/test_two_factor.py`; requirement 6 not done, see decisions)
- **Type:** security
- **Priority:** P2
- **Found:** 2026-11-23, code review
- **Confidential:** don't publish before the fix is released


## Current situation

Tokens are stored per user in `webapp/etc/keys.json` ([app_login.py:118](../../webapp/web_modules/app_login.py#L118)). [API tokens are weak](weak-api-tokens.md) made them strong, but their life cycle is open:

* **No expiry.** A token is valid until the user creates a new one or deletes it.
* **The token stays when the user is removed.** `/api/save_permissions` doesn't touch `keys.json`. The token only stops working because the user isn't listed anymore ([app_login.py:159](../../webapp/web_modules/app_login.py#L159)).
  If a user with the same name is added again (e.g. a new colleague gets the same IBM i profile name), the old token works again.
* **A disabled or deleted IBM i profile** doesn't stop the token: it's never checked against the IBM i.
* **A token can create its own successor** (`/api/generate_user_key` accepts token requests, [routes.py:335](../../webapp/routes/routes.py#L335)). Whoever has a stolen token can replace it and lock out the owner.
* **Admins can see all tokens** (masked, [admin_view.py:51](../../webapp/web_modules/admin_view.py#L51)) **but can't revoke** a token of another user.
* Tokens of the old format (57 bits) are still accepted ([weak API tokens](weak-api-tokens.md), requirement 4).


## Requirements

1. Removing a user (`save_permissions`) deletes their token. Adding a user never revives an old one.
2. Admins can revoke the token of any user on the settings page (`DELETE`-like `POST /api/revoke_token/{user}`), recorded in the [audit log](../features/audit-log.md).
3. `/api/generate_user_key` and `/api/drop_key` only with a session (not with a token). With [2FA](../features/two-factor-authentication.md): only after a recent second factor (step-up).
4. Tokens of the old format are no longer accepted from version X (one release with a warning in the log and on the user page before).
5. A token gets an expiry date (`C_TOKEN_MAX_DAYS`, default 365, 0 = no expiry). The user page shows it; 14 days before, the page shows a warning.
6. When a token is used, i-Releaser checks at most once per day whether the IBM i profile still exists and is `*ENABLED` (needs a query of `QSYS2.USER_INFO` under the profile of i-Releaser). A disabled profile disables the token.


## Acceptance criteria

- [x] Test: removing a user deletes their entry in `keys.json`; adding the same name again doesn't make the old token valid.
- [x] Test: an admin can revoke the token of another user; a non-admin can't.
- [x] Test: `/api/generate_user_key` with a token gets `403`.
- [x] Test: an expired token gets `401` with the message "token expired".
- [ ] Test (`ibmi`): a token of a disabled profile is refused.


## Non-goals

* Several tokens per user, read-only tokens, scopes: part of [API v2](../features/api-v2.md).


## Decisions (2026-11-23)

* Requirement 6 (check of the IBM i profile) is not done: it can't be tested without an IBM i and needs authority to the profiles. The expiry limits how long a token of a disabled profile works; removing the user in i-Releaser deletes the token at once.
* Requirement 4: tokens of the old format are accepted with a warning in the log and on the user page; they will be refused by the next major version.
* Tokens of older versions without expiry get it at their first use with this version (`C_TOKEN_MAX_DAYS` from then), so integrations don't stop at the update.
* A token whose user is no longer listed (also removed in the file by hand) is deleted when it's used.
* Removing a user also removes the two-factor authentication of the user.


## Open questions (answered 2026-11-23)

* Requirement 6: `QSYS2.USER_INFO` only returns profiles the profile of i-Releaser has `*READ` authority to. Is that acceptable for installations? Alternative: no check, rely on the expiry.
* Default of `C_TOKEN_MAX_DAYS`: 365? The OBI extension must then show the expiry.
