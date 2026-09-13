"""Safe public payloads and submission validation for clinical practice."""

import hashlib
import secrets


DECISION_GROUPS = ("possible_diseases", "tests", "treatments", "measures")


def public_case_id(case: dict) -> str:
    return "case-" + hashlib.sha256(case["id"].encode()).hexdigest()[:20]


def shuffled(items: list[str]) -> list[str]:
    return secrets.SystemRandom().sample(items, len(items))


def public_case(case: dict) -> dict:
    # Whitelist, rather than remove a few known answer fields. Newly added
    # teacher metadata and answer keys cannot accidentally become public.
    return {
        "id": public_case_id(case),
        "format": case.get("format"),
        "background": case.get("background", ""),
        "patient_info": case.get("patient_info", {}),
        "options": {group: shuffled(case["options"][group]) for group in DECISION_GROUPS},
        "workflow": "all-decisions-v1",
    }


def validate_decision(case: dict, answers: dict) -> None:
    if len(answers.get("possible_diseases", [])) != 1:
        raise ValueError("请选择一项初步诊断或暴露分级。")
    for group in DECISION_GROUPS:
        selected = answers.get(group, [])
        if len(selected) != len(set(selected)) or not set(selected).issubset(case["options"][group]):
            raise ValueError("选项与当前情景不一致，请重新加载后作答。")
