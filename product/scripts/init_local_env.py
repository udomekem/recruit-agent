"""Fill blank local-only settings in product/.env with generated values.

Found by the phase 2 clean clone check: after `cp .env.example .env`, `make services`
failed because Docker Compose needs MinIO credentials and an encryption key that a new
user has no way to know. Run `make local-env` once after copying `.env.example`.

Never overwrites a value that is already set. Never touches API keys (KIE_API_KEY,
ANTHROPIC_API_KEY, LANGFUSE_*): those come from your own accounts. Prints names only,
never values.
"""

from __future__ import annotations

import base64
import os
import re
import secrets
from pathlib import Path

ENV = Path(__file__).resolve().parents[1] / ".env"


def generated() -> dict[str, str]:
    user = "recruit-local"
    password = secrets.token_urlsafe(24)
    return {
        "RECRUITER_TOKEN": secrets.token_urlsafe(24),
        "DASHBOARD_PASSWORD": secrets.token_urlsafe(12),
        "SESSION_SECRET": secrets.token_urlsafe(48),
        "MINIO_ROOT_USER": user,
        "MINIO_ROOT_PASSWORD": password,
        "MINIO_KMS_SECRET_KEY": "recruit-key:" + base64.b64encode(os.urandom(32)).decode(),
        "S3_ACCESS_KEY": user,
        "S3_SECRET_KEY": password,
    }


def main() -> None:
    if not ENV.is_file():
        raise SystemExit("product/.env not found: run `cp .env.example .env` first")
    lines = ENV.read_text(encoding="utf-8").splitlines()
    current: dict[str, str] = {}
    for line in lines:
        m = re.match(r"^([A-Z0-9_]+)=(.*)$", line)
        if m:
            current[m.group(1)] = m.group(2).split("#", 1)[0].strip().strip('"').strip("'")
    values = generated()
    # keep the app's S3 login in step with an existing MinIO login
    if current.get("MINIO_ROOT_USER"):
        values["S3_ACCESS_KEY"] = current["MINIO_ROOT_USER"]
    if current.get("MINIO_ROOT_PASSWORD"):
        values["S3_SECRET_KEY"] = current["MINIO_ROOT_PASSWORD"]
    filled = []
    out = []
    for line in lines:
        m = re.match(r"^([A-Z0-9_]+)=(.*)$", line)
        if m and m.group(1) in values and not current.get(m.group(1)):
            out.append(f'{m.group(1)}="{values[m.group(1)]}"')
            filled.append(m.group(1))
        else:
            out.append(line)
    for name, value in values.items():
        if name not in current:
            out.append(f'{name}="{value}"')
            filled.append(name)
    ENV.write_text("\n".join(out) + "\n", encoding="utf-8")
    ENV.chmod(0o600)
    print("filled: " + (", ".join(filled) if filled else "nothing (all already set)"))
    missing = [k for k in ("KIE_API_KEY",) if not current.get(k)]
    if missing:
        print(
            "still needed from your own accounts: "
            + ", ".join(missing)
            + " (model calls; tests and the fast evals run without it)"
        )


if __name__ == "__main__":
    main()
