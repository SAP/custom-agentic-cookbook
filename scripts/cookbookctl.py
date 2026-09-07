#!/usr/bin/env python3
"""Validate and manage local SAP BTP Agent Cookbook pilot state."""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - exercised on hosts without dependencies
    yaml = None


ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = ROOT / ".cookbook"
STATE_FILE = STATE_DIR / "state.json"
GENERATED_TFVARS = STATE_DIR / "generated.tfvars.json"
LOCAL_STATE_FILES = ("state.json", "generated.tfvars.json")

_SECRET_KEYS = {
    "api_key",
    "apikey",
    "certificate",
    "client_secret",
    "credentials",
    "password",
    "passwd",
    "private_key",
    "service_key",
    "secret",
    "token",
}


class CookbookError(RuntimeError):
    """A user-actionable coordinator error."""


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def atomic_json(path: Path, value: Any) -> None:
    """Write private local state atomically with deterministic JSON formatting."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=str(path.parent)
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def require_mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CookbookError(f"{name} must be a YAML mapping")
    return value


def required_text(mapping: Mapping[str, Any], key: str, path: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise CookbookError(f"{path}.{key} must be a non-empty string")
    return value.strip()


def optional_text(mapping: Mapping[str, Any], key: str, path: str) -> str | None:
    value = mapping.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise CookbookError(f"{path}.{key} must be null or a non-empty string")
    return value.strip()


def text_list(value: Any, path: str) -> list[str]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise CookbookError(f"{path} must be a list of non-empty strings")
    return [item.strip() for item in value]


def reject_embedded_credentials(value: Any, path: str = "manifest") -> None:
    """Keep the portable manifest credential-free, including extension maps."""
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = re.sub(r"[^a-z0-9]+", "_", str(key).lower()).strip("_")
            if normalized in _SECRET_KEYS:
                raise CookbookError(
                    f"{path}.{key} is not allowed; pilot manifests must be credential-free"
                )
            reject_embedded_credentials(nested, f"{path}.{key}")
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            reject_embedded_credentials(nested, f"{path}[{index}]")


def ensure_entitlement(
    entitlements: dict[str, Any], key: str, service_name: str, plan_name: str
) -> None:
    for value in entitlements.values():
        if value["service_name"] == service_name and value["plan_name"] == plan_name:
            return
    if key in entitlements:
        raise CookbookError(
            f"services.entitlements.{key} is reserved for {service_name}/{plan_name}"
        )
    entitlements[key] = {"service_name": service_name, "plan_name": plan_name}


def load_manifest(path: Path) -> dict[str, Any]:
    if yaml is None:
        raise CookbookError(
            "PyYAML is required; install requirements-cookbookctl.txt in a virtual environment"
        )
    if not path.is_file():
        raise CookbookError(f"manifest not found: {path}")
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise CookbookError(f"invalid YAML in {path}: {exc}") from exc
    return normalize_manifest(require_mapping(loaded, "manifest"))


def normalize_manifest(source: dict[str, Any]) -> dict[str, Any]:
    reject_embedded_credentials(source)
    manifest = copy.deepcopy(source)
    if manifest.get("version") != 1:
        raise CookbookError("manifest.version must be 1")

    account = require_mapping(manifest.get("account"), "account")
    account["global_account_subdomain"] = required_text(
        account, "global_account_subdomain", "account"
    )
    account["name"] = required_text(account, "name", "account")
    account["subdomain"] = required_text(account, "subdomain", "account")
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", account["subdomain"]):
        raise CookbookError(
            "account.subdomain must use lowercase letters, numbers, and internal hyphens"
        )
    account["region"] = required_text(account, "region", "account")
    account.setdefault("btp_cli_url", "https://cli.btp.cloud.sap")
    account.setdefault("usage", "NOT_USED_FOR_PRODUCTION")
    account["admins"] = text_list(account.setdefault("admins", []), "account.admins")
    account.setdefault("labels", {"managed-by": ["cookbookctl"]})
    require_mapping(account["labels"], "account.labels")

    runtime = require_mapping(manifest.get("runtime"), "runtime")
    if "target" not in runtime:
        raise CookbookError(
            "runtime.target must be explicit (cf or kyma); omission is not consent to a default"
        )
    target = required_text(runtime, "target", "runtime")
    if target not in {"cf", "kyma"}:
        raise CookbookError("runtime.target must be cf or kyma")
    runtime["target"] = target

    cloudfoundry = require_mapping(
        runtime.setdefault("cloudfoundry", {}), "runtime.cloudfoundry"
    )
    cloudfoundry.setdefault("enabled", target == "cf")
    if not isinstance(cloudfoundry["enabled"], bool):
        raise CookbookError("runtime.cloudfoundry.enabled must be true or false")
    if target == "cf" and not cloudfoundry["enabled"]:
        raise CookbookError(
            "runtime.cloudfoundry.enabled must be true for a cf runtime"
        )
    if target == "kyma" and cloudfoundry["enabled"]:
        raise CookbookError(
            "Cloud Foundry and Kyma are mutually exclusive runtime targets"
        )
    cloudfoundry.setdefault("spaces", {"dev": {"name": "dev"}})
    spaces = require_mapping(cloudfoundry["spaces"], "runtime.cloudfoundry.spaces")
    if cloudfoundry["enabled"] and not spaces:
        raise CookbookError(
            "runtime.cloudfoundry.spaces must contain at least one space"
        )
    api_url = optional_text(cloudfoundry, "api_url", "runtime.cloudfoundry")
    if api_url is not None and not api_url.startswith("https://"):
        raise CookbookError("runtime.cloudfoundry.api_url must start with https://")
    if api_url is not None:
        cloudfoundry["api_url"] = api_url

    kyma = runtime.get("kyma")
    if target == "kyma" and kyma is None:
        raise CookbookError("runtime.kyma is required when runtime.target is kyma")
    if target == "cf" and kyma is not None:
        raise CookbookError("runtime.kyma must be omitted when runtime.target is cf")
    if kyma is not None:
        kyma = require_mapping(kyma, "runtime.kyma")
        mode = kyma.setdefault("mode", "required")
        if mode not in {"required", "if_available"}:
            raise CookbookError("runtime.kyma.mode must be required or if_available")
        kyma["plan"] = required_text(kyma, "plan", "runtime.kyma")
        kyma["region"] = required_text(kyma, "region", "runtime.kyma")
        kyma.setdefault("entitlement_amount", 1)
        autoscaler = require_mapping(
            kyma.setdefault("autoscaler", {}), "runtime.kyma.autoscaler"
        )
        minimum = autoscaler.get("min")
        maximum = autoscaler.get("max")
        if minimum is not None and (
            isinstance(minimum, bool) or not isinstance(minimum, int) or minimum < 0
        ):
            raise CookbookError(
                "runtime.kyma.autoscaler.min must be a non-negative integer"
            )
        if maximum is not None and (
            isinstance(maximum, bool) or not isinstance(maximum, int) or maximum < 1
        ):
            raise CookbookError(
                "runtime.kyma.autoscaler.max must be a positive integer"
            )
        if minimum is not None and maximum is not None and maximum < minimum:
            raise CookbookError("runtime.kyma.autoscaler.max must be >= min")
        require_mapping(kyma.setdefault("parameters", {}), "runtime.kyma.parameters")

    agent = require_mapping(manifest.get("agent"), "agent")
    agent["name"] = required_text(agent, "name", "agent")
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", agent["name"]):
        raise CookbookError("agent.name must be kebab-case")
    agent["purpose"] = required_text(agent, "purpose", "agent")
    material_choices = ("language", "framework", "taskstore", "llm_provider")
    missing = [f"agent.{key}" for key in material_choices if key not in agent]
    if missing:
        raise CookbookError(
            "material architecture choices must be explicit; missing "
            + ", ".join(missing)
        )
    for key in material_choices:
        agent[key] = required_text(agent, key, "agent")
    if agent["language"] not in {"typescript", "python"}:
        raise CookbookError("agent.language must be typescript or python")
    if agent["framework"] not in {"express", "cap"}:
        raise CookbookError("agent.framework must be express or cap")
    if agent["language"] == "python" and agent["framework"] != "express":
        raise CookbookError("Python agents support only the express framework")
    if agent["taskstore"] not in {"memory", "hana"}:
        raise CookbookError("agent.taskstore must be memory or hana")
    if agent["taskstore"] == "hana" and agent["framework"] != "cap":
        raise CookbookError("agent.taskstore hana requires the CAP framework")
    if agent["llm_provider"] not in {"aicore", "openai-compatible"}:
        raise CookbookError("agent.llm_provider must be aicore or openai-compatible")

    joule = require_mapping(manifest.setdefault("joule", {}), "joule")
    joule.setdefault("enabled", False)
    if not isinstance(joule["enabled"], bool):
        raise CookbookError("joule.enabled must be true or false")
    if joule["enabled"]:
        joule.setdefault("tenant_type", "PRODUCTIVE")
        if joule["tenant_type"] not in {"PRODUCTIVE", "TEST"}:
            raise CookbookError("joule.tenant_type must be PRODUCTIVE or TEST")
        joule.setdefault("include_process_automation", True)
        joule["users"] = text_list(joule.setdefault("users", []), "joule.users")
        joule["groups"] = text_list(joule.setdefault("groups", []), "joule.groups")
        joule.setdefault("identity_provider_origin", "sap.custom")

    services = require_mapping(manifest.setdefault("services", {}), "services")
    entitlements = require_mapping(
        services.setdefault("entitlements", {}), "services.entitlements"
    )
    for key, value in entitlements.items():
        entitlement = require_mapping(value, f"services.entitlements.{key}")
        entitlement["service_name"] = required_text(
            entitlement, "service_name", f"services.entitlements.{key}"
        )
        entitlement["plan_name"] = required_text(
            entitlement, "plan_name", f"services.entitlements.{key}"
        )
        amount = entitlement.get("amount")
        if amount is not None and (
            isinstance(amount, bool)
            or not isinstance(amount, (int, float))
            or amount < 0
        ):
            raise CookbookError(
                f"services.entitlements.{key}.amount must be a non-negative number"
            )
    services["cf_instances"] = require_mapping(
        services.setdefault("cf_instances", {}), "services.cf_instances"
    )
    if agent["llm_provider"] == "aicore":
        ensure_entitlement(entitlements, "aicore_extended", "aicore", "extended")
    if agent["taskstore"] == "hana":
        ensure_entitlement(entitlements, "hana_hdi_shared", "hana", "hdi-shared")
    if joule["enabled"]:
        ensure_entitlement(entitlements, "destination_lite", "destination", "lite")
        ensure_entitlement(entitlements, "xsuaa_application", "xsuaa", "application")

    verification = require_mapping(
        manifest.setdefault("verification", {}), "verification"
    )
    verification.setdefault("a2a_version", "1.0")
    verification.setdefault("agent_card_path", "/.well-known/agent-card.json")
    if verification["a2a_version"] != "1.0":
        raise CookbookError("verification.a2a_version must be '1.0'")
    if verification["agent_card_path"] != "/.well-known/agent-card.json":
        raise CookbookError(
            "verification.agent_card_path must use the A2A v1.0 Agent Card path "
            "/.well-known/agent-card.json"
        )
    return manifest


def compact(mapping: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in mapping.items() if value is not None}


def render_tfvars(manifest: dict[str, Any]) -> dict[str, Any]:
    account = manifest["account"]
    runtime = manifest["runtime"]
    cloudfoundry = runtime["cloudfoundry"]
    services = manifest["services"]
    rendered = compact(
        {
            "global_account_subdomain": account["global_account_subdomain"],
            "btp_cli_url": account["btp_cli_url"],
            "subaccount_name": account["name"],
            "subaccount_subdomain": account["subdomain"],
            "region": account["region"],
            "subaccount_usage": account["usage"],
            "subaccount_labels": account["labels"],
            "subaccount_admins": account["admins"],
            "enable_cloudfoundry": cloudfoundry["enabled"],
            "cf_api_url": cloudfoundry.get("api_url"),
            "cf_org_name": cloudfoundry.get("org_name", account["subdomain"]),
            "cf_memory_quota_gb": cloudfoundry.get("memory_gb"),
            "cf_spaces": cloudfoundry["spaces"],
            "entitlements": services["entitlements"],
            "cf_service_instances": services["cf_instances"],
        }
    )
    kyma = runtime.get("kyma")
    if kyma is not None:
        autoscaler = kyma["autoscaler"]
        rendered["kyma_environment"] = compact(
            {
                "mode": kyma["mode"],
                "environment_name": kyma.get("environment_name"),
                "cluster_name": kyma.get("cluster_name"),
                "plan_name": kyma["plan"],
                "cluster_region": kyma["region"],
                "machine_type": kyma.get("machine_type"),
                "auto_scaler_min": autoscaler.get("min"),
                "auto_scaler_max": autoscaler.get("max"),
                "entitlement_amount": kyma["entitlement_amount"],
                "plan_unique_identifier": kyma.get("plan_unique_identifier"),
                "extra_parameters_json": json.dumps(
                    kyma["parameters"], separators=(",", ":"), sort_keys=True
                ),
            }
        )
    joule = manifest["joule"]
    if joule["enabled"]:
        rendered["joule_studio"] = {
            "tenant_type": joule["tenant_type"],
            "include_process_automation": joule["include_process_automation"],
            "developer_users": joule["users"],
            "developer_groups": joule["groups"],
            "identity_provider_origin": joule["identity_provider_origin"],
        }
    return rendered


def manifest_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_state(manifest_path: Path) -> dict[str, Any]:
    digest = manifest_digest(manifest_path)
    state = {}
    if STATE_FILE.is_file():
        try:
            state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            state = {}
    if (
        not isinstance(state, dict)
        or state.get("version") != 1
        or state.get("manifest_sha256") != digest
        or not isinstance(state.get("stages"), dict)
    ):
        state = {
            "version": 1,
            "manifest": str(manifest_path),
            "manifest_sha256": digest,
            "stages": {},
            "updated_at": now(),
        }
        atomic_json(STATE_FILE, state)
    return state


def record_stage(manifest_path: Path, stage: str, status: str) -> None:
    state = load_state(manifest_path)
    state.setdefault("stages", {})[stage] = {"status": status, "updated_at": now()}
    state["updated_at"] = now()
    atomic_json(STATE_FILE, state)


def command_exists(name: str) -> bool:
    return shutil.which(name) is not None


def btp_json(*arguments: str) -> Any:
    """Run one of the coordinator's fixed read-only BTP CLI queries."""
    if not command_exists("btp"):
        return None
    try:
        result = subprocess.run(
            ["btp", "--format", "json", *arguments],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


def subaccount_rows(payload: Any) -> list[dict[str, Any]]:
    """Normalize BTP CLI list output into a stable public JSON shape."""
    items = payload.get("value", []) if isinstance(payload, dict) else payload
    rows = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "guid": item.get("guid"),
                "display_name": item.get("displayName"),
                "subdomain": item.get("subdomain"),
                "region": item.get("region"),
                "state": item.get("state"),
                "used_for_production": item.get("usedForProduction"),
            }
        )
    return rows


