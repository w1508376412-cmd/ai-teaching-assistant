import json
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import src.case_training as training
import src.main as main


class AllDecisionsVisibleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(main.app)
        cls.cases = main.load_cases()

    def test_public_payload_contains_all_four_decision_groups(self):
        response = self.client.get("/api/cases")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["cache-control"], "no-store")
        public = response.json()["cases"]
        self.assertEqual(len(public), 10)
        for source, case in zip(self.cases, public):
            self.assertEqual(
                set(case),
                {"id", "format", "background", "patient_info", "options", "workflow"},
            )
            self.assertEqual(set(case["options"]), set(training.DECISION_GROUPS))
            self.assertEqual(case["workflow"], "all-decisions-v1")
            self.assertNotIn(source["id"], json.dumps(case))
            for group in training.DECISION_GROUPS:
                self.assertEqual(set(case["options"][group]), set(source["options"][group]))
                self.assertEqual(len(case["options"][group]), 4)
            evidence = json.dumps([case["background"], case["patient_info"]], ensure_ascii=False)
            self.assertNotIn(source["knowledge_disease"], evidence)

    def test_public_serializer_shuffles_each_group_without_mutating_source(self):
        case = self.cases[0]
        before = json.dumps(case, sort_keys=True)
        with patch.object(training, "shuffled", side_effect=lambda items: list(reversed(items))):
            result = training.public_case(case)
        for group in training.DECISION_GROUPS:
            self.assertEqual(result["options"][group], list(reversed(case["options"][group])))
        self.assertEqual(json.dumps(case, sort_keys=True), before)

    def test_submission_requires_one_diagnosis_and_valid_current_options(self):
        case = self.cases[0]
        valid = case["correct_answers"]
        training.validate_decision(case, valid)
        for change in (
            {"possible_diseases": []},
            {"possible_diseases": case["options"]["possible_diseases"][:2]},
            {"possible_diseases": ["未知诊断"]},
            {"tests": ["未提供的检查"]},
            {"tests": [case["options"]["tests"][0]] * 2},
        ):
            with self.subTest(change=change):
                with self.assertRaises(ValueError):
                    training.validate_decision(case, {**valid, **change})

    def test_evaluation_is_single_step_and_includes_full_case(self):
        case = self.cases[1]
        wrong = case["options"]["possible_diseases"][1]
        body = {**case["correct_answers"], "possible_diseases": [wrong]}
        path = f"/api/cases/{training.public_case_id(case)}/evaluate"
        with patch.object(main, "complete", return_value="诊断判断需修正。") as model:
            response = self.client.post(path, json=body)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["correct_answers"], case["correct_answers"])
        messages = model.call_args.args[0]
        self.assertIn("同时完成诊断判断", messages[0]["content"])
        self.assertIn(wrong, messages[1]["content"])
        self.assertIn(case["patient_info"]["辅助检查"], messages[1]["content"])

    def test_invalid_submission_is_rejected_before_model_call(self):
        case = self.cases[0]
        path = f"/api/cases/{training.public_case_id(case)}/evaluate"
        with patch.object(main, "complete") as model:
            response = self.client.post(path, json={**case["correct_answers"], "tests": ["未知检查"]})
        self.assertEqual(response.status_code, 409)
        model.assert_not_called()

    def test_diagnosis_unlock_endpoint_is_removed(self):
        case_id = training.public_case_id(self.cases[0])
        response = self.client.post(f"/api/cases/{case_id}/diagnosis", json={"diagnosis": "麻疹"})
        self.assertIn(response.status_code, {404, 405})


if __name__ == "__main__":
    unittest.main()
