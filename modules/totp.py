"""
Time-based one-time passwords (TOTP, RFC 6238) for the two-factor authentication (docs/features/two-factor-authentication.md).

Only the standard library: HMAC-SHA1, 6 digits, 30 seconds, the defaults of all common authenticator apps.
"""
import base64
import hashlib
import hmac
import secrets
import struct
import time
import urllib.parse


DIGITS = 6
STEP_SECONDS = 30
# Steps before and after the current one which are accepted (clock difference of the phone)
WINDOW = 1
SECRET_BYTES = 20

ISSUER = 'i-Releaser'

RECOVERY_CODES = 10
_RECOVERY_ALPHABET = 'abcdefghjkmnpqrstuvwxyz23456789'



def generate_secret() -> str:
    """A new secret (160 bits) in Base32, as authenticator apps expect it"""
    return base64.b32encode(secrets.token_bytes(SECRET_BYTES)).decode('ascii').rstrip('=')



def _decode_secret(secret: str) -> bytes:
    secret = secret.strip().replace(' ', '').upper()
    return base64.b32decode(secret + '=' * (-len(secret) % 8))



def get_step(timestamp: float|None=None) -> int:
    return int((time.time() if timestamp is None else timestamp) // STEP_SECONDS)



def get_code(secret: str, step: int, digits: int=DIGITS, digest=hashlib.sha1) -> str:
    """The code of a time step (RFC 4226, section 5.3)"""

    mac = hmac.new(_decode_secret(secret), struct.pack('>Q', step), digest).digest()
    offset = mac[-1] & 0x0F
    value = struct.unpack('>I', mac[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(value % 10 ** digits).zfill(digits)



def is_code_format(code: str|None) -> bool:
    return code is not None and len(code.strip()) == DIGITS and code.strip().isdigit()



def verify(secret: str, code: str|None, last_step: int|None=None, timestamp: float|None=None) -> int|None:
    """
    Checks a code against the current time step and WINDOW steps before and after it.

    Args:
        last_step: The step of the last code which has been accepted: a code is only accepted once (replay)

    Returns:
        int|None: The time step of the code, None if it's not valid
    """

    if not is_code_format(code):
        return None

    code = code.strip()
    current = get_step(timestamp)

    for step in range(current - WINDOW, current + WINDOW + 1):
        if last_step is not None and step <= last_step:
            continue
        if hmac.compare_digest(get_code(secret, step), code):
            return step

    return None



def get_uri(user: str, secret: str) -> str:
    """otpauth URI for the QR code of the authenticator app"""

    label = urllib.parse.quote(f"{ISSUER}:{user}")
    query = urllib.parse.urlencode({'secret': secret, 'issuer': ISSUER, 'algorithm': 'SHA1', 'digits': DIGITS, 'period': STEP_SECONDS})
    return f"otpauth://totp/{label}?{query}"



def get_qr_code(uri: str) -> str:
    """The QR code as data URI of an SVG image (an <img>, no HTML from data in the page)"""

    import qrcode
    import qrcode.image.svg

    svg = qrcode.make(uri, image_factory=qrcode.image.svg.SvgPathImage, border=2).to_string()
    return 'data:image/svg+xml;base64,' + base64.b64encode(svg).decode('ascii')



def generate_recovery_codes() -> list[str]:
    """Codes to log in once each without the app, e.g. `k7mq-x2pn-4h`"""

    def code() -> str:
        text = ''.join(secrets.choice(_RECOVERY_ALPHABET) for _ in range(10))
        return f"{text[:4]}-{text[4:8]}-{text[8:]}"

    return [code() for _ in range(RECOVERY_CODES)]



def normalize_recovery_code(code: str) -> str:
    return code.strip().lower().replace('-', '').replace(' ', '')



def hash_recovery_code(code: str) -> str:
    # 50 bits of a secure random generator: a hash without salt is enough (as for the API tokens)
    return hashlib.sha256(normalize_recovery_code(code).encode('utf-8')).hexdigest()
