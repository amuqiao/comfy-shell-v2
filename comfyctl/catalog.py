from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT_DIR / "catalog" / "comfyui.json"


def version_parts(value: str | None) -> tuple[int, ...]:
    if value is None:
        return ()
    return tuple(int(part) for part in re.findall(r"\d+", value))


def version_at_least(value: str | None, minimum: str) -> bool:
    parts = version_parts(value)
    minimum_parts = version_parts(minimum)
    if not parts or not minimum_parts:
        return False
    length = max(len(parts), len(minimum_parts))
    padded = parts + (0,) * (length - len(parts))
    minimum_padded = minimum_parts + (0,) * (length - len(minimum_parts))
    return padded >= minimum_padded


@lru_cache
def load_catalog(path: str | None = None) -> dict[str, Any]:
    catalog_path = Path(path) if path is not None else CATALOG_PATH
    data = json.loads(catalog_path.read_text(encoding="utf-8"))
    _validate_catalog(data)
    return data


def _validate_catalog(data: dict[str, Any]) -> None:
    if not isinstance(data.get("github"), dict):
        raise ValueError("catalog.github is required")
    versions = data.get("versions")
    profiles = data.get("runtime_profiles")
    rules = data.get("recommendation_rules")
    if not isinstance(versions, list) or not versions:
        raise ValueError("catalog.versions must be a non-empty list")
    if not isinstance(profiles, list) or not profiles:
        raise ValueError("catalog.runtime_profiles must be a non-empty list")
    if not isinstance(rules, list) or not rules:
        raise ValueError("catalog.recommendation_rules must be a non-empty list")
    version_ids = set()
    visible_version_count = 0
    for item in versions:
        if not isinstance(item, dict):
            raise ValueError("catalog.versions entries must be objects")
        for key in ("id", "label", "channel", "ref"):
            if not item.get(key):
                raise ValueError(f"catalog version missing {key}")
        if item.get("advanced") is not True:
            visible_version_count += 1
        if item["id"] in version_ids:
            raise ValueError(f"duplicate catalog version id: {item['id']}")
        version_ids.add(item["id"])
    if visible_version_count < 1:
        raise ValueError("catalog.versions must include at least one non-advanced entry")
    profile_ids = set()
    profile_torch_profiles = set()
    visible_profile_count = 0
    for item in profiles:
        if not isinstance(item, dict):
            raise ValueError("catalog.runtime_profiles entries must be objects")
        for key in ("id", "label", "python_version", "torch_profile"):
            if not item.get(key):
                raise ValueError(f"catalog runtime profile missing {key}")
        if item.get("advanced") is not True:
            visible_profile_count += 1
        packages = item.get("packages") or {}
        if item.get("backend") != "requirements":
            required_packages = {"torch", "torchvision", "torchaudio"}
            if not isinstance(packages, dict) or not required_packages.issubset(packages):
                raise ValueError(f"catalog runtime profile missing torch packages: {item['id']}")
        if item["id"] in profile_ids:
            raise ValueError(f"duplicate catalog runtime profile id: {item['id']}")
        if item["torch_profile"] in profile_torch_profiles:
            raise ValueError(f"duplicate catalog torch_profile: {item['torch_profile']}")
        profile_ids.add(item["id"])
        profile_torch_profiles.add(item["torch_profile"])
    if visible_profile_count < 1:
        raise ValueError("catalog.runtime_profiles must include at least one non-advanced entry")
    for rule in rules:
        if not isinstance(rule, dict):
            raise ValueError("catalog.recommendation_rules entries must be objects")
        if rule.get("version_id") not in version_ids:
            raise ValueError(f"unknown recommendation version_id: {rule.get('version_id')}")
        if rule.get("runtime_profile_id") not in profile_ids:
            raise ValueError(f"unknown recommendation runtime_profile_id: {rule.get('runtime_profile_id')}")


def catalog_payload() -> dict[str, Any]:
    return load_catalog()


def supported_torch_profiles() -> frozenset[str]:
    return frozenset(str(item["torch_profile"]) for item in load_catalog()["runtime_profiles"])


def version_by_id(version_id: str) -> dict[str, Any]:
    for item in load_catalog()["versions"]:
        if item["id"] == version_id:
            return dict(item)
    raise KeyError(version_id)


def runtime_profile_by_id(profile_id: str) -> dict[str, Any]:
    for item in load_catalog()["runtime_profiles"]:
        if item["id"] == profile_id:
            return dict(item)
    raise KeyError(profile_id)


def default_version() -> dict[str, Any]:
    versions = load_catalog()["versions"]
    for item in versions:
        if item.get("recommended") is True:
            return dict(item)
    return dict(versions[0])


def default_runtime_profile() -> dict[str, Any]:
    profiles = load_catalog()["runtime_profiles"]
    for item in profiles:
        if item.get("recommended") is True:
            return dict(item)
    return dict(profiles[0])


def torch_profile_packages(torch_profile: str) -> dict[str, str]:
    for item in load_catalog()["runtime_profiles"]:
        if item["torch_profile"] == torch_profile:
            packages = item.get("packages") or {}
            if not isinstance(packages, dict):
                raise ValueError(f"catalog runtime profile has invalid packages: {item['id']}")
            return {str(key): str(value) for key, value in packages.items()}
    raise KeyError(torch_profile)


def torch_profile_backend(torch_profile: str) -> str | None:
    for item in load_catalog()["runtime_profiles"]:
        if item["torch_profile"] == torch_profile:
            backend = item.get("backend")
            if backend == "requirements" or backend is None:
                return None
            return str(backend)
    raise KeyError(torch_profile)


def recommendation(*, cuda_version: str | None, gpus: list[dict[str, str]]) -> dict[str, Any]:
    vendor = "nvidia" if gpus else "none"
    catalog = load_catalog()
    for rule in catalog["recommendation_rules"]:
        when = rule.get("when") or {}
        if when.get("gpu_vendor") != vendor:
            continue
        cuda_min = when.get("cuda_min")
        if cuda_min and not version_at_least(cuda_version, str(cuda_min)):
            continue
        version = version_by_id(str(rule["version_id"]))
        profile = runtime_profile_by_id(str(rule["runtime_profile_id"]))
        gpu_ids = [gpus[0]["index"]] if rule.get("gpu") == "first" and gpus else []
        return {
            "rule_id": rule["id"],
            "version_id": version["id"],
            "version_label": version["label"],
            "version_channel": version["channel"],
            "runtime_profile_id": profile["id"],
            "runtime_profile_label": profile["label"],
            "comfy_ref": version["ref"],
            "python_version": profile["python_version"],
            "torch_profile": profile["torch_profile"],
            "gpu_ids": gpu_ids,
            "reason": rule.get("reason", ""),
            "warnings": list(rule.get("warnings") or []),
        }
    raise ValueError(f"no recommendation rule matched gpu_vendor={vendor} cuda_version={cuda_version}")
