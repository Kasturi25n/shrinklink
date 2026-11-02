"""Short code generation.

Design choice: random Base62 codes instead of encoding the auto-increment ID.
  + Not enumerable (nobody can walk /1, /2, /3 and scrape every link)
  + No coupling to DB row IDs, so it works with sharded / multi-primary setups
  - Needs a uniqueness check (retry on collision; the DB UNIQUE constraint is the
    final guard against races)

With 7 chars of Base62 there are 62^7 ≈ 3.5 trillion codes, so collisions stay
very rare until billions of links exist.
"""
import re
import secrets
import string

ALPHABET = string.ascii_letters + string.digits  # Base62

ALIAS_PATTERN = re.compile(r"^[A-Za-z0-9_-]{3,32}$")

# Paths the app itself serves; a link must never shadow them.
RESERVED_CODES = {
    "api", "docs", "redoc", "openapi.json", "health", "static", "favicon.ico", "dashboard",
}


def generate_code(length: int = 7) -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(length))


def is_valid_alias(alias: str) -> bool:
    return bool(ALIAS_PATTERN.match(alias)) and alias.lower() not in RESERVED_CODES
