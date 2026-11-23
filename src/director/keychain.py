"""OS keychain access for provider/credential material.

Windows uses the Credential Locker through `keyring`; secrets never enter project
config, SQLite, logs, prompts or receipts. If no backend is available, callers
must fail closed rather than fall back to plaintext.
"""

from __future__ import annotations

import re

from .security import ValidationError

SERVICE_PREFIX = "director"
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,127}$")


class KeychainUnavailable(Exception):
    pass


def _keyring():
    try:
        import keyring
    except Exception as exc:  # pragma: no cover - optional dependency
        raise KeychainUnavailable("keyring package is not installed") from exc
    try:
        backend = keyring.get_keyring()
    except Exception as exc:
        raise KeychainUnavailable("keychain backend unavailable") from exc
    name = type(backend).__name__.lower()
    if "fail" in name:
        raise KeychainUnavailable("no working keychain backend")
    return keyring


def _service(project_id: str) -> str:
    if not project_id or len(project_id) > 64:
        raise ValidationError("invalid project id for keychain")
    return f"{SERVICE_PREFIX}:{project_id}"


def set_secret(project_id: str, name: str, value: str) -> None:
    if not _NAME.match(name):
        raise ValidationError("invalid secret name")
    if not isinstance(value, str) or not value or len(value) > 16_384:
        raise ValidationError("invalid secret value")
    _keyring().set_password(_service(project_id), name, value)


def get_secret(project_id: str, name: str) -> str | None:
    if not _NAME.match(name):
        raise ValidationError("invalid secret name")
    return _keyring().get_password(_service(project_id), name)


def delete_secret(project_id: str, name: str) -> None:
    if not _NAME.match(name):
        raise ValidationError("invalid secret name")
    try:
        _keyring().delete_password(_service(project_id), name)
    except Exception:
        # Deleting a missing secret is idempotent for the operator.
        return


def has_secret(project_id: str, name: str) -> bool:
    return get_secret(project_id, name) is not None


def available() -> tuple[bool, str]:
    try:
        backend = _keyring().get_keyring()
        return True, type(backend).__name__
    except KeychainUnavailable as exc:
        return False, str(exc)
