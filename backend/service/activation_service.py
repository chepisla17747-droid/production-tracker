"""Activation codes: the short secret an administrator hands to a new employee.

The code replaces the emailed invitation link. Only its SHA-256 digest is stored, in
account_private.account_token, so a code that is lost cannot be recovered from the
database; an administrator issues a new one instead.
"""
import hashlib
import secrets
from datetime import timedelta

from psycopg import Connection
from psycopg.rows import dict_row

from backend.annotations import PositiveInt, PositiveDuration
from backend.validation import validate_call

# Read aloud and written on paper, so I, L, O, 0 and 1 are left out. Eight characters
# from this alphabet are about 40 bits, and login throttling covers online guessing.
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 8
GROUP_SIZE = 4
DEFAULT_LIFETIME = timedelta(days=7)
# One message for every unusable code, so a wrong username and a wrong code look alike.
REFUSED = "That username and activation code do not match an account waiting to be set up."


def generate_code() -> str:
    """A fresh code, grouped for reading: for example 4KQ7-9TXM."""
    raw = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
    return "-".join(raw[at:at + GROUP_SIZE] for at in range(0, CODE_LENGTH, GROUP_SIZE))


def normalize_code(code) -> str:
    """Accept the code as typed: any case, with or without spaces and dashes."""
    if not isinstance(code, str):
        return ""
    return "".join(character for character in code.upper() if character.isalnum())


def code_digest(code) -> str:
    return hashlib.sha256(normalize_code(code).encode("ascii", "ignore")).hexdigest()


@validate_call
def create_activation_code(
    conn: Connection,
    account_id: PositiveInt,
    *,
    lifetime: PositiveDuration = DEFAULT_LIFETIME,
) -> str:
    """Store a new code's digest and return the code itself, once, to its issuer.

    The caller owns the transaction. Never log the code or store it in readable form.
    """
    code = generate_code()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO account_private.account_token
                (account_id, token_digest, purpose, expires_at)
            VALUES (%s, %s, 'invitation', CURRENT_TIMESTAMP + %s)
            """,
            (account_id, code_digest(code), lifetime),
        )
    return code


def lock_activation(conn: Connection, username, code) -> dict:
    """Lock and return the account a username and code identify together.

    Unknown usernames, wrong codes, expired, consumed, revoked and already-activated
    accounts all raise the same message, so nothing is learned by trying.
    """
    if not isinstance(username, str) or not username.strip() or not normalize_code(code):
        raise ValueError(REFUSED)
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT t.id AS token_id, t.account_id, a.username, a.employee_id, a.is_active,
                   a.password_hash IS NULL AS pending
            FROM account_private.account_token AS t
            JOIN public.user_account AS a ON a.id = t.account_id
            WHERE LOWER(a.username) = LOWER(%s) AND t.token_digest = %s
                AND t.purpose = 'invitation'
                AND t.expires_at > CURRENT_TIMESTAMP
                AND t.consumed_at IS NULL AND t.revoked_at IS NULL
            FOR UPDATE OF t, a
            """,
            (username.strip(), code_digest(code)),
        )
        row = cur.fetchone()
    if row is None or not row["pending"] or not row["is_active"]:
        raise ValueError(REFUSED)
    return row


def consume_activation(conn: Connection, token_id: int) -> None:
    """Mark the code used; it can never be presented again."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE account_private.account_token SET consumed_at = CURRENT_TIMESTAMP "
            "WHERE id = %s AND consumed_at IS NULL",
            (token_id,),
        )
