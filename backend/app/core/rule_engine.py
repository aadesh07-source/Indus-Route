"""Deterministic rule engine — the ONLY component that decides requirements.

Pure functions: input is a business-profile dict, output is approvals /
documents / SLA data. No I/O, no AI calls, no DB access inside evaluation
(makes it independently unit-testable and demonstrably deterministic).
"""
import json
import re
from pathlib import Path
from typing import Any, Optional

RULES_DIR = Path(__file__).resolve().parents[1] / "rules"

_cache: Optional[dict] = None


def _load_json(path: Path) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def load_all_rules() -> dict:
    """Load and cache sector rule tables + document check specs."""
    global _cache
    if _cache is not None:
        return _cache
    sectors: dict = {}
    for path in sorted(RULES_DIR.glob("*.json")):
        if path.name == "document_checks.json":
            continue
        data = _load_json(path)
        if data.get("sector"):
            sectors[data["sector"]] = data
    _cache = {
        "sectors": sectors,
        "document_checks": _load_json(RULES_DIR / "document_checks.json"),
    }
    return _cache


def list_sectors() -> list:
    rules = load_all_rules()
    return [
        {"sector": key, "label": data.get("label", key),
         "approval_count": len(data.get("approvals", []))}
        for key, data in rules["sectors"].items()
    ]


def get_doc_spec(doc_type: str) -> Optional[dict]:
    return load_all_rules()["document_checks"].get(doc_type)


def list_doc_types() -> list:
    return sorted(load_all_rules()["document_checks"].keys())


def _eval_condition(condition: Optional[dict], profile: dict) -> bool:
    """Evaluate a data-driven profile condition. Unknown ops fail safe (False)."""
    if not condition:
        return True
    field, op, value = condition.get("field"), condition.get("op"), condition.get("value")
    actual = profile.get(field)
    try:
        if op == "eq":
            return actual == value
        if op == "neq":
            return actual != value
        if op == "gte":
            return float(actual or 0) >= float(value)
        if op == "lte":
            return float(actual or 0) <= float(value)
        if op == "in":
            return actual in (value or [])
        if op == "exists":
            return bool(actual)
    except (TypeError, ValueError):
        return False
    return False


def _approval_to_dict(appr: dict) -> dict:
    return {
        "id": appr["id"],
        "code": appr.get("code", appr["id"]),
        "name": appr.get("name", ""),
        "department": appr.get("department", ""),
        "description": appr.get("description", ""),
        "sla_days": int(appr.get("sla_days", 15)),
        "required_documents": list(appr.get("required_documents", [])),
        "dependency_ids": list(appr.get("dependency_ids", [])),
        "parallel_group": appr.get("parallel_group", ""),
        "green_channel_eligible": bool(appr.get("green_channel_eligible", False)),
    }


def evaluate_profile(profile: dict) -> dict:
    """Deterministically map a business profile to its applicable approvals."""
    sector = str(profile.get("sector", "")).strip().lower()
    rules = load_all_rules()
    sector_data = rules["sectors"].get(sector)
    if sector_data is None:
        return {
            "sector": sector,
            "known": False,
            "approvals": [],
            "excluded": [],
            "parallel_groups": {},
            "max_sla_days": 0,
            "total_sla_days": 0,
            "note": "Sector not in rule set. Contact the department helpdesk.",
        }

    applicable, excluded = [], []
    for appr in sector_data.get("approvals", []):
        if _eval_condition(appr.get("condition"), profile):
            applicable.append(_approval_to_dict(appr))
        else:
            excluded.append({
                "id": appr["id"], "code": appr.get("code"), "name": appr.get("name"),
                "reason": "Not applicable for this profile (rule condition not met).",
            })

    parallel_groups: dict = {}
    for appr in applicable:
        group = appr["parallel_group"] or "sequential"
        parallel_groups.setdefault(group, []).append(appr["code"])

    return {
        "sector": sector,
        "known": True,
        "approvals": applicable,
        "excluded": excluded,
        "parallel_groups": parallel_groups,
        "max_sla_days": max([a["sla_days"] for a in applicable], default=0),
        "total_sla_days": sum(a["sla_days"] for a in applicable),
        "note": (
            "Approvals in the same parallel group can be pursued simultaneously; "
            "dependency_ids list approvals that must be granted first."
        ),
    }


def get_approval_by_code(code: str, sector: Optional[str] = None) -> Optional[dict]:
    rules = load_all_rules()
    for key, data in rules["sectors"].items():
        if sector and key != sector:
            continue
        for appr in data.get("approvals", []):
            if appr.get("code") == code or appr.get("id") == code:
                return _approval_to_dict(appr)
    return None


def search_rules_text(question: str) -> list:
    """RAG-lite: keyword retrieval over the rule set (deterministic, cited)."""
    rules = load_all_rules()
    tokens = [t for t in re.split(r"\W+", question.lower()) if len(t) > 3]
    results = []
    for key, data in rules["sectors"].items():
        for appr in data.get("approvals", []):
            haystack = " ".join([
                str(appr.get("name", "")), str(appr.get("description", "")),
                str(appr.get("department", "")), key, str(data.get("label", "")),
            ]).lower()
            matched = [t for t in tokens if t in haystack]
            if matched:
                results.append({
                    "source": "rule_table:{}.{}".format(key, appr.get("code")),
                    "title": appr.get("name", ""),
                    "department": appr.get("department", ""),
                    "sla_days": appr.get("sla_days"),
                    "description": appr.get("description", ""),
                    "required_documents": appr.get("required_documents", []),
                    "matched_keywords": matched,
                    "score": len(matched),
                })
    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:5]

