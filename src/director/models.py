"""Typed task contracts, acceptance criteria and resource budgets."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .security import (
    ValidationError,
    canonical_json,
    contains_secret,
    sha256_text,
)

SUPPORTED_DOMAINS = ("general", "website", "ml", "research")

KNOWN_ACTIONS = (
    "read_artifact",
    "write_artifact",
    "run_local_subprocess",
    "launch_browser",
    "network_read",
    "model_call",
    "model_call_local",
    "external_send",
    "deploy",
    "delete",
)

_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")


def _require_key(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _KEY_RE.match(value):
        raise ValidationError(f"{label} must match [a-z0-9._-] (1-128 chars)")
    return value


def _bounded_str(value: Any, label: str, max_len: int, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ValidationError(f"{label} must be text")
    if not allow_empty and not value.strip():
        raise ValidationError(f"{label} must not be empty")
    if len(value) > max_len:
        raise ValidationError(f"{label} exceeds {max_len} characters")
    if contains_secret(value):
        raise ValidationError(f"{label} contains a secret-like value; remove it before saving")
    return value


def _str_list(value: Any, label: str, max_items: int, max_len: int) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        raise ValidationError(f"{label} must be a list of strings")
    if not isinstance(value, Sequence):
        raise ValidationError(f"{label} must be a list of strings")
    if len(value) > max_items:
        raise ValidationError(f"{label} exceeds {max_items} entries")
    out: list[str] = []
    for item in value:
        out.append(_bounded_str(item, label, max_len))
    return tuple(out)


@dataclass(frozen=True)
class Budgets:
    max_model_calls: int = 0
    max_input_tokens: int = 0
    max_output_tokens: int = 0
    max_cost_usd: float = 0.0
    max_wall_seconds: int = 300
    max_cpu_seconds: int = 300
    max_memory_mb: int = 1024
    max_concurrent: int = 1
    max_findings: int = 500
    max_output_bytes: int = 262_144
    max_scan_files: int = 2000
    max_file_bytes: int = 1_048_576

    def validate(self) -> "Budgets":
        for name in (
            "max_model_calls",
            "max_input_tokens",
            "max_output_tokens",
            "max_wall_seconds",
            "max_cpu_seconds",
            "max_memory_mb",
            "max_concurrent",
            "max_findings",
            "max_output_bytes",
            "max_scan_files",
            "max_file_bytes",
        ):
            value = getattr(self, name)
            if not isinstance(value, int) or value < 0:
                raise ValidationError(f"budget {name} must be a non-negative integer")
        if self.max_concurrent < 1:
            raise ValidationError("budget max_concurrent must be at least 1")
        if not isinstance(self.max_cost_usd, (int, float)) or not math.isfinite(self.max_cost_usd):
            raise ValidationError("budget max_cost_usd must be finite")
        if self.max_cost_usd < 0:
            raise ValidationError("budget max_cost_usd must be non-negative")
        return self

    def limit_for(self, unit: str) -> float:
        mapping = {
            "model_calls": self.max_model_calls,
            "input_tokens": self.max_input_tokens,
            "output_tokens": self.max_output_tokens,
            "cost_usd": self.max_cost_usd,
            "wall_seconds": self.max_wall_seconds,
            "cpu_seconds": self.max_cpu_seconds,
            "findings": self.max_findings,
            "output_bytes": self.max_output_bytes,
        }
        if unit not in mapping:
            raise ValidationError(f"unknown budget unit '{unit[:32]}'")
        return float(mapping[unit])

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_model_calls": self.max_model_calls,
            "max_input_tokens": self.max_input_tokens,
            "max_output_tokens": self.max_output_tokens,
            "max_cost_usd": self.max_cost_usd,
            "max_wall_seconds": self.max_wall_seconds,
            "max_cpu_seconds": self.max_cpu_seconds,
            "max_memory_mb": self.max_memory_mb,
            "max_concurrent": self.max_concurrent,
            "max_findings": self.max_findings,
            "max_output_bytes": self.max_output_bytes,
            "max_scan_files": self.max_scan_files,
            "max_file_bytes": self.max_file_bytes,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "Budgets":
        if data is None:
            return cls().validate()
        if not isinstance(data, Mapping):
            raise ValidationError("budgets must be an object")
        allowed = set(cls.__dataclass_fields__)  # type: ignore[attr-defined]
        unknown = set(data) - allowed
        if unknown:
            raise ValidationError("budgets contain unknown fields")
        return cls(**dict(data)).validate()  # type: ignore[arg-type]


@dataclass(frozen=True)
class PermissionPolicy:
    allow_external_network: bool = False
    allow_cloud_spend: bool = False
    allow_untrusted_execution: bool = False
    read_roots: tuple[str, ...] = ()
    write_roots: tuple[str, ...] = ()
    allowed_actions: tuple[str, ...] = ("read_artifact",)
    denied_paths: tuple[str, ...] = ()

    def validate(self) -> "PermissionPolicy":
        for name in ("allow_external_network", "allow_cloud_spend", "allow_untrusted_execution"):
            if not isinstance(getattr(self, name), bool):
                raise ValidationError(f"{name} must be boolean")
        for root in self.read_roots + self.write_roots + self.denied_paths:
            if not isinstance(root, str) or not root:
                raise ValidationError("permission paths must be non-empty strings")
            if len(root) > 1024:
                raise ValidationError("permission path too long")
            if root.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", root):
                raise ValidationError("permission roots must be project-relative")
            if ".." in re.split(r"[\\/]", root):
                raise ValidationError("permission roots must not contain '..'")
        for action in self.allowed_actions:
            if action not in KNOWN_ACTIONS:
                raise ValidationError(f"unknown action '{str(action)[:32]}'")
        if self.allow_cloud_spend and not self.allow_external_network:
            raise ValidationError("cloud spend requires external network to be enabled")
        return self

    def to_dict(self) -> dict[str, Any]:
        return {
            "allow_external_network": self.allow_external_network,
            "allow_cloud_spend": self.allow_cloud_spend,
            "allow_untrusted_execution": self.allow_untrusted_execution,
            "read_roots": list(self.read_roots),
            "write_roots": list(self.write_roots),
            "allowed_actions": list(self.allowed_actions),
            "denied_paths": list(self.denied_paths),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "PermissionPolicy":
        if data is None:
            return cls().validate()
        if not isinstance(data, Mapping):
            raise ValidationError("permissions must be an object")
        allowed = set(cls.__dataclass_fields__)  # type: ignore[attr-defined]
        unknown = set(data) - allowed
        if unknown:
            raise ValidationError("permissions contain unknown fields")
        payload = dict(data)
        for key in ("read_roots", "write_roots", "allowed_actions", "denied_paths"):
            if key in payload:
                payload[key] = tuple(_str_list(payload[key], key, 100, 1024))
        return cls(**payload).validate()  # type: ignore[arg-type]


@dataclass(frozen=True)
class AcceptanceCriterion:
    key: str
    description: str
    evaluator: str
    mandatory: bool = True
    params: Mapping[str, Any] = field(default_factory=dict)

    def validate(self) -> "AcceptanceCriterion":
        _require_key(self.key, "criterion key")
        _bounded_str(self.description, "criterion description", 2000)
        _bounded_str(self.evaluator, "criterion evaluator", 128)
        if not isinstance(self.mandatory, bool):
            raise ValidationError("criterion mandatory must be boolean")
        if not isinstance(self.params, Mapping):
            raise ValidationError("criterion params must be an object")
        if len(canonical_json(dict(self.params))) > 20_000:
            raise ValidationError("criterion params too large")
        return self

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "description": self.description,
            "evaluator": self.evaluator,
            "mandatory": self.mandatory,
            "params": dict(self.params),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AcceptanceCriterion":
        if not isinstance(data, Mapping):
            raise ValidationError("criterion must be an object")
        allowed = {"key", "description", "evaluator", "mandatory", "params"}
        unknown = set(data) - allowed
        if unknown:
            raise ValidationError("criterion contains unknown fields")
        return cls(
            key=data.get("key"),  # type: ignore[arg-type]
            description=data.get("description"),  # type: ignore[arg-type]
            evaluator=data.get("evaluator"),  # type: ignore[arg-type]
            mandatory=data.get("mandatory", True),
            params=data.get("params", {}),
        ).validate()


@dataclass(frozen=True)
class Requirement:
    key: str
    text: str
    domain: str
    criteria: tuple[AcceptanceCriterion, ...] = ()

    def validate(self) -> "Requirement":
        _require_key(self.key, "requirement key")
        _bounded_str(self.text, "requirement text", 4000)
        _require_key(self.domain, "requirement domain")
        if not self.criteria:
            raise ValidationError("requirement must declare at least one criterion")
        if len(self.criteria) > 50:
            raise ValidationError("requirement has too many criteria")
        for criterion in self.criteria:
            criterion.validate()
        return self

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "text": self.text,
            "domain": self.domain,
            "criteria": [c.to_dict() for c in self.criteria],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Requirement":
        if not isinstance(data, Mapping):
            raise ValidationError("requirement must be an object")
        allowed = {"key", "text", "domain", "criteria"}
        if set(data) - allowed:
            raise ValidationError("requirement contains unknown fields")
        criteria_raw = data.get("criteria", [])
        if not isinstance(criteria_raw, Sequence) or isinstance(criteria_raw, str):
            raise ValidationError("requirement criteria must be a list")
        return cls(
            key=data.get("key"),  # type: ignore[arg-type]
            text=data.get("text"),  # type: ignore[arg-type]
            domain=data.get("domain"),  # type: ignore[arg-type]
            criteria=tuple(AcceptanceCriterion.from_dict(c) for c in criteria_raw),
        ).validate()


@dataclass(frozen=True)
class TaskContract:
    project_id: str
    revision: int
    intent: str
    deliverables: tuple[str, ...]
    constraints: tuple[str, ...]
    non_goals: tuple[str, ...]
    assumptions: tuple[str, ...]
    domains: tuple[str, ...]
    requirements: tuple[Requirement, ...]
    budgets: Budgets
    permissions: PermissionPolicy
    stopping_conditions: tuple[str, ...]

    def validate(self) -> "TaskContract":
        if not isinstance(self.project_id, str) or not (1 <= len(self.project_id) <= 64):
            raise ValidationError("project_id must be 1-64 characters")
        if not isinstance(self.revision, int) or self.revision < 1:
            raise ValidationError("revision must be a positive integer")
        _bounded_str(self.intent, "intent", 20_000)
        _str_list(self.deliverables, "deliverables", 200, 4000)
        _str_list(self.constraints, "constraints", 200, 4000)
        _str_list(self.non_goals, "non_goals", 200, 4000)
        _str_list(self.assumptions, "assumptions", 200, 4000)
        _str_list(self.stopping_conditions, "stopping_conditions", 50, 2000)
        if not self.domains:
            raise ValidationError("contract must declare at least one domain")
        if len(self.domains) > 50:
            raise ValidationError("too many domains")
        for domain in self.domains:
            _require_key(domain, "domain")
        if not self.requirements:
            raise ValidationError("contract must declare at least one requirement")
        seen_req: set[str] = set()
        seen_crit: set[str] = set()
        for requirement in self.requirements:
            requirement.validate()
            if requirement.key in seen_req:
                raise ValidationError("duplicate requirement key")
            seen_req.add(requirement.key)
            for criterion in requirement.criteria:
                if criterion.key in seen_crit:
                    raise ValidationError("duplicate criterion key")
                seen_crit.add(criterion.key)
        self.budgets.validate()
        self.permissions.validate()
        return self

    @property
    def unsupported_domains(self) -> tuple[str, ...]:
        return tuple(d for d in self.domains if d not in SUPPORTED_DOMAINS)

    @property
    def mandatory_criteria(self) -> tuple[AcceptanceCriterion, ...]:
        out: list[AcceptanceCriterion] = []
        for requirement in self.requirements:
            out.extend(c for c in requirement.criteria if c.mandatory)
        return tuple(out)

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "revision": self.revision,
            "intent": self.intent,
            "deliverables": list(self.deliverables),
            "constraints": list(self.constraints),
            "non_goals": list(self.non_goals),
            "assumptions": list(self.assumptions),
            "domains": list(self.domains),
            "requirements": [r.to_dict() for r in self.requirements],
            "budgets": self.budgets.to_dict(),
            "permissions": self.permissions.to_dict(),
            "stopping_conditions": list(self.stopping_conditions),
        }

    def hash(self) -> str:
        return sha256_text(canonical_json(self.to_dict()))

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TaskContract":
        if not isinstance(data, Mapping):
            raise ValidationError("contract must be an object")
        allowed = {
            "project_id",
            "revision",
            "intent",
            "deliverables",
            "constraints",
            "non_goals",
            "assumptions",
            "domains",
            "requirements",
            "budgets",
            "permissions",
            "stopping_conditions",
        }
        if set(data) - allowed:
            raise ValidationError("contract contains unknown fields")
        requirements_raw = data.get("requirements", [])
        if not isinstance(requirements_raw, Sequence) or isinstance(requirements_raw, str):
            raise ValidationError("requirements must be a list")
        return cls(
            project_id=data.get("project_id"),  # type: ignore[arg-type]
            revision=data.get("revision"),  # type: ignore[arg-type]
            intent=data.get("intent"),  # type: ignore[arg-type]
            deliverables=_str_list(data.get("deliverables"), "deliverables", 200, 4000),
            constraints=_str_list(data.get("constraints"), "constraints", 200, 4000),
            non_goals=_str_list(data.get("non_goals"), "non_goals", 200, 4000),
            assumptions=_str_list(data.get("assumptions"), "assumptions", 200, 4000),
            domains=_str_list(data.get("domains"), "domains", 50, 128),
            requirements=tuple(Requirement.from_dict(r) for r in requirements_raw),
            budgets=Budgets.from_dict(data.get("budgets")),  # type: ignore[arg-type]
            permissions=PermissionPolicy.from_dict(data.get("permissions")),  # type: ignore[arg-type]
            stopping_conditions=_str_list(
                data.get("stopping_conditions"), "stopping_conditions", 50, 2000
            ),
        ).validate()
