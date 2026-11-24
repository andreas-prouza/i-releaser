import asyncio, os, logging, re, secrets
import hashlib
import datetime
from concurrent.futures import ThreadPoolExecutor

from fastapi import Request
from starlette.concurrency import run_in_threadpool

from modules import current_user, errors, files, permission_config
from modules.db import api_token_data, login_failure_data
from modules.db_deployment.connection import quote_odbc_value
from etc import constants, db_config, web_constants
from web_modules import audit, two_factor


#cnxn = pyodbc.connect('DSN=*LOCAL')
#cursor = cnxn.cursor()


# The same text for a wrong password and a block: it doesn't tell which users exist or are blocked
LOGIN_FAILED_TEXT = ("Login failed. Check your user, password and code (if you have set up two-factor authentication), "
                     "and if you have access to i-Releaser. After several failed logins the login is blocked: ask an administrator to unblock it.")
LOGIN_BLOCKED_TEXT = LOGIN_FAILED_TEXT

# Plain HTTP to another host than localhost, with C_COOKIE_SECURE = True (docs/bugfixes/secure-cookie-over-http-without-message.md)
COOKIE_NEEDS_HTTPS_TEXT = ("The login can't work with this address: it uses plain HTTP, and i-Releaser only sends its session cookie over HTTPS. "
                           "Open i-Releaser with https://, or ask an administrator to set C_COOKIE_SECURE = False in webapp/etc/global_cfg.py.")

_USER_PROFILE = re.compile(r'[A-Za-z$#@][A-Za-z0-9$#@_]{0,9}')

# The last use of a token isn't more exact than this
KEY_LAST_USED_INTERVAL_SECONDS = 60

# Sign-ons on the IBM i run in these threads, not on the event loop (docs/bugfixes/blocking-login-in-middleware.md).
# A sign-on which hangs keeps its thread until the ODBC login timeout ends it.
_sign_on_executor = ThreadPoolExecutor(max_workers=max(1, constants.C_LOGIN_MAX_PARALLEL), thread_name_prefix='login')
# Logins which are waiting for the IBM i, in this process (only changed on the event loop)
_active_logins = 0

# SQLSTATE of pyodbc errors when the login timeout has expired: the IBM i hasn't answered, the password hasn't been checked
TIMEOUT_SQLSTATES = ('HYT00', 'HYT01')



def is_local_debugging() -> bool:
    """Developers can log in without a password"""
    return os.environ.get("I_RELEASER_LOCAL_DEBUGGING", "False").lower() == "true"



def get_connection_string(user: str, password: str) -> str:

    driver = db_config.DATABASES['IBM_I']['DRIVER']
    host = db_config.DATABASES['IBM_I']['HOST']

    return f"driver={quote_odbc_value(driver)};system={quote_odbc_value(host)};uid={quote_odbc_value(user)};pwd={quote_odbc_value(password)}"



def is_user_allowed_to_login(user: str, password: str) -> bool:
    """Checks everything which can be checked without trying to connect. Each failed connect counts for the IBM i profile."""

    if not _USER_PROFILE.fullmatch(user):
        return False

    if any(ord(char) < 32 for char in password):
        return False

    return user.lower() in [x.lower() for x in permission_config.PermissionKonfig.get_user_list()]



def sign_on(user: str, password: str) -> None:
    """Checks user and password on the IBM i. Blocking: runs in a thread of `_sign_on_executor`.

    Raises:
        Exception: If the sign-on fails
    """

    if is_local_debugging():
        return

    import pyodbc
    conn = pyodbc.connect(get_connection_string(user, password), timeout=constants.C_LOGIN_TIMEOUT_SECONDS)
    conn.close()