def manifest_account_summary(path: Path) -> dict[str, Any] | None:
    """Read only manifest account identifiers without creating local state."""
    if yaml is None or not path.is_file():
        return None
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return None
    account = data.get("account") if isinstance(data, dict) else None
    if not isinstance(account, dict):
        return None
    return {
        "path": str(path),
        "subdomain": account.get("subdomain"),
        "global_account_subdomain": account.get("global_account_subdomain"),
        "region": account.get("region"),
    }


def assess_manifest_subaccount(
    manifest_subdomain: str | None, rows: list[dict[str, Any]]
) -> tuple[str, dict[str, Any] | None]:
    if not manifest_subdomain:
        return "unknown", None
    existing = next(
        (row for row in rows if row.get("subdomain") == manifest_subdomain), None
    )
    if existing is None:
        return "available", None
    return "already-exists", existing


def command_accounts(manifest_path: Path, *, as_json: bool) -> int:
    """Discover the active global account without selecting or changing it."""
    if not command_exists("btp"):
        message = "btp CLI is not installed; install it and run 'btp login --sso'"
        if as_json:
            print(json.dumps({"logged_in": False, "error": message}, indent=2))
        else:
            print(f"Error: {message}", file=sys.stderr)
        return 1

    global_account = btp_json("get", "accounts/global-account")
    if not isinstance(global_account, dict):
        message = (
            "no active BTP CLI session; run 'btp login --sso' and select the "
            "intended global account"
        )
        if as_json:
            print(json.dumps({"logged_in": False, "error": message}, indent=2))
        else:
            print(f"Error: {message}", file=sys.stderr)
        return 1

    session_subdomain = str(global_account.get("subdomain") or "")
    subaccounts = btp_json("list", "accounts/subaccount")
    if not isinstance(subaccounts, (dict, list)):
        message = "could not list subaccounts from the active BTP CLI session"
        report = {
            "logged_in": True,
            "global_account": {
                "display_name": global_account.get("displayName"),
                "subdomain": session_subdomain,
            },
            "error": message,
        }
        if as_json:
            print(json.dumps(report, indent=2, sort_keys=True))
        else:
            print(f"Error: {message}", file=sys.stderr)
        return 1

    rows = subaccount_rows(subaccounts)
    active = manifest_account_summary(manifest_path)
    guidance = [
        "Discovery is read-only: cookbookctl does not select, adopt, or change a subaccount."
    ]
    manifest_report: dict[str, Any] = {"exists": False, "path": str(manifest_path)}
    if active:
        expected_global = active.get("global_account_subdomain")
        if expected_global and expected_global != session_subdomain:
            assessment = "wrong-global-account"
            existing = None
            guidance.append(
                f"The session targets '{session_subdomain}', but the manifest selects "
                f"'{expected_global}'. Log in to the intended account before continuing."
            )
        else:
            assessment, existing = assess_manifest_subaccount(
                active.get("subdomain"), rows
            )
            if assessment == "available":
                guidance.append(
                    f"Subdomain '{active.get('subdomain')}' is not present in the visible account list."
                )
            elif assessment == "already-exists":
                guidance.append(
                    f"Subdomain '{active.get('subdomain')}' already exists. This command "
                    "reports the match but does not select or adopt it."
                )
        manifest_report = {
            "exists": True,
            **active,
            "assessment": assessment,
            "existing_subaccount_guid": existing.get("guid") if existing else None,
        }
    else:
        guidance.append(
            "No manifest exists; review the visible subdomains before choosing one."
        )

    report = {
        "logged_in": True,
        "global_account": {
            "display_name": global_account.get("displayName"),
            "subdomain": session_subdomain,
        },
        "subaccounts": rows,
        "manifest": manifest_report,
        "guidance": guidance,
    }
    if as_json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    print("BTP account discovery")
    print(
        f"  Global account: {global_account.get('displayName')} "
        f"(subdomain {session_subdomain})"
    )
    if rows:
        print("  Visible subaccounts:")
        for row in rows:
            print(
                f"    - {row.get('display_name')} (subdomain {row.get('subdomain')}, "
                f"region {row.get('region')}, state {row.get('state')})"
            )
    else:
        print("  Visible subaccounts: none")
    for line in guidance:
        print(f"  * {line}")
    return 0


