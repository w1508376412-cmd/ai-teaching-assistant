"""Staged clinical practice: release decisions only after an initial diagnosis.

This is a teaching workflow, not a proctored exam. Public payloads intentionally
exclude teaching targets, answer keys and disease-bearing file identifiers.
Set CASE_ATTEMPT_SECRET to the same value when running multiple API workers.
"""

import base64
import hashlib
import hmac
import json
import os
import secrets
import time


FOLLOWUP_GROUPS = ("tests", "treatments", "measures")
ATTEMPT_TTL = 24 * 60 * 60
_SIGNING_KEY = os.getenv("CASE_ATTEMPT_SECRET", "").encode() or secrets.token_bytes(32)


def public_case_id(case: dict) -> str:
    return "case-" + hashlib.sha256(case["id"].encode()).hexdigest()[:20]


def shuffled(items: list[str]) -> list[str]:
    return secrets.SystemRandom().sample(items, len(items))


def public_case(case: dict) -> dict:
    # Whitelist, rather than remove a few known answer fields. Newly added
    # teacher metadata must never accidentally become visible before diagnosis.
    return {
        "id": public_case_id(case),
        "format": case.get("format"),
        "background": case.get("background", ""),
        "patient_info": case.get("patient_info", {}),
        "options": {
            "possible_diseases": shuffled(case["options"]["possible_diseases"]),
        },
        "workflow": "diagnosis-first-v1",
    }


def _fingerprint(case: dict) -> str:
    data = {key: value for key, value in case.items() if not key.startswith("_")}
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def lock_diagnosis(case: dict, diagnosis: str) -> dict:
    if diagnosis not in case["options"]["possible_diseases"]:
        raise ValueError("请选择本情景提供的一项初步诊断。")
    payload = json.dumps({
        "case": public_case_id(case),
        "revision": _fingerprint(case),
        "diagnosis": diagnosis,
        "expires": int(time.time()) + ATTEMPT_TTL,
        "nonce": secrets.token_hex(12),
    }, ensure_ascii=False, separators=(",", ":")).encode()
    encoded = base64.urlsafe_b64encode(payload).decode().rstrip("=")
    signature = hmac.new(_SIGNING_KEY, encoded.encode(), hashlib.sha256).hexdigest()
    # Deliberately identical response shape for correct and incorrect diagnoses.
    return {
        "attempt_token": f"{encoded}.{signature}",
        "locked_diagnosis": diagnosis,
        "options": {group: shuffled(case["options"][group]) for group in FOLLOWUP_GROUPS},
    }


def validate_decision(case: dict, token: str, answers: dict) -> None:
    try:
        encoded, signature = token.split(".")
        expected = hmac.new(_SIGNING_KEY, encoded.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError
        payload = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
        if (payload["case"] != public_case_id(case)
                or payload["revision"] != _fingerprint(case)
                or payload["expires"] <= time.time()):
            raise ValueError
    except (ValueError, KeyError, TypeError, UnicodeError):
        raise ValueError("作答记录无效或已过期，请重新开始本情景并先确认诊断。") from None
    if answers.get("possible_diseases") != [payload["diagnosis"]]:
        raise ValueError("初步诊断已锁定，本轮作答不能修改。")
    for group in FOLLOWUP_GROUPS:
        selected = answers.get(group, [])
        if len(selected) != len(set(selected)) or not set(selected).issubset(case["options"][group]):
            raise ValueError("选项与当前情景不一致，请重新加载后作答。")
