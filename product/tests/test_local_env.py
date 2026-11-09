"""`make local-env`: fills only blank local secrets, never overwrites, never prints values."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "init_local_env.py"


def load(env: Path):  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location("init_local_env", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.ENV = env
    return mod


def parse(text: str) -> dict[str, str]:
    out = {}
    for line in text.splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            out[k] = v.split("#", 1)[0].strip().strip('"')
    return out


def test_fills_blanks_keeps_existing_and_is_idempotent(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    example = (Path(__file__).resolve().parents[1] / ".env.example").read_text()
    env = tmp_path / ".env"
    env.write_text(example.replace("KIE_API_KEY=", 'KIE_API_KEY="my-real-key"'))
    mod = load(env)
    mod.main()
    first = parse(env.read_text())
    for name in [
        "RECRUITER_TOKEN",
        "DASHBOARD_PASSWORD",
        "SESSION_SECRET",
        "MINIO_ROOT_USER",
        "MINIO_ROOT_PASSWORD",
        "MINIO_KMS_SECRET_KEY",
        "S3_ACCESS_KEY",
        "S3_SECRET_KEY",
    ]:
        assert first[name], name
    assert first["S3_ACCESS_KEY"] == first["MINIO_ROOT_USER"]
    assert first["S3_SECRET_KEY"] == first["MINIO_ROOT_PASSWORD"]
    assert first["MINIO_KMS_SECRET_KEY"].startswith("recruit-key:")
    assert first["KIE_API_KEY"] == "my-real-key"  # API keys untouched
    printed = capsys.readouterr().out
    assert first["MINIO_ROOT_PASSWORD"] not in printed and first["RECRUITER_TOKEN"] not in printed
    mod.main()  # second run changes nothing
    assert parse(env.read_text()) == first
    assert "nothing" in capsys.readouterr().out