def read_state(manifest_path: Path) -> tuple[dict[str, Any] | None, bool]:
    """Read workflow state without creating or repairing it."""
    if not STATE_FILE.is_file():
        return None, False
    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None, False
    if not isinstance(state, dict):
        return None, False
    matches = (
        state.get("version") == 1
        and isinstance(state.get("stages"), dict)
        and manifest_path.is_file()
        and state.get("manifest_sha256") == manifest_digest(manifest_path)
    )
    return state, matches


def managed_parked_root(*, create: bool) -> Path:
    """Resolve the allowlisted archive root and reject a redirected child path."""
    state_root = STATE_DIR.resolve()
    parked_path = STATE_DIR / "parked"
    if parked_path.is_symlink():
        raise CookbookError("managed parked root must not be a symbolic link")
    if create:
        parked_path.mkdir(parents=True, exist_ok=True)
    parked_root = parked_path.resolve()
    if parked_root.parent != state_root:
        raise CookbookError("managed parked root must be directly below .cookbook")
    return parked_root


def command_park(manifest_path: Path) -> int:
    """Move the manifest and known coordinator state into a local archive."""
    if manifest_path.is_symlink():
        raise CookbookError("pilot manifest must not be a symbolic link")
    manifest = load_manifest(manifest_path)
    subdomain = manifest["account"]["subdomain"]

    sources = [manifest_path]
    sources.extend(
        path
        for path in (STATE_DIR / name for name in LOCAL_STATE_FILES)
        if path.exists()
    )
    symbolic = [str(path) for path in sources if path.is_symlink()]
    if symbolic:
        raise CookbookError(
            "refusing to park symbolic-link state files:\n  " + "\n  ".join(symbolic)
        )

    parked_root = managed_parked_root(create=True)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = parked_root / f"{subdomain}-{stamp}"
    if target.exists():
        raise CookbookError(f"park target already exists: {target}")
    if target.resolve().parent != parked_root:
        raise CookbookError("park target escaped the managed parked root")

    state_target = target / "state"
    state_target.mkdir(parents=True, mode=0o700)
    metadata = {
        "version": 1,
        "parked_at": now(),
        "subdomain": subdomain,
        "manifest_sha256": manifest_digest(manifest_path),
        "state_files": [path.name for path in sources[1:]],
    }
    atomic_json(target / "parked.json", metadata)

    moves = [(manifest_path, target / "pilot.yaml")]
    moves.extend((path, state_target / path.name) for path in sources[1:])
    completed = []
    try:
        for source, destination in moves:
            shutil.move(str(source), str(destination))
            completed.append((source, destination))
    except OSError as exc:
        for source, destination in reversed(completed):
            if destination.exists() and not source.exists():
                shutil.move(str(destination), str(source))
        for leftover in (target / "parked.json", state_target, target):
            try:
                if leftover.is_file():
                    leftover.unlink()
                elif leftover.is_dir() and not any(leftover.iterdir()):
                    leftover.rmdir()
            except OSError:
                pass
        raise CookbookError(f"could not park the pilot safely: {exc}") from exc

    print(f"Pilot parked locally: {target}")
    print("No SAP BTP resource was selected, changed, or stopped.")
    print(f"Restore it with: ./cookbookctl unpark {target}")
    return 0


