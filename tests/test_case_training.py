import json
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import src.case_training as training
import src.main as main


class DiagnosisFirstTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(main.app)
        cls.cases = main.load_cases()

    def test_initial_payload_whitelists_patient_evidence_only(self):
        response = self.client.get("/api/cases")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["cache-control"], "no-store")
        public = response.json()["cases"]
        self.assertEqual(len(public), 10)
        for source, case in zip(self.cases, public):
            self.assertEqual(set(case), {"id", "format", "background", "patient_info", "options", "workflow"})
            self.assertEqual(set(case["options"]), {"possible_diseases"})
            self.assertEqual(set(case["options"]["possible_diseases"]), set(source["options"]["possible_diseases"]))
            self.assertNotIn(source["id"], json.dumps(case))
            self.assertEqual(case["workflow"], "diagnosis-first-v1")
            evidence = json.dumps([case["background"], case["patient_info"]], ensure_ascii=False)
            self.assertNotIn(source["knowledge_disease"], evidence)

    def test_public_serializer_does_not_shuffle_source_data(self):
        case = self.cases[0]
        before = json.dumps(case, sort_keys=True)
        with patch.object(training, "shuffled", side_effect=lambda items: list(reversed(items))):
            result = training.public_case(case)
        self.assertEqual(result["options"]["possible_diseases"], list(reversed(case["options"]["possible_diseases"])))
        self.assertEqual(json.dumps(case, sort_keys=True), before)

    def lock(self, case, diagnosis=None):
        diagnosis = diagnosis or case["options"]["possible_diseases"][0]
        response = self.client.post(f"/api/cases/{training.public_case_id(case)}/diagnosis", json={"diagnosis": diagnosis})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_every_diagnosis_can_advance_without_correctness_feedback(self):
        with patch.object(main, "complete") as model:
            for case in self.cases:
                for diagnosis in case["options"]["possible_diseases"]:
                    with self.subTest(case=case["id"], diagnosis=diagnosis):
                        result = self.lock(case, diagnosis)
                        self.assertEqual(set(result), {"attempt_token", "locked_diagnosis", "options"})
                        self.assertEqual(result["locked_diagnosis"], diagnosis)
                        self.assertEqual(set(result["options"]), set(training.FOLLOWUP_GROUPS))
                        for group in training.FOLLOWUP_GROUPS:
                            self.assertEqual(set(result["options"][group]), set(case["options"][group]))
                            self.assertEqual(len(result["options"][group]), 4)
            model.assert_not_called()

    def test_invalid_or_missing_diagnosis_cannot_unlock(self):
        case = self.cases[0]
        path = f"/api/cases/{training.public_case_id(case)}/diagnosis"
        for body in ({"diagnosis": ""}, {"diagnosis": "未知选项"}, {}):
            self.assertEqual(self.client.post(path, json=body).status_code, 422)

    def test_evaluation_requires_an_unmodified_locked_diagnosis(self):
        case = self.cases[0]
        attempt = self.lock(case)
        valid = {"attempt_token": attempt["attempt_token"], **case["correct_answers"]}
        path = f"/api/cases/{training.public_case_id(case)}/evaluate"
        with patch.object(main, "complete") as model:
            self.assertEqual(self.client.post(path, json=case["correct_answers"]).status_code, 422)
            for change in (
                {"attempt_token": "not-a-valid-token"},
                {"possible_diseases": [case["options"]["possible_diseases"][1]]},
                {"possible_diseases": []},
                {"tests": ["未提供的检查"]},
                {"tests": [case["options"]["tests"][0]] * 2},
            ):
                self.assertEqual(self.client.post(path, json={**valid, **change}).status_code, 409)
            other = training.public_case_id(self.cases[1])
            self.assertEqual(self.client.post(f"/api/cases/{other}/evaluate", json=valid).status_code, 409)
            model.assert_not_called()

    def test_expired_and_outdated_case_attempts_are_rejected(self):
        case = self.cases[0]
        with patch.object(training.time, "time", return_value=1):
            attempt = training.lock_diagnosis(case, case["options"]["possible_diseases"][0])
        with self.assertRaises(ValueError):
            training.validate_decision(case, attempt["attempt_token"], case["correct_answers"])
        current = self.lock(case)
        changed = {**case, "background": "更新后的病史"}
        with self.assertRaises(ValueError):
            training.validate_decision(changed, current["attempt_token"], case["correct_answers"])

    def test_final_feedback_includes_full_case_and_original_wrong_diagnosis(self):
        case = self.cases[1]
        wrong = case["options"]["possible_diseases"][1]
        attempt = self.lock(case, wrong)
        body = {**case["correct_answers"], "possible_diseases": [wrong], "attempt_token": attempt["attempt_token"]}
        with patch.object(main, "complete", return_value="初步诊断需修正。") as model:
            response = self.client.post(f"/api/cases/{training.public_case_id(case)}/evaluate", json=body)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["correct_answers"], case["correct_answers"])
        self.assertEqual(response.json()["reference_sop"], case["reference_sop"])
        messages = model.call_args.args[0]
        self.assertIn("不得因后续处置正确", messages[0]["content"])
        self.assertIn(wrong, messages[1]["content"])
        self.assertIn(case["patient_info"]["辅助检查"], messages[1]["content"])


if __name__ == "__main__":
    unittest.main()
