# API tokens are weak

- **Status:** finished
- **Type:** security
- **Priority:** P1
- **Found:** 2026-10-23, code review
- **Confidential:** don't publish before the fix is released


## Current situation

`generate_new_user_key` ([app_login.py:63](../../webapp/web_modules/app_login.py#L63)):

* builds the key from 10 letters with `random.choice` (about 57 bits, from a generator which isn't meant for secrets);
* the token is the SHA-256 hex of that key. It looks like 256 bits but has only the 57 bits of the key.

`is_key_valid` compares the hashes with `==` in a loop over all users.

The route generates two keys per click and only returns the second one ([routes.py:166](../../webapp/routes/routes.py#L166)).


## Requirements

1. Tokens are created with the `secrets` module and have at least 256 bits (e.g. `secrets.token_urlsafe(32)`).
2. Only the SHA-256 hash of the token is stored (as today). The lookup is done by hash or compared with `hmac.compare_digest`.
3. One token per request of the user.
4. Existing tokens stay valid. The changelog advises to generate new ones.
5. The user page shows when the token was created (exists) and when it was used last.


## Acceptance criteria

- [x] Unit test: a new token has at least 43 characters (`token_urlsafe(32)`) and is different every time.
- [x] Unit test: a token of the old format is still accepted.
- [x] Unit test: one click writes one entry to `keys.json`, and the returned token is the one stored.
- [x] The last use is shown on the user page.


## Non-goals

* [Token in the header instead of the URL](api-token-stored-in-custom-data.md)


## Decisions

* Expiry or read-only tokens? **Not now.**