def validated_archive(archive: Path) -> tuple[Path, dict[str, Any]]:
    """Validate archive containment, ownership marker, and expected file set."""
    parked_root = managed_parked_root(create=False)
    if archive.is_symlink():
        raise CookbookError("parked archive must not be a symbolic link")
    try:
        resolved = archive.resolve(strict=True)
    except OSError as exc:
        raise CookbookError(f"parked archive does not exist: {archive}") from exc
    if resolved.parent != parked_root:
        raise CookbookError(f"archive is outside the managed parked root: {archive}")
    if not resolved.is_dir():
        raise CookbookError(f"parked archive is not a directory: {archive}")

    expected_top_level = {"parked.json", "pilot.yaml", "state"}
    actual_top_level = {item.name for item in resolved.iterdir()}
    if actual_top_level != expected_top_level:
        raise CookbookError("parked archive contains missing or unexpected entries")
    metadata_file = resolved / "parked.json"
    if metadata_file.is_symlink() or not metadata_file.is_file():
        raise CookbookError(f"invalid parked archive marker: {metadata_file}")
    try:
        metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise CookbookError(
            f"unreadable parked archive marker: {metadata_file}"
        ) from exc
    if not isinstance(metadata, dict) or metadata.get("version") != 1:
        raise CookbookError("parked archive marker must use version 1")
    subdomain = metadata.get("subdomain")
    if not isinstance(subdomain, str) or not resolved.name.startswith(f"{subdomain}-"):
        raise CookbookError("parked archive marker does not match its directory")

    manifest_source = resolved / "pilot.yaml"
    state_source = resolved / "state"
    if manifest_source.is_symlink() or not manifest_source.is_file():
        raise CookbookError("parked archive has no regular pilot.yaml")
    if state_source.is_symlink() or not state_source.is_dir():
        raise CookbookError("parked archive has no regular state directory")
    state_entries = list(state_source.iterdir())
    if any(item.is_symlink() for item in state_entries):
        raise CookbookError("parked archive state must not contain symbolic links")
    if any(
        item.name not in LOCAL_STATE_FILES or not item.is_file()
        for item in state_entries
    ):
        raise CookbookError("parked archive contains unexpected state files")
    if metadata.get("manifest_sha256") != manifest_digest(manifest_source):
        raise CookbookError("parked manifest does not match the archive marker")
    return resolved, metadata


