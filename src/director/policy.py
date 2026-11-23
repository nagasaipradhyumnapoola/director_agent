"""Capability grants and the effect gateway.

Default deny for consequential actions. Only an owner-approved grant can allow
an action, and an active deny always wins. Models, retrieved text and child
reports have no API path to create grants.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .models import KNOWN_ACTIONS, PermissionPolicy
from .security import ValidationError, canonical_json, sha256_object, sha256_text
from .store import Store

_BASE_READ_ACTIONS = {"read_artifact"}


class PolicyDenied(Exception):
    """The effect gateway refused an action."""


@dataclass(frozen=True)
class GrantCheck:
    allowed: bool
    reason: str
    grant_id: str | None = None

    def require(self) -> None:
        if not self.allowed:
            raise PolicyDenied(self.reason)


def _parse_ts(value: str | None) -> float | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def _resource_matches(grant_resource: str, resource: str) -> bool:
    if grant_resource in ("*", "project"):
        return True
    if grant_resource == resource:
        return True
    prefix = grant_resource.rstrip("*").rstrip("/\\")
    if not prefix:
        return True
    normalised = resource.replace("\\", "/")
    prefix = prefix.replace("\\", "/")
    return normalised == prefix or normalised.startswith(prefix + "/")


class PolicyGateway:
    def __init__(self, store: Store):
        self.store = store
        self.project_id = store.project_id

    def contract_permissions(self) -> PermissionPolicy:
        latest = self.store.latest_contract()
        if latest:
            return latest[1].permissions
        return PermissionPolicy()

    def policy_hash(self) -> str:
        grants = [
            {
                "id": g["id"],
                "actor": g["actor"],
                "action": g["action"],
                "resource": g["resource"],
                "effect": g["effect"],
                "limits": g["limits"],
                "expires_at": g["expires_at"],
                "task_revision": g["task_revision"],
                "payload_hash": g["payload_hash"],
                "revoked": g["revoked"],
            }
            for g in self.store.list_grants(include_revoked=True)
        ]
        return sha256_object(
            {
                "permissions": self.contract_permissions().to_dict(),
                "grants": sorted(grants, key=lambda g: g["id"]),
            }
        )

    def check(
        self,
        actor: str,
        action: str,
        resource: str,
        task_revision: int,
        payload: Mapping[str, Any] | None = None,
        now: float | None = None,
    ) -> GrantCheck:
        if action not in KNOWN_ACTIONS:
            return GrantCheck(False, "unknown action is denied by default")
        if not actor or len(actor) > 200:
            return GrantCheck(False, "invalid actor")
        if not isinstance(resource, str) or len(resource) > 2048:
            return GrantCheck(False, "invalid resource")
        current = now if now is not None else datetime.now(timezone.utc).timestamp()
        permissions = self.contract_permissions()

        if action in _BASE_READ_ACTIONS:
            root = Path(self.store.root)
            candidate = (root / resource).resolve(strict=False)
            try:
                candidate.relative_to(root.resolve(strict=False))
            except ValueError:
                return GrantCheck(False, "read outside the project root is denied")
            for denied in permissions.denied_paths:
                denied_path = (root / denied).resolve(strict=False)
                try:
                    candidate.relative_to(denied_path)
                    return GrantCheck(False, "resource is on the contract deny list")
                except ValueError:
                    continue
            return GrantCheck(True, "baseline project read")

        if action not in permissions.allowed_actions:
            return GrantCheck(False, "action is not enabled by the task contract")
        if action in {"network_read", "model_call"}:
            if not permissions.allow_external_network:
                return GrantCheck(False, "external network is disabled by contract")
        if action in {"external_send", "deploy"}:
            if not permissions.allow_external_network:
                return GrantCheck(False, "external effects are disabled by contract")
        if action == "delete" and not permissions.allow_untrusted_execution:
            return GrantCheck(False, "delete requires explicit owner policy")

        payload_hash = sha256_object(dict(payload)) if payload is not None else None
        active = []
        for grant in self.store.list_grants(include_revoked=False):
            if grant["expires_at"]:
                expires = _parse_ts(grant["expires_at"])
                if expires is None or expires <= current:
                    continue
            if int(grant["task_revision"]) != int(task_revision):
                continue
            if grant["actor"] != "*" and grant["actor"] != actor:
                continue
            if not _resource_matches(str(grant["resource"]), resource):
                continue
            if grant["payload_hash"] and grant["payload_hash"] != payload_hash:
                continue
            active.append(grant)
        denied = [g for g in active if g["effect"] == "deny"]
        if denied:
            return GrantCheck(False, "an active deny grant overrides allow", denied[0]["id"])
        allowed = [g for g in active if g["effect"] == "allow"]
        if not allowed:
            return GrantCheck(False, f"no matching owner grant for '{action}'")
        return GrantCheck(True, "matching owner grant", allowed[0]["id"])

    def require(
        self,
        actor: str,
        action: str,
        resource: str,
        task_revision: int,
        payload: Mapping[str, Any] | None = None,
    ) -> GrantCheck:
        result = self.check(actor, action, resource, task_revision, payload)
        result.require()
        return result

    def grant(
        self,
        actor: str,
        action: str,
        resource: str,
        task_revision: int,
        limits: Mapping[str, Any] | None = None,
        effect: str = "allow",
        expires_at: str | None = None,
        payload: Mapping[str, Any] | None = None,
        approved_by: str = "owner",
    ) -> str:
        if action not in KNOWN_ACTIONS:
            raise ValidationError("unknown action")
        if expires_at is not None and _parse_ts(expires_at) is None:
            raise ValidationError("grant expiry must be a valid ISO timestamp")
        payload_hash = sha256_object(dict(payload)) if payload is not None else None
        return self.store.add_grant(
            actor=actor,
            action=action,
            resource=resource,
            effect=effect,
            limits=dict(limits or {}),
            task_revision=task_revision,
            approved_by=approved_by,
            expires_at=expires_at,
            payload_hash=payload_hash,
        )


def policy_fingerprint(permissions: PermissionPolicy, grants: list[dict[str, Any]]) -> str:
    return sha256_text(canonical_json({"permissions": permissions.to_dict(), "grants": grants}))
