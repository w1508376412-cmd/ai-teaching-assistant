import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from collections import Counter
from unittest.mock import patch

from fastapi.testclient import TestClient
from src import main, study
from src.assessment_bank import PAIRS, CASE_PAIRS, bank_with_sources


class StudyTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.store = study.Store(self.folder.name + "/study.sqlite3")
        self.mock = patch.object(study, "get_store", return_value=self.store)
        self.mock.start()
        self.addCleanup(self.mock.stop)
        self.env = patch.dict("os.environ", {"ADMIN_PASSWORD": "faculty-test-password"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.client = TestClient(main.app)
        self.addCleanup(self.client.close)
        self.admin = {"X-Admin-Password": "faculty-test-password"}

    def login(self, number="2026001", name="测试学生", client=None):
        response = (client or self.client).post("/api/session/login", json={"student_no": number, "name": name})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def start(self, phase="pre"):
        response = self.client.post("/api/assessments/start", json={"phase": phase})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def answer_key(self, paper):
        with self.store.db() as c:
            private = json.loads(c.execute("SELECT paper FROM attempts WHERE id=?", (paper["id"],)).fetchone()[0])
        return {q["id"]: q["correct"] for q in private["questions"]}

    def finish_pre(self):
        self.login()
        paper = self.start()
        response = self.client.post(f"/api/assessments/{paper['id']}/submit", json={"answers": self.answer_key(paper), "revision": 0})
        self.assertEqual(response.status_code, 200, response.text)
        return paper, response.json()

    def test_all_pairs_valid_and_source_mapped(self):
        bank_with_sources()
        for pair in PAIRS + CASE_PAIRS:
            for form in ("A", "B"):
                questions = pair[form].get("questions", [pair[form]])
                for q in questions:
                    self.assertEqual(len(q["choices"]), 4)
                    self.assertEqual(len(set(q["choices"])), 4)
                    self.assertIn(q["answer"], q["choices"])

    def test_parallel_forms_frozen_and_equal_blueprint(self):
        a, b = [self.store.make_paper(f) for f in ("A", "B")]
        self.assertEqual(len(a["questions"]), 28)
        self.assertEqual(len(a["cases"]), 2)
        self.assertEqual(sum(q["points"] for q in a["questions"]), 100)
        self.assertEqual(Counter(q["difficulty"] for q in a["questions"] if not q["case_id"]), {"基础": 8, "应用": 8, "综合": 4})
        for x, y in zip(a["questions"], b["questions"]):
            for key in ("pair", "difficulty", "point", "domain", "points"):
                self.assertEqual(x[key], y[key])
            self.assertNotEqual(x["stem"], y["stem"])
        with patch.object(study, "PAIRS", []):
            reloaded = study.Store(self.store.path).make_paper("A")
        self.assertEqual([q["stem"] for q in a["questions"]], [q["stem"] for q in reloaded["questions"]])
        self.assertNotEqual(a["questions"][0]["options"], reloaded["questions"][0]["options"])

    def test_pretest_gate_server_side_and_no_answer_leak(self):
        for path in ("/api/cases", "/api/knowledge", "/api/rash-atlas", "/assets/rash-atlas/atlas.json"):
            self.assertEqual(self.client.get(path).status_code, 401)
        self.login()
        for path in ("/api/cases", "/api/knowledge", "/api/rash-atlas", "/assets/rash-atlas/atlas.json"):
            self.assertEqual(self.client.get(path).status_code, 403)
        self.assertEqual(self.client.post("/api/chat/knowledge", json={"messages": [{"role": "user", "content": "测试"}]}).status_code, 403)
        p = self.start()
        for q in p["questions"]:
            for key in ("correct", "explanation", "pair", "sources", "disease"):
                self.assertNotIn(key, q)
        self.assertEqual(self.client.get("/api/assessment-results").json(), {"ready": False})
        self.assertEqual(self.client.get("/api/admin/study/papers").status_code, 401)
        self.assertEqual(self.client.post("/api/assessments/start", json={"phase": "post"}).status_code, 403)

    def test_drafts_resume_conflicts_and_owner_isolation(self):
        self.login()
        p = self.start()
        self.assertEqual(self.start()["id"], p["id"])
        answers = {p["questions"][0]["id"]: p["questions"][0]["options"][0]["id"]}
        path = f"/api/assessments/{p['id']}"
        self.assertEqual(self.client.put(path + "/draft", json={"answers": answers, "revision": 0}).json()["revision"], 1)
        self.assertEqual(self.client.put(path + "/draft", json={"answers": answers, "revision": 0}).status_code, 409)
        self.assertEqual(self.client.post(path + "/submit", json={"answers": answers, "revision": 1}).status_code, 422)
        self.assertEqual(self.client.put(path + "/draft", json={"answers": {"q01": "fabricated"}, "revision": 1}).status_code, 422)
        with TestClient(main.app) as other:
            self.login("2026002", client=other)
            self.assertEqual(other.get(path).status_code, 404)
            self.assertEqual(other.put(path + "/draft", json={"answers": answers, "revision": 1}).status_code, 404)
        self.client.post("/api/session/logout")
        self.login()
        self.assertEqual(self.client.get(path).json()["answers"], answers)

    def test_full_workflow_teacher_release_scoring_and_exports(self):
        pre, status = self.finish_pre()
        self.assertTrue(status["pre_completed"])
        self.assertNotIn("score", status["results"][0])
        self.assertEqual(self.client.get("/api/cases").status_code, 200)
        self.client.post("/api/session/logout")
        self.assertTrue(self.login()["pre_completed"])
        self.assertEqual(self.client.post("/api/assessments/start", json={"phase": "post"}).status_code, 403)
        self.assertEqual(self.client.put("/api/admin/study/release", json={"open": True}).status_code, 401)
        self.client.put("/api/admin/study/release", headers=self.admin, json={"open": True})
        post = self.start("post")
        self.assertNotEqual(post["form"], pre["form"])
        self.assertEqual(self.client.get("/api/cases").status_code, 403)
        self.client.put("/api/admin/study/release", headers=self.admin, json={"open": False})
        key = self.answer_key(post)
        key["q01"] = next(o["id"] for o in post["questions"][0]["options"] if o["id"] != key["q01"])
        path = f"/api/assessments/{post['id']}"
        done = self.client.post(path + "/submit", json={"answers": key, "revision": 0})
        self.assertEqual(done.status_code, 200)
        self.assertEqual([r["score"] for r in done.json()["results"]], [100, 97])
        self.assertEqual(self.client.get("/api/cases").status_code, 200)
        self.assertTrue(self.client.get("/api/assessment-results").json()["ready"])
        self.assertEqual(self.client.post(path + "/submit", json={"answers": {}, "revision": 0}).json(), done.json())
        self.assertEqual(self.client.put(path + "/draft", json={"answers": {}, "revision": 1}).status_code, 409)
        summary = self.client.get("/api/admin/study", headers=self.admin).json()
        self.assertEqual(summary["mean_gain"], -3)
        items = self.client.get("/api/admin/study/export?kind=items", headers=self.admin)
        self.assertIn("no-store", items.headers["cache-control"])
        self.assertIn("配对知识点ID", items.text)
        self.assertIn("2026001", items.text)

    def test_identity_cookie_origin_and_teacher_authorization(self):
        response = self.client.post("/api/session/login", json={"student_no": "2026003", "name": "测试学生"})
        self.assertIn("HttpOnly", response.headers["set-cookie"])
        self.assertIn("SameSite=lax", response.headers["set-cookie"])
        self.assertIn("no-store", response.headers["cache-control"])
        self.assertEqual(self.client.post("/api/session/login", json={"student_no": "2026003", "name": "其他姓名"}).status_code, 409)
        self.assertEqual(self.client.post("/api/session/logout", headers={"Origin": "https://evil.example"}).status_code, 403)
        self.assertEqual(self.client.get("/api/admin/study", headers={"X-Admin-Password": "wrong"}).status_code, 401)

    def test_atomic_start_does_not_create_duplicate_attempts(self):
        user, _ = self.store.login("2026123", "并发测试", "local")
        with ThreadPoolExecutor(max_workers=4) as executor:
            attempts = list(executor.map(lambda _: self.store.start(user, "pre"), range(4)))
        self.assertEqual(len({p["id"] for p in attempts}), 1)

    def test_teacher_identity_login_bypasses_exam_but_not_student_permissions(self):
        with patch.dict("os.environ", {"TEACHER_STUDENT_NO": "TEACHER-TEST", "TEACHER_NAME": "本地测试教师"}):
            self.assertEqual(self.client.post("/api/session/login", json={"student_no": "TEACHER-TEST", "name": "错误姓名"}).status_code, 401)
            result = self.login("TEACHER-TEST", "本地测试教师")
            self.assertEqual(result["role"], "teacher")
            self.assertFalse(result["pre_completed"])
            self.assertEqual(self.client.get("/api/cases").status_code, 200)
            self.assertEqual(self.client.post("/api/assessments/start", json={"phase": "pre"}).status_code, 403)
            self.assertEqual(self.client.get("/api/admin/content").status_code, 200)
            self.assertEqual(self.client.get("/api/admin/study/papers").status_code, 200)
            self.assertEqual(self.client.put("/api/admin/study/release", json={"open": True}).status_code, 200)
            self.assertEqual(self.client.get("/api/admin/study").json()["registered"], 0)
            self.client.post("/api/session/logout")
            self.login()
            self.assertEqual(self.client.get("/api/admin/study").status_code, 401)
            self.assertEqual(self.client.get("/api/admin/content").status_code, 401)
            self.assertEqual(self.client.put("/api/admin/study/release", json={"open": False}).status_code, 401)


if __name__ == "__main__":
    unittest.main()
