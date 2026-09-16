"""Regression guard for the retired standalone atlas quiz endpoints."""
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from src import main, study


class RetiredRashQuizTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.store = study.Store(folder.name + "/study.sqlite3")
        store_patch = patch.object(study, "get_store", return_value=self.store)
        store_patch.start()
        self.addCleanup(store_patch.stop)
        env = patch.dict("os.environ", {"ADMIN_PASSWORD": "retired-test-only",
                                       "TEACHER_STUDENT_NO": "TEACHER-TEST",
                                       "TEACHER_NAME": "本地测试教师"})
        env.start()
        self.addCleanup(env.stop)
        self.client = TestClient(main.app)
        self.addCleanup(self.client.close)

    def assert_retired(self):
        ident, qid = "a" * 32, "b" * 16
        requests = (
            ("POST", "/api/rash-quiz", {}),
            ("GET", "/api/rash-quiz", None),
            ("GET", f"/api/rash-quiz/{ident}", None),
            ("GET", f"/api/rash-quiz/{ident}?index=0", None),
            ("GET", f"/api/rash-quiz/{ident}/image/{qid}", None),
            ("POST", f"/api/rash-quiz/{ident}/answer", {"question_id": qid, "choice": "旧选项"}),
        )
        for method, path, body in requests:
            with self.subTest(method=method, path=path):
                response = self.client.request(method, path, **({"json": body} if body is not None else {}))
                self.assertEqual(response.status_code, 404, response.text)

    def test_routes_are_unregistered_and_always_404(self):
        self.assertFalse(any(getattr(route, "path", "").startswith("/api/rash-quiz") for route in main.app.routes))
        self.assert_retired()
        login = self.client.post("/api/session/login", json={"student_no": "RETIRED-001", "name": "练习移除测试"})
        self.assertEqual(login.status_code, 200)
        self.assert_retired()
        pre = self.client.post("/api/assessments/start", json={"phase": "pre"}).json()
        answers = {q["id"]: q["options"][0]["id"] for q in pre["questions"]}
        self.assertEqual(self.client.post(f"/api/assessments/{pre['id']}/submit", json={"answers": answers, "revision": 0}).status_code, 200)
        self.assert_retired()
        self.client.put("/api/admin/study/release", headers={"X-Admin-Password": "retired-test-only"}, json={"open": True})
        self.assertEqual(self.client.post("/api/assessments/start", json={"phase": "post"}).status_code, 200)
        self.assert_retired()
        self.client.post("/api/session/logout")
        self.assertEqual(self.client.post("/api/session/login", json={"student_no": "TEACHER-TEST", "name": "本地测试教师"}).status_code, 200)
        self.assert_retired()


if __name__ == "__main__":
    unittest.main()