def command_unpark(archive: Path, manifest_path: Path) -> int:
    """Restore a validated local archive to the caller-selected manifest path."""
    archive, _ = validated_archive(archive)
    sources = [(archive / "pilot.yaml", manifest_path)]
    sources.extend(
        (item, STATE_DIR / item.name) for item in sorted((archive / "state").iterdir())
    )
    conflicts = [str(destination) for _, destination in sources if destination.exists()]
    if conflicts:
        raise CookbookError(
            "unpark would overwrite active workspace files:\n  "
            + "\n  ".join(conflicts)
        )
    if not manifest_path.parent.is_dir():
        raise CookbookError(
            f"manifest parent directory does not exist: {manifest_path.parent}"
        )
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    completed = []
    try:
        for source, destination in sources:
            shutil.move(str(source), str(destination))
            completed.append((source, destination))
    except OSError as exc:
        for source, destination in reversed(completed):
            if destination.exists() and not source.exists():
                shutil.move(str(destination), str(source))
        raise CookbookError(f"could not restore the pilot safely: {exc}") from exc

    (archive / "parked.json").unlink()
    (archive / "state").rmdir()
    archive.rmdir()
    print(f"Pilot restored locally: {manifest_path}")
    print("Inspect it with './cookbookctl status'.")
    return 0


