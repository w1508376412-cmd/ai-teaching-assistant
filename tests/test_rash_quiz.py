import json
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from src import main, study, rash_quiz


class RashQuizTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.store = study.Store(folder.name + "/study.sqlite3")
        for module in (study, rash_quiz):
            mock = patch.object(module, "get_store", return_value=self.store)
            mock.start()
            self.addCleanup(mock.stop)
        mock = patch.dict("os.environ", {"ADMIN_PASSWORD": "rash-test-password"})
        mock.start()
        self.addCleanup(mock.stop)
        self.client = TestClient(main.app)
        self.addCleanup(self.client.close)

    def login(self, client=None, number="RASH-001", complete=True):
        client = client or self.client
        response = client.post("/api/session/login", json={"student_no": number, "name": "看图测试"})
        self.assertEqual(response.status_code, 200)
        if complete:
            p = client.post("/api/assessments/start", json={"phase": "pre"}).json()
            with self.store.db() as c:
                paper = json.loads(c.execute("SELECT paper FROM attempts WHERE id=?", (p["id"],)).fetchone()[0])
            answers = {q["id"]: q["correct"] for q in paper["questions"]}
            self.assertEqual(client.post(f"/api/assessments/{p['id']}/submit", json={"answers": answers, "revision": 0}).status_code, 200)

    def test_bank_images_sources_and_choices(self):
        bank = rash_quiz.bank()
        self.assertEqual(len(bank), 8)
        for q in bank:
            self.assertEqual(len(set(q["choices"])), 4)
            self.assertIn(q["answer"], q["choices"])
            self.assertTrue(q["image"]["source_label"])
            self.assertTrue(q["image"]["caption"] and q["image"]["license"])
            self.assertTrue(q["context"].startswith("模拟病史"))

    def test_access_gate_owner_and_no_premature_answers(self):
        self.assertEqual(self.client.post("/api/rash-quiz", json={}).status_code, 401)
        self.login(complete=False)
        self.assertEqual(self.client.post("/api/rash-quiz", json={}).status_code, 403)
        self.login()
        data = self.client.post("/api/rash-quiz", json={}).json()
        q = data["question"]
        self.assertEqual(set(q), {"id", "context", "options", "image_url", "alt"})
        self.assertEqual(data["history"], [])
        self.assertRegex(q["image_url"], r"^/api/rash-quiz/[a-f0-9]{32}/image/[a-f0-9]{16}$")
        image = self.client.get(q["image_url"])
        self.assertEqual(image.status_code, 200)
        self.assertEqual(image.headers["content-type"], "image/webp")
        self.assertIn("no-store", image.headers["cache-control"])
        self.assertNotIn("content-disposition", image.headers)
        with TestClient(main.app) as other:
            self.login(other, "RASH-002")
            self.assertEqual(other.get(f"/api/rash-quiz/{data['id']}").status_code, 404)
            self.assertEqual(other.get(q["image_url"]).status_code, 404)
            self.assertEqual(other.post(f"/api/rash-quiz/{data['id']}/answer", json={"question_id": q["id"], "choice": q["options"][0]}).status_code, 404)
        self.client.put("/api/admin/study/release", headers={"X-Admin-Password": "rash-test-password"}, json={"open": True})
        self.client.post("/api/assessments/start", json={"phase": "post"})
        self.assertEqual(self.client.get(q["image_url"]).status_code, 403)
        self.assertEqual(self.client.get(f"/api/rash-quiz/{data['id']}").status_code, 403)
        self.assertEqual(self.client.post("/api/rash-quiz", json={}).status_code, 403)

    def test_five_questions_scoring_resuming_and_immutable_answers(self):
        self.login()
        start = self.client.post("/api/rash-quiz", json={}).json()
        base = f"/api/rash-quiz/{start['id']}"
        with self.store.db() as c:
            private = json.loads(c.execute("SELECT questions FROM rash_quizzes WHERE id=?", (start["id"],)).fetchone()[0])
        self.assertEqual(len({q["disease"] for q in private}), 5)
        self.assertEqual(self.client.get(base + "?index=1").status_code, 409)
        self.assertEqual(self.client.get(base + "/image/" + private[1]["id"]).status_code, 404)
        self.assertEqual(self.client.post(base + "/answer", json={"question_id": private[1]["id"], "choice": private[1]["answer"]}).status_code, 409)
        self.assertEqual(self.client.post(base + "/answer", json={"question_id": private[0]["id"], "choice": "伪造选项"}).status_code, 422)
        for n, q in enumerate(private):
            current = self.client.get(base + f"?index={n}").json()["question"]
            self.assertNotIn("answer", current)
            choice = q["answer"] if n < 3 else next(o for o in q["options"] if o != q["answer"])
            body = {"question_id": q["id"], "choice": choice}
            response = self.client.post(base + "/answer", json=body)
            self.assertEqual(response.status_code, 200)
            feedback = response.json()
            self.assertEqual(feedback["question"]["correct"], n < 3)
            self.assertTrue(feedback["question"]["explanation"])
            self.assertEqual(feedback["question"]["source"]["source_label"], q["image"]["source_label"])
            self.assertEqual(self.client.post(base + "/answer", json=body).json(), feedback)
            body["choice"] = next(o for o in q["options"] if o != choice)
            self.assertEqual(self.client.post(base + "/answer", json=body).status_code, 409)
            self.assertEqual(self.client.get(base + f"?index={n}").json(), feedback)
        done = self.client.get(base).json()
        self.assertTrue(done["completed"])
        self.assertIsNone(done["question"])
        self.assertEqual(done["correct_count"], 3)
        self.assertEqual(len(done["history"]), 5)
        self.client.post("/api/session/logout")
        self.login(complete=False)
        self.assertEqual(self.client.get(base).json(), done)


if __name__ == "__main__":
    unittest.main()
