#!/usr/bin/env python3
"""DEK rotation script — re-wraps every per-record DEK with a new MASTER_KEY.

When to run: after rotating the KEK (MASTER_KEY).

How it works:
  1. Decrypt each dek_enc with the OLD_MASTER_KEY.
  2. Re-encrypt the DEK with the NEW_MASTER_KEY.
  3. Write the new dek_enc back — ciphertext is untouched (DEK itself doesn't change).

Usage:
    OLD_MASTER_KEY=<base64-key> NEW_MASTER_KEY=<base64-key> \
    DATABASE_URL=postgresql://... python scripts/rotate_dek.py

Safe: it never touches auth_ciphertext — the actual credential bytes stay encrypted
under the same DEK throughout. Only the DEK wrapping key changes.
"""

from __future__ import annotations

import os
import sys

from cryptography.fernet import Fernet
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

# Import models directly
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from app.models.registry import Registry  # noqa: E402


def _load_key(env_var: str) -> Fernet:
    val = os.environ.get(env_var, "")
    if not val:
        print(f"ERROR: {env_var} is not set", file=sys.stderr)
        sys.exit(1)
    return Fernet(val.encode())


def main() -> None:
    old_kek = _load_key("OLD_MASTER_KEY")
    new_kek = _load_key("NEW_MASTER_KEY")
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        print("ERROR: DATABASE_URL is not set", file=sys.stderr)
        sys.exit(1)

    sync_url = db_url.replace("+asyncpg", "+psycopg2")
    engine = create_engine(sync_url)
    Session = sessionmaker(engine)

    with Session() as session:
        registries = session.execute(select(Registry)).scalars().all()
        rotated = 0
        errors = 0

        for reg in registries:
            if not reg.auth_dek_enc:
                continue
            try:
                # Unwrap DEK with old KEK
                dek = old_kek.decrypt(reg.auth_dek_enc)
                # Re-wrap DEK with new KEK
                new_dek_enc = new_kek.encrypt(dek)
                reg.auth_dek_enc = new_dek_enc
                rotated += 1
            except Exception as exc:
                print(
                    f"ERROR: failed to rotate registry {reg.id}: {exc}",
                    file=sys.stderr,
                )
                errors += 1

        if errors:
            print(
                f"Aborting — {errors} rotation error(s). No changes committed.",
                file=sys.stderr,
            )
            session.rollback()
            sys.exit(1)

        session.commit()
        print(f"Rotated {rotated} registry DEK(s) successfully.")


if __name__ == "__main__":
    main()