async def check_sign_on(user: str, password: str) -> bool|None:
    """
    Returns:
        bool|None: True if the sign-on succeeded, False if it failed, None if the IBM i didn't answer in time

    Raises:
        errors.Service_Unavailable_Error: Too many logins at the same time
    """

    global _active_logins

    if _active_logins >= constants.C_LOGIN_MAX_PARALLEL:
        raise errors.Service_Unavailable_Error("Too many logins at the same time. Please try again in a moment.")

    _active_logins += 1
    try:
        loop = asyncio.get_running_loop()
        # A bit longer than the ODBC login timeout: the driver ends the sign-on first, if it can
        await asyncio.wait_for(loop.run_in_executor(_sign_on_executor, sign_on, user, password), timeout=constants.C_LOGIN_TIMEOUT_SECONDS + 2)
        return True

    except asyncio.TimeoutError:
        logging.warning(f"Sign-on of {user=} on the IBM i: no answer within {constants.C_LOGIN_TIMEOUT_SECONDS} seconds")
        return None

    except Exception as e:
        if e.args and e.args[0] in TIMEOUT_SQLSTATES:
            logging.warning(f"Sign-on of {user=} on the IBM i: login timeout ({e.args[0]})")
            return None

        logging.info(f"Sign-on of {user=} failed: {type(e).__name__}")
        return False

    finally:
        _active_logins -= 1



async def login(request: Request, user: str, password: str, code: str|None=None) -> bool:
    """
    Logs the user in with the IBM i user and password, and the code of the authenticator app if the user has
    two-factor authentication. The code is checked first: without it, the password doesn't reach the IBM i (QMAXSIGN).
    The blocking parts run in threads.
    If it fails, `request.state.login_error` contains the text for the login page (no session is stored for it).

    Raises:
        errors.Service_Unavailable_Error: Too many logins at the same time
    """

    session = request.state.session
    client = request.client.host if request.client else 'unknown'

    if await run_in_threadpool(login_failure_data.is_blocked, user.lower(), client):
        logging.warning(f"Login blocked for {user=}, {client=}")
        await run_in_threadpool(audit.record, request, 'login_blocked', None, None, 'failed', user.lower())
        request.state.login_error = LOGIN_BLOCKED_TEXT
        return False

    if not is_user_allowed_to_login(user, password):
        logging.info(f"Login failed for {user=}, {client=}: user not allowed or invalid input")
        await run_in_threadpool(login_failure_data.add_failure, user.lower(), client, False)
        await run_in_threadpool(audit.record, request, 'login_failed', None, {'reason': 'user not allowed or invalid input'}, 'failed', user.lower())
        request.state.login_error = LOGIN_FAILED_TEXT
        return False

    code_ok, code_match = await run_in_threadpool(two_factor.check_login_code, user.lower(), code)

    if not code_ok:
        logging.info(f"Login failed for {user=}, {client=}: code of the two-factor authentication")
        await run_in_threadpool(login_failure_data.add_failure, user.lower(), client, False)
        await run_in_threadpool(audit.record, request, 'login_failed', None, {'reason': 'code of the two-factor authentication'}, 'failed', user.lower())
        request.state.login_error = LOGIN_FAILED_TEXT
        return False

    logging.debug(f"Try to login; {user=}")
    result = await check_sign_on(user, password)

    if result is not True:
        # Only a sign-on which the IBM i has refused counts for the user (QMAXSIGN), not one without answer
        await run_in_threadpool(login_failure_data.add_failure, user.lower(), client, result is False)
        await run_in_threadpool(audit.record, request, 'login_failed', None, {'reason': 'password' if result is False else 'no answer of the IBM i'}, 'failed', user.lower())
        request.state.login_error = LOGIN_FAILED_TEXT
        return False

    user = user.lower()

    # Used up only now: a wrong password doesn't cost a recovery code. Fails if the same code has been used meanwhile.
    if code_match is not None and not await run_in_threadpool(two_factor.use_login_code, user, code_match):
        request.state.login_error = LOGIN_FAILED_TEXT
        return False

    # A session id which has been known before must not be valid after the login
    session.regenerate()
    session['is_logged_in'] = True
    session['current_user'] = user
    current_user.set_user(user)
    await run_in_threadpool(login_failure_data.clear_failures, user, client)
    await run_in_threadpool(two_factor.after_login, session, user, code_match)
    logging.info(f"Login of user {user} from {client}{' with two-factor authentication' if code_match else ''}")
    await run_in_threadpool(audit.record, request, 'login', None,
                            {'two_factor': code_match is not None, 'recovery_code': code_match is not None and code_match[0] == 'recovery'}, 'ok', user)
    return True