def active_pilot_report(manifest_path: Path) -> dict[str, Any]:
    summary = manifest_account_summary(manifest_path)
    if not summary:
        return {"exists": False, "path": str(manifest_path)}
    state, matches = read_state(manifest_path)
    stages = {}
    if state is not None and matches:
        stages = {
            name: entry.get("status")
            for name, entry in state.get("stages", {}).items()
            if isinstance(entry, dict)
        }
    return {
        "exists": True,
        **summary,
        "state_matches_manifest": matches,
        "stages": stages,
    }


def parked_pilot_reports() -> list[dict[str, Any]]:
    parked_root = managed_parked_root(create=False)
    if not parked_root.is_dir():
        return []
    reports = []
    for item in sorted(parked_root.iterdir()):
        if item.is_symlink() or not item.is_dir():
            continue
        metadata_file = item / "parked.json"
        if metadata_file.is_symlink() or not metadata_file.is_file():
            continue
        try:
            metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(metadata, dict) or metadata.get("version") != 1:
            continue
        reports.append(
            {
                "path": str(item),
                "subdomain": metadata.get("subdomain"),
                "parked_at": metadata.get("parked_at"),
            }
        )
    return reports


def command_pilots(manifest_path: Path, *, as_json: bool) -> int:
    """Report active and parked local pilot state without writing it."""
    active = active_pilot_report(manifest_path)
    parked = parked_pilot_reports()
    if active["exists"]:
        guidance = [
            "Resume or revise the active pilot, or park it before starting another local pilot."
        ]
        if not active["state_matches_manifest"]:
            guidance.append("The saved state is absent or does not match the manifest.")
    elif parked:
        guidance = [
            "Start fresh or restore a parked pilot with './cookbookctl unpark <path>'."
        ]
    else:
        guidance = ["No pilot state exists; start with a fresh local manifest."]
    report = {"active": active, "parked": parked, "guidance": guidance}
    if as_json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    print("Local pilot state")
    if active["exists"]:
        stages = (
            ", ".join(f"{name} {status}" for name, status in active["stages"].items())
            or "no matching recorded stages"
        )
        print(f"  Active: {active['path']} ({active.get('subdomain')}); {stages}")
    else:
        print(f"  Active: none ({active['path']} does not exist)")
    if parked:
        print("  Parked:")
        for item in parked:
            print(
                f"    - {item['path']} (subdomain {item['subdomain']}, "
                f"parked {item['parked_at']})"
            )
    else:
        print("  Parked: none")
    for line in guidance:
        print(f"  * {line}")
    return 0


