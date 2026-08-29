import json
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
CASES_DIR = ROOT_DIR / "cases"
RAG_PATH = ROOT_DIR / "rag_data" / "chunks.jsonl"


class ClinicalScenarioLibraryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cases = [
            json.loads(path.read_text(encoding="utf-8"))
            for path in sorted(CASES_DIR.glob("*.json"))
        ]
        cls.knowledge_diseases = {
            json.loads(line)["disease"]
            for line in RAG_PATH.read_text(encoding="utf-8").splitlines()
            if line.strip()
        }

    def test_library_contains_ten_clinical_scenarios(self) -> None:
        self.assertEqual(len(self.cases), 10)
        self.assertEqual(len({case["id"] for case in self.cases}), 10)
        self.assertEqual(len({case["title"] for case in self.cases}), 10)

    def test_every_scenario_maps_to_the_knowledge_base(self) -> None:
        for case in self.cases:
            with self.subTest(case=case["id"]):
                self.assertIn(case["knowledge_disease"], self.knowledge_diseases)
                self.assertEqual(case["format"], "interactive_v2")
                self.assertGreaterEqual(len(case["learning_objectives"]), 3)
                self.assertIn(case["difficulty"], {"基础", "进阶"})

    def test_correct_answers_are_available_options(self) -> None:
        groups = ("possible_diseases", "measures", "treatments")
        for case in self.cases:
            for group in groups:
                with self.subTest(case=case["id"], group=group):
                    options = case["options"][group]
                    correct = case["correct_answers"][group]
                    self.assertGreaterEqual(len(options), 4)
                    self.assertTrue(correct)
                    self.assertTrue(set(correct).issubset(options))

    def test_old_customs_training_context_is_removed(self) -> None:
        forbidden = ("入境旅客", "海关", "口岸", "卫生检疫", "关员", "就诊方便卡")
        for case in self.cases:
            serialized = json.dumps(case, ensure_ascii=False)
            with self.subTest(case=case["id"]):
                for phrase in forbidden:
                    self.assertNotIn(phrase, serialized)


if __name__ == "__main__":
    unittest.main()