def check_login_settings() -> None:
    """Warns if failed logins in i-Releaser can disable IBM i profiles (IBM default of QMAXSIGN: 3)"""

    if constants.C_LOGIN_MAX_FAILURES >= 3:
        logging.warning(f"C_LOGIN_MAX_FAILURES = {constants.C_LOGIN_MAX_FAILURES}: failed logins in i-Releaser can disable IBM i profiles "
                        "if the system value QMAXSIGN is 3 (the default). Keep it below QMAXSIGN, see docs/installation.md.")



#-----------------------------------------------------------------------------------------------
# API tokens (docs/features/api-v2.md#tokens): several per user in the table api_tokens, before one in webapp/etc/keys.json
#-----------------------------------------------------------------------------------------------

# The token of the Web API v1 (generate_user_key replaces it, drop_key deletes it), also the name of a token taken over from keys.json
V1_TOKEN_NAME = 'API token'
MAX_TOKENS_PER_USER = 20
MAX_TOKEN_NAME_LENGTH = 64
# Recognizable in logs and by secret scanners
TOKEN_PREFIX = 'irt_'

# Tokens before 2026-10 (docs/bugfixes/weak-api-tokens.md): the SHA-256 hex of 10 letters. Still accepted, with a warning.
_LEGACY_TOKEN = re.compile(r'[0-9a-f]{64}')

TOKEN_EXPIRES_SOON_DAYS = 14



def get_keys_lock_file() -> str:
    return f"{web_constants.C_KEYS_FILE}.lock"



def hash_key(key: str) -> str:
    return hashlib.sha256(bytes(key, 'utf-8')).hexdigest()



def mask_key(key: str) -> str:
    return "*" * 8 + key[-6:]



def _utc(value) -> str|None:
    """A time of keys.json (local time without zone) in UTC"""

    if not value:
        return None
    try:
        return datetime.datetime.fromisoformat(str(value)).astimezone(datetime.timezone.utc).isoformat(timespec='seconds')
    except ValueError:
        return None



def migrate_keys_file() -> int:
    """
    Takes over the tokens of webapp/etc/keys.json (one per user, before 2026-11) into the table api_tokens and renames the file
    to keys.json.migrated. Each keeps its hash, expiry and last use, with the name 'API token' and the scope `write`.
    At the start of the web app, and when the file appears again (e.g. restored from a backup).

    Returns:
        int: The number of tokens taken over
    """

    path = web_constants.C_KEYS_FILE
    if not os.path.exists(path):
        return 0

    with files.lock(get_keys_lock_file()):
        # Another worker may have done it meanwhile
        if not os.path.exists(path):
            return 0

        keys = files.getJson(path, retry=True) or {}
        count = 0

        for user, key in keys.items():
            if not isinstance(key, dict) or not key.get('key'):
                continue
            if api_token_data.add(user, V1_TOKEN_NAME, key['key'], key.get('orig_key_masked') or '', api_token_data.WRITE, _utc(key.get('expires')),
                                  created_at=_utc(key.get('date')), last_used_at=_utc(key.get('last_used')), legacy=bool(key.get('legacy'))) is not None:
                count += 1

        os.replace(path, f"{path}.migrated")

    logging.warning(f"{count} API tokens taken over from {path} into the database. The file is renamed to {path}.migrated")
    return count



def get_token_expiry(now: datetime.datetime|None=None, days: int|None=None) -> str|None:
    """When a token which is created now expires: after `days` (default and maximum C_TOKEN_MAX_DAYS, 0: never), UTC"""

    days = constants.C_TOKEN_MAX_DAYS if days is None else days
    if not days:
        return None

    return ((now or datetime.datetime.now(datetime.timezone.utc)) + datetime.timedelta(days=days)).isoformat(timespec='seconds')



def check_token_name(name) -> str:

    if not isinstance(name, str) or not name.strip():
        raise errors.Invalid_Input_Error("The token needs a name")

    name = name.strip()
    if len(name) > MAX_TOKEN_NAME_LENGTH or any(ord(c) < 32 or ord(c) == 127 for c in name):
        raise errors.Invalid_Input_Error(f"The name of a token has at most {MAX_TOKEN_NAME_LENGTH} characters, without control characters")

    return name