def command_status(manifest_path: Path, *, as_json: bool) -> int:
    """Report manifest, state, and rendered-file status without writing."""
    active = active_pilot_report(manifest_path)
    state, matches = read_state(manifest_path)
    report = {
        "manifest": active,
        "state": {
            "exists": STATE_FILE.is_file(),
            "matches_manifest": matches,
            "version": state.get("version") if state else None,
            "stages": state.get("stages", {}) if state and matches else {},
            "updated_at": state.get("updated_at") if state else None,
        },
        "rendered_inputs": {
            "exists": GENERATED_TFVARS.is_file(),
            "path": str(GENERATED_TFVARS),
        },
    }
    if as_json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    print("Cookbook coordinator status")
    print(
        f"  Manifest: {'present' if active['exists'] else 'missing'} ({manifest_path})"
    )
    print(f"  State: {'matching' if matches else 'missing or stale'} ({STATE_FILE})")
    print(
        f"  Rendered inputs: {'present' if GENERATED_TFVARS.is_file() else 'missing'} "
        f"({GENERATED_TFVARS})"
    )
    return 0


def command_validate(manifest: dict[str, Any], manifest_path: Path) -> int:
    rendered = render_tfvars(manifest)
    print(f"Manifest validation passed: {manifest_path}")
    print(
        "Architecture: "
        f"{manifest['runtime']['target']} / "
        f"{manifest['agent']['language']}+{manifest['agent']['framework']} / "
        f"{manifest['agent']['taskstore']} / {manifest['agent']['llm_provider']}"
    )
    print(f"Rendered input contract validated: {len(rendered)} fields")
    print("No generated files or workflow state were written.")
    return 0


