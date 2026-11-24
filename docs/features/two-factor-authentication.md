# Two-factor authentication (TOTP)

- **Status:** ready (implemented 2026-11-23, tested with `tests/test_two_factor.py`, `tests/test_web_browser_two_factor.py`. Open: the check with authenticator apps on a phone, and on IBM i)
- **Type:** feature (security)
- **Priority:** P1
- **Source:** Code review 2026-11-23 (user request: "add what is missing, e.g. 2FA")


## Current situation

* The login checks the IBM i user and password with an ODBC connect ([app_login.py:56](../../webapp/web_modules/app_login.py#L56)). There is no second factor.
* Whoever knows (or guesses, phishes, reads in a script) the password of an IBM i profile listed in i-Releaser can run deployments into production.
* Every wrong password reaches the IBM i and counts for `QMAXSIGN` (see [the login can disable IBM i profiles](../bugfixes/login-can-disable-ibm-i-profiles.md)).
* The login is done by the middleware for any `POST`, in one step ([minor web defects](../bugfixes/minor-web-defects-2026-11.md), item 1). A second step isn't possible today.


## Options

| Option | For | Against |
|---|---|---|
| **TOTP in i-Releaser** (authenticator app, RFC 6238) | Works on every IBM i release; only the standard library of Python (`hmac`, `hashlib`, `base64`, `struct`, `secrets`); the code can be checked *before* the IBM i sign-on | i-Releaser stores a secret per user; enrollment and recovery in i-Releaser |
| Integrated MFA of IBM i | No secret in i-Releaser; same factor as 5250 and ACS | Needs IBM i **7.6** ([IBM docs](https://www.ibm.com/docs/en/ssw_ibm_i_76/mfa/mfaoverview.htm)): installations start at 7.5. System-wide attribute `ADLSGNFAC(*ENABLED)` and `AUTHMTH(*TOTP)` per profile; support of the ODBC driver to be checked (IBM documents a [password with appended factor](https://www.ibm.com/support/knowledgecenter/ssw_ibm_i_76/mfa/mfapwdfactor.htm)) |
| Passkeys (WebAuthn) | Strongest, safe against phishing | Packages `webauthn`, `cryptography`, `cbor2`: `cryptography` needs Rust and probably doesn't build in PASE (as `pydantic` 2) |
| Single sign-on (OIDC) at the reverse proxy | Uses the company login and its MFA | Needs an identity provider and a proxy module; the IBM i user must be mapped; large change |

**Decision proposal: TOTP in i-Releaser.** Integrated MFA of IBM i as later option for 7.6 systems, see [non-goals](#non-goals).


## Requirements

### Login

1. The login has its own route: `GET /login` shows the form, `POST /login` checks it. No other path accepts credentials (see [minor web defects](../bugfixes/minor-web-defects-2026-11.md), item 1).
2. Order of the checks:
   1. user is listed in `user_permissions.json`, user and client are not blocked;
   2. if the user has 2FA: the **code is checked first, locally**. A wrong code ends the login: the IBM i sign-on isn't tried, so it doesn't count for `QMAXSIGN`;
   3. password with the ODBC connect ([in a thread, with timeout](../bugfixes/blocking-login-in-middleware.md)).
3. The form has the fields user, password and code (the code field is shown after the first step for users with 2FA, or always, see [open questions](#open-questions)). The error message is the same for every failure.
4. A wrong code counts as failed login (same lockout as a wrong password, but not for the IBM i counter).

### TOTP

5. RFC 6238 with HMAC-SHA1, 6 digits, 30 seconds: the defaults of all common apps (Microsoft/Google Authenticator, FreeOTP, 1Password, ...). Implemented with the standard library and tested with the test vectors of RFC 6238.
6. A code is accepted in the current, the previous and the next interval (clock difference). A code (interval) which has been used once is not accepted again for this user (replay).
7. Secret: 160 bits (`secrets.token_bytes(20)`), Base32 for the app.

### Enrollment and recovery

8. On the user page: "Set up two-factor authentication". i-Releaser shows the secret as QR code and as text (`otpauth://totp/i-Releaser:<user>?secret=...&issuer=i-Releaser`). It's active after the user has entered a valid code.
9. With the activation the user gets 10 recovery codes (shown once). Each can be used once instead of a code. They are stored as hashes. The user can create new ones (the old ones become invalid).
10. The user can turn off 2FA with a current code (unless the policy requires it).
11. An admin can reset the 2FA of a user (e.g. lost phone): the user sets it up again at the next login. Recorded in the [audit log](audit-log.md).

### Policy

12. Setting `C_2FA_POLICY`: `off` | `optional` (default) | `admins` (required for users with permission `admin`) | `required`. Also on the settings page (processing settings show how).
13. A user for whom 2FA is required but not set up goes to the setup page after the password and can't do anything else until it's set up.

### Step-up

14. These actions need a code which has been entered in the last `C_2FA_STEP_UP_MINUTES` (default 10) minutes, otherwise the page asks for it: create an API token, change permissions, change settings, reset the 2FA of another user, approval of the [four-eyes check](four-eyes-check.md).

### Storage

15. Table `user_mfa` in `var/app.sqlite`: user, secret, created, last used interval, recovery code hashes. The database file is only readable by the profile of i-Releaser (as today, `installation.md`). No encryption of the secret: the key would be on the same system (documented as decision).

### API tokens

16. API tokens don't need a code (they are a second secret already). Creating one needs step-up (requirement 14). See [API tokens outlive their user](../bugfixes/api-token-outlives-user.md).


## Acceptance criteria

- [x] Unit test: TOTP values of RFC 6238 Appendix B (SHA1) are computed correctly.
- [x] Test: with 2FA a wrong code doesn't call the ODBC connect (mocked connect isn't called).
- [x] Test: a code can't be used twice; a code of the previous interval is accepted.
- [x] Test: setup → activation only with a valid code; recovery code works once.
- [x] Test: policy `required`: a user without 2FA is sent to the setup page for every page and API call with session.
- [x] Test: creating a token without recent code asks for the code.
- [x] Test: an admin resets the 2FA of a user; non-admins can't.
- [x] Browser test: setup with QR code, login with code, recovery code.
- [ ] Checked with Microsoft Authenticator and one other app.


## Non-goals

* Integrated MFA of IBM i (7.6): later, as an option "pass the code to the IBM i" for installations which use it. Needs a test of the ODBC driver with an appended factor.
* Passkeys / WebAuthn, SMS, e-mail codes.
* Single sign-on.


## Decisions (2026-11-23)

* QR code with the package `qrcode` 8.2 (review OK, see [technik.md](../technik.md#package-prüfung)), as SVG data URI in an `<img>`.
* One login form with the field `Code (if you have set up two-factor authentication)`, always shown.
* Default policy: `optional` in `etc/constants.py` (existing installations keep working), `admins` in the template `etc/examples/settings.py` (new installations).
* The policy is shown on the settings page; it's changed in `etc/settings.py` only (no switch in the web app: it's a security setting of the installation).
* The code is checked before the IBM i sign-on but only used up after it, so a wrong password doesn't cost a recovery code.
* Wrong codes have their own limit (`C_2FA_MAX_FAILURES` within `C_LOGIN_BLOCK_MINUTES`); they don't count for the IBM i counter of the user.
* Removing a user (permissions page) also removes the two-factor authentication of the user.


## Open questions (answered 2026-11-23, the proposals)

* QR code: the package `qrcode` (`lincolnloop/python-qrcode`, pure Python, SVG without Pillow) needs a [package review](../technik.md#package-prüfung). Alternative without a package: only the secret as text and the `otpauth://` link (most apps accept both, but scanning is easier). Proposal: `qrcode`, if the review is OK.
* Code field always visible or only after the first step? Always visible is simpler (one form, one request) but shows the field to users without 2FA. Proposal: one form; "Code (if set up)".
* Default policy: `optional` or `admins`? Proposal: `admins` for new installations, `optional` for existing ones (changelog).