def create_token(user: str, name: str, scope: str=api_token_data.WRITE, days: int|None=None) -> tuple[str, dict]:
    """
    Returns:
        tuple: the token (shown once, only its hash is stored), its row

    Raises:
        errors.Invalid_Input_Error: name, scope or days
        errors.Conflict_Error: the user has a token of this name, or too many tokens
    """

    name = check_token_name(name)

    if scope not in api_token_data.SCOPES:
        raise errors.Invalid_Input_Error(f"The scope has to be one of {', '.join(api_token_data.SCOPES)}")

    max_days = constants.C_TOKEN_MAX_DAYS
    if days is not None and (isinstance(days, bool) or not isinstance(days, int) or days < 1 or (max_days and days > max_days)):
        raise errors.Invalid_Input_Error(f"A token expires after 1 to {max_days} days (C_TOKEN_MAX_DAYS)" if max_days else "'expires_in_days' has to be 1 or more")

    if len(api_token_data.get_of_user(user)) >= MAX_TOKENS_PER_USER:
        raise errors.Conflict_Error(f"You have {MAX_TOKENS_PER_USER} tokens. Delete one first.")

    token = TOKEN_PREFIX + secrets.token_urlsafe(32)
    token_id = api_token_data.add(user, name, hash_key(token), mask_key(token), scope, get_token_expiry(days=days))

    if token_id is None:
        raise errors.Conflict_Error(f"You have a token named '{name}' already")

    logging.info(f"API token '{name}' ({scope}) created for user {user.lower()}")
    return token, api_token_data.get(token_id)



def generate_new_user_key(request: Request) -> str:
    """Web API v1: replaces the token 'API token' of the user (scope write)"""

    user = request.state.session['current_user']
    api_token_data.delete_of_user(user, V1_TOKEN_NAME)
    return create_token(user, V1_TOKEN_NAME)[0]



def drop_token_of(user: str) -> bool:
    """Deletes all tokens of a user (revoked by an admin, or the user has been removed)

    Returns:
        bool: False if the user has no token
    """

    return api_token_data.delete_of_user(user) > 0



def drop_user_key(request: Request) -> None:
    """Web API v1: deletes the token 'API token' of the user"""

    api_token_data.delete_of_user(request.state.session['current_user'], V1_TOKEN_NAME)



def is_key_valid(request: Request, auth_token: str):
    """
    Returns:
        str|None: The user of the token. None if it isn't valid; `request.state.token_error` tells why, if the user may know it.
        `request.state.token_scope` is its scope.
    """

    migrate_keys_file()

    token = api_token_data.get_by_hash(hash_key(auth_token))

    if token is None:
        logging.warning("Request with an unknown token")
        return None

    user = token['user']

    if user not in [x.lower() for x in permission_config.PermissionKonfig.get_user_list()]:
        # Removed in the file by hand: the token must not work again when a user of this name is added (docs/bugfixes/api-token-outlives-user.md)
        logging.warning(f"Tokens of user '{user}' deleted: the user has no access to i-Releaser anymore")
        drop_token_of(user)
        return None

    now = datetime.datetime.now(datetime.timezone.utc)

    if token['expires_at'] is None and constants.C_TOKEN_MAX_DAYS:
        # A token of an older version: it expires C_TOKEN_MAX_DAYS after its first use with this version
        api_token_data.update(token['id'], expires_at=get_token_expiry(now))

    elif token['expires_at'] is not None and datetime.datetime.fromisoformat(token['expires_at']) < now:
        logging.info(f"Expired token '{token['name']}' of user '{user}'")
        request.state.token_error = "Your API token has expired. Create a new one on your account page (My account)."
        return None

    if _LEGACY_TOKEN.fullmatch(auth_token) and not token['legacy']:
        logging.warning(f"User '{user}' uses an API token of the old format. It will not be accepted by the next major version: create a new one.")
        api_token_data.update(token['id'], legacy=1)

    session = request.state.session
    session.transient = True
    session['current_user'] = user
    request.state.token_scope = token['scope']

    last_used = datetime.datetime.fromisoformat(token['last_used_at']) if token['last_used_at'] else None
    if last_used is None or (now - last_used).total_seconds() > KEY_LAST_USED_INTERVAL_SECONDS:
        api_token_data.update(token['id'], last_used_at=now.isoformat(timespec='seconds'))

    return user