def command_render(manifest: dict[str, Any], manifest_path: Path, stdout: bool) -> int:
    rendered = render_tfvars(manifest)
    atomic_json(GENERATED_TFVARS, rendered)
    record_stage(manifest_path, "render", "complete")
    if stdout:
        print(json.dumps(rendered, indent=2, sort_keys=True))
    else:
        print(f"Rendered inputs: {GENERATED_TFVARS}")
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="cookbookctl", description=__doc__)
    result.add_argument(
        "--manifest", default="pilot.yaml", help="pilot manifest (default: pilot.yaml)"
    )
    subcommands = result.add_subparsers(dest="command", required=True)
    accounts = subcommands.add_parser(
        "accounts", help="discover the active global account and visible subaccounts"
    )
    accounts.add_argument(
        "--json", action="store_true", help="print machine-readable JSON"
    )
    pilots = subcommands.add_parser(
        "pilots", help="show active and parked local pilots"
    )
    pilots.add_argument(
        "--json", action="store_true", help="print machine-readable JSON"
    )
    subcommands.add_parser("park", help="archive the active manifest and local state")
    unpark = subcommands.add_parser("unpark", help="restore a parked local pilot")
    unpark.add_argument("path", help="archive under .cookbook/parked")
    status = subcommands.add_parser("status", help="show local coordinator status")
    status.add_argument(
        "--json", action="store_true", help="print machine-readable JSON"
    )
    subcommands.add_parser(
        "validate", help="validate a manifest without writing files or local state"
    )
    render = subcommands.add_parser("render", help="render deterministic local inputs")
    render.add_argument("--stdout", action="store_true", help="print rendered JSON")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    manifest_path = Path(args.manifest).expanduser().resolve()
    try:
        if args.command == "accounts":
            return command_accounts(manifest_path, as_json=args.json)
        if args.command == "pilots":
            return command_pilots(manifest_path, as_json=args.json)
        if args.command == "park":
            return command_park(manifest_path)
        if args.command == "unpark":
            return command_unpark(Path(args.path).expanduser(), manifest_path)
        if args.command == "status":
            return command_status(manifest_path, as_json=args.json)
        manifest = load_manifest(manifest_path)
        if args.command == "validate":
            return command_validate(manifest, manifest_path)
        if args.command == "render":
            return command_render(manifest, manifest_path, args.stdout)
        raise CookbookError(f"unsupported command: {args.command}")
    except CookbookError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
