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
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

try:
    import yaml
except ImportError:  # pragma: no cover - exercised on hosts without dependencies
    yaml = None


ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = ROOT / ".cookbook"
STATE_FILE = STATE_DIR / "state.json"
GENERATED_TFVARS = STATE_DIR / "generated.tfvars.json"

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
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def require_mapping(value: Any, name: str) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise CookbookError(f"{name} must be a YAML mapping")
    return value


def required_text(mapping: Mapping[str, Any], key: str, path: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise CookbookError(f"{path}.{key} must be a non-empty string")
    return value.strip()


def optional_text(mapping: Mapping[str, Any], key: str, path: str) -> Optional[str]:
    value = mapping.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise CookbookError(f"{path}.{key} must be null or a non-empty string")
    return value.strip()


def text_list(value: Any, path: str) -> List[str]:
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
    entitlements: Dict[str, Any], key: str, service_name: str, plan_name: str
) -> None:
    for value in entitlements.values():
        if value["service_name"] == service_name and value["plan_name"] == plan_name:
            return
    if key in entitlements:
        raise CookbookError(
            f"services.entitlements.{key} is reserved for {service_name}/{plan_name}"
        )
    entitlements[key] = {"service_name": service_name, "plan_name": plan_name}


def load_manifest(path: Path) -> Dict[str, Any]:
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


def normalize_manifest(source: Dict[str, Any]) -> Dict[str, Any]:
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
        raise CookbookError("runtime.cloudfoundry.enabled must be true for a cf runtime")
    if target == "kyma" and cloudfoundry["enabled"]:
        raise CookbookError("Cloud Foundry and Kyma are mutually exclusive runtime targets")
    cloudfoundry.setdefault("spaces", {"dev": {"name": "dev"}})
    spaces = require_mapping(cloudfoundry["spaces"], "runtime.cloudfoundry.spaces")
    if cloudfoundry["enabled"] and not spaces:
        raise CookbookError("runtime.cloudfoundry.spaces must contain at least one space")
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
            raise CookbookError("runtime.kyma.autoscaler.min must be a non-negative integer")
        if maximum is not None and (
            isinstance(maximum, bool) or not isinstance(maximum, int) or maximum < 1
        ):
            raise CookbookError("runtime.kyma.autoscaler.max must be a positive integer")
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
            "material architecture choices must be explicit; missing " + ", ".join(missing)
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
            isinstance(amount, bool) or not isinstance(amount, (int, float)) or amount < 0
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


def compact(mapping: Dict[str, Any]) -> Dict[str, Any]:
    return {key: value for key, value in mapping.items() if value is not None}


def render_tfvars(manifest: Dict[str, Any]) -> Dict[str, Any]:
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


def load_state(manifest_path: Path) -> Dict[str, Any]:
    digest = manifest_digest(manifest_path)
    state = {}
    if STATE_FILE.is_file():
        try:
            state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            state = {}
    if state.get("manifest_sha256") != digest:
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
    result = subprocess.run(
        ["btp", "--format", "json", *arguments],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


def subaccount_rows(payload: Any) -> List[Dict[str, Any]]:
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


def manifest_account_summary(path: Path) -> Optional[Dict[str, Any]]:
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
    manifest_subdomain: Optional[str], rows: List[Dict[str, Any]]
) -> tuple[str, Optional[Dict[str, Any]]]:
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

    rows = subaccount_rows(btp_json("list", "accounts/subaccount"))
    active = manifest_account_summary(manifest_path)
    session_subdomain = str(global_account.get("subdomain") or "")
    guidance = [
        "Discovery is read-only: cookbookctl does not select, adopt, or change a subaccount."
    ]
    manifest_report: Dict[str, Any] = {"exists": False, "path": str(manifest_path)}
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
        guidance.append("No manifest exists; review the visible subdomains before choosing one.")

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


def command_validate(manifest: Dict[str, Any], manifest_path: Path) -> int:
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


def command_render(manifest: Dict[str, Any], manifest_path: Path, stdout: bool) -> int:
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
    accounts.add_argument("--json", action="store_true", help="print machine-readable JSON")
    subcommands.add_parser(
        "validate", help="validate a manifest without writing files or local state"
    )
    render = subcommands.add_parser("render", help="render deterministic local inputs")
    render.add_argument("--stdout", action="store_true", help="print rendered JSON")
    return result


def main(argv: Optional[List[str]] = None) -> int:
    args = parser().parse_args(argv)
    manifest_path = Path(args.manifest).expanduser().resolve()
    try:
        if args.command == "accounts":
            return command_accounts(manifest_path, as_json=args.json)
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
