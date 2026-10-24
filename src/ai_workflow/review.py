"""Content-bound decisions; an approval never changes research acceptance."""

from __future__ import annotations

import hashlib
import json
import math


def json_safe(value):
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    return value


def artifact_hash(value) -> str:
    encoded = json.dumps(json_safe(value), sort_keys=True, ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def make_review_request(stage: str, contract: dict, payload: dict) -> dict:
    request = {"stage": stage, "contract": contract, "payload": json_safe(payload)}
    return {**request, "artifact_hash": artifact_hash(request)}


def validate_review_decision(request: dict, decision) -> dict:
    if (not isinstance(decision, dict) or decision.get("stage") != request["stage"]
            or decision.get("artifact_hash") != request["artifact_hash"]
            or decision.get("decision") not in {"approve", "reject"}
            or not isinstance(decision.get("reviewer"), str) or not decision["reviewer"].strip()
            or len(decision["reviewer"]) > 200 or not isinstance(decision.get("note", ""), str)
            or len(decision.get("note", "")) > 2000):
        raise ValueError("Invalid review decision or stale artifact hash")
    return {"stage": request["stage"], "artifact_hash": request["artifact_hash"],
            "decision": decision["decision"], "reviewer": decision["reviewer"].strip(),
            "note": decision.get("note", "")}
