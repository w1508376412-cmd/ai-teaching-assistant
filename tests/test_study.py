import csv
import io
import json
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from collections import Counter
from unittest.mock import patch

from fastapi.testclient import TestClient
from src import main, study
from src.assessment_bank import PAIRS, CASE_PAIRS, bank_with_sources
from src.rash_assessment_bank import RASH_PAIRS, bank as rash_bank

VERSION = "infectious-clinical-2026-09-v5"
LEGACY_VERSION = "infectious-clinical-2026-09-v3"
SECTION_TOTALS = {"basic": 60, "rash": 16, "case": 24}


class StudyTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.store = study.Store(self.folder.name + "/study.sqlite3")
        self.mock = patch.object(study, "get_store", return_value=self.store)
        self.store_mock = self.mock.start()
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
        private = self.private_paper(paper)
        return {q["id"]: q["correct"] for q in private["questions"]}

    def private_paper(self, paper):
        with self.store.db() as c:
            private = json.loads(c.execute("SELECT paper FROM attempts WHERE id=?", (paper["id"],)).fetchone()[0])
        return private

    def export_rows(self, kind="summary"):
        response = self.client.get(f"/api/admin/study/export?kind={kind}", headers=self.admin)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("no-store", response.headers["cache-control"])
        self.assertTrue(response.content.startswith(b"\xef\xbb\xbf"))
        return list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"))))

    def seed_legacy_pre(self, submitted=False, first_form="A"):
        """Persist the v3 wire/storage shape, deliberately without v4 metadata.

        Basic/case content is shared with v4; pin the historical 20*3 + 8*5
        scoring and omit section/image fields and result.sections. No private
        production database or student records are used.
        """
        self.login("LEGACY-001", "旧版学生")
        forms = {}
        for form in ("A", "B"):
            paper = self.store.make_paper(form)
            paper["version"] = LEGACY_VERSION
            paper["questions"] = [q for q in paper["questions"] if not q["id"].startswith("r")]
            for q in paper["questions"]:
                q["points"] = 5 if q["case_id"] else 3
                for key in list(q):
                    if key == "section" or key.startswith("image_"):
                        del q[key]
            self.assertEqual(len(paper["questions"]), 28)
            forms[form] = paper
        paper = forms[first_form]
        key = {q["id"]: q["correct"] for q in paper["questions"]}
        breakdown, items = {}, []
        for q in paper["questions"]:
            bucket = breakdown.setdefault(q["domain"], {"score": 0, "total": 0})
            bucket["score"] += q["points"]
            bucket["total"] += q["points"]
            items.append({"id": q["id"], "pair": q["pair"], "earned": q["points"], "points": q["points"]})
        result = {"score": 100, "total": 100, "breakdown": breakdown, "items": items}
        ident = "a" * 32
        now = time.time()
        with self.store.db(write=True) as c:
            user = c.execute("SELECT id FROM students WHERE student_no='LEGACY-001'").fetchone()[0]
            c.execute("UPDATE students SET first_form=? WHERE id=?", (first_form, user))
            c.execute("UPDATE settings SET value=? WHERE key='version'", (LEGACY_VERSION,))
            for form, frozen in forms.items():
                # Older deployments used unversioned paper_A / paper_B settings.
                c.execute("INSERT OR REPLACE INTO settings VALUES (?, ?)", (f"paper_{form}", study.encode(frozen)))
            c.execute("INSERT INTO attempts (id,student,phase,form,version,paper,answers,revision,started,submitted,result) "
                      "VALUES (?,?,'pre',?,?,?,?,0,?,?,?)",
                      (ident, user, first_form, LEGACY_VERSION, study.encode(paper),
                       study.encode(key if submitted else {"q01": key["q01"]}), now - 120,
                       now - 60 if submitted else None, study.encode(result) if submitted else None))
            c.execute("CREATE TABLE IF NOT EXISTS rash_quizzes (id TEXT PRIMARY KEY, student TEXT NOT NULL, "
                      "questions TEXT NOT NULL, answers TEXT NOT NULL DEFAULT '{}', started REAL NOT NULL)")
            c.execute("INSERT INTO rash_quizzes VALUES ('retired-record', ?, '[]', '{}', ?)", (user, now))
            before = dict(c.execute("SELECT * FROM attempts WHERE id=?", (ident,)).fetchone())
        self.store = study.Store(self.store.path)
        self.store_mock.return_value = self.store
        return before, forms

    def finish_pre(self):
        self.login()
        paper = self.start()
        response = self.client.post(f"/api/assessments/{paper['id']}/submit", json={"answers": self.answer_key(paper), "revision": 0})
        self.assertEqual(response.status_code, 200, response.text)
        return paper, response.json()

    def test_all_pairs_valid_and_source_mapped(self):
        bank_with_sources()
        self.assertEqual(Counter(p["difficulty"] for p in PAIRS), {"基础": 10, "应用": 8, "综合": 7})
        self.assertTrue(all(p["domain"] in {"临床识别", "检查与诊断", "病情评估", "治疗原则"} for p in PAIRS))
        for pair in PAIRS + CASE_PAIRS:
            for form in ("A", "B"):
                questions = pair[form].get("questions", [pair[form]])
                for q in questions:
                    self.assertEqual(len(q["choices"]), 4)
                    self.assertEqual(len(set(q["choices"])), 4)
                    self.assertIn(q["answer"], q["choices"])
                    self.assertNotRegex(q["stem"], r"^\d+\.")
                    for choice in q["choices"]:
                        self.assertNotRegex(choice, r"仅凭|一律|唯一依据|无需|不需|只检测|只查|即可出院|停止所有|任意单药")

    def test_parallel_forms_frozen_and_equal_blueprint(self):
        a, b = [self.store.make_paper(f) for f in ("A", "B")]
        self.assertEqual(study.VERSION, VERSION)
        for paper in (a, b):
            self.assertEqual(paper["version"], VERSION)
            self.assertEqual(len(paper["questions"]), 36)
            self.assertEqual(len(paper["cases"]), 2)
            self.assertEqual(sum(q["points"] for q in paper["questions"]), 100)
            self.assertEqual(Counter(q["section"] for q in paper["questions"]), {"basic": 20, "rash": 8, "case": 8})
            self.assertEqual([q["section"] for q in paper["questions"]], ["basic"] * 20 + ["rash"] * 8 + ["case"] * 8)
            self.assertEqual(Counter(q["difficulty"] for q in paper["questions"] if q["section"] == "basic"), {"基础": 8, "应用": 8, "综合": 4})
            for section, total in SECTION_TOTALS.items():
                group = [q for q in paper["questions"] if q["section"] == section]
                self.assertEqual(sum(q["points"] for q in group), total)
                self.assertEqual({q["points"] for q in group}, {2 if section == "rash" else 3})
            self.assertEqual(Counter(q["case_id"] for q in paper["questions"] if q["section"] == "case"), {"c1": 4, "c2": 4})
            rash = [q for q in paper["questions"] if q["section"] == "rash"]
            self.assertEqual([q["id"] for q in rash], [f"r{n:02}" for n in range(1, 9)])
            self.assertEqual(len({q["pair"] for q in rash}), 8)
            self.assertTrue(all(not q.get("image_file") for q in rash[:4]))
            self.assertTrue(all(q.get("image_file") and q.get("image_source") for q in rash[4:]))
            for q in rash:
                self.assertEqual(len({o["text"] for o in q["options"]}), 4)
                self.assertIn(q["correct"], {o["id"] for o in q["options"]})
                self.assertTrue(q["explanation"] and q["sources"] and q["point"])
                self.assertTrue(all(s["document"] for s in q["sources"]))
                self.assertTrue(any(s["url"].startswith("https://") for s in q["sources"]))
        for x, y in zip(a["questions"], b["questions"]):
            for key in ("id", "section", "pair", "difficulty", "point", "domain", "points"):
                self.assertEqual(x[key], y[key])
            self.assertNotEqual(x["stem"], y["stem"])
            if x.get("image_file"):
                self.assertNotEqual(x["image_file"], y["image_file"])
        for x, y in zip(a["cases"], b["cases"]):
            self.assertNotEqual(x["background"], y["background"])
        with patch.object(study, "PAIRS", []):
            reloaded = study.Store(self.store.path).make_paper("A")
        self.assertEqual([q["stem"] for q in a["questions"]], [q["stem"] for q in reloaded["questions"]])
        self.assertNotEqual(a["questions"][0]["options"], reloaded["questions"][0]["options"])

    def test_eight_rash_pairs_use_existing_atlas_images_and_record_sources(self):
        atlas = json.loads((study.ROOT / "assets/rash-atlas/atlas.json").read_text())
        diseases = {d["id"]: d for category in atlas["categories"] for d in category["diseases"]}
        bank = rash_bank()
        self.assertEqual(len(RASH_PAIRS), 8)
        self.assertEqual(len(bank), 8)
        self.assertEqual(len({p["atlas_id"] for p in bank}), 8)
        for n, pair in enumerate(bank):
            atlas_disease = diseases[pair["atlas_id"]]
            self.assertEqual(pair["disease"], atlas_disease["name"])
            self.assertTrue(pair["point"] and pair["difficulty"] and pair["domain"])
            self.assertTrue(any(s["url"].startswith("https://") for s in pair["sources"]))
            self.assertNotEqual(pair["A"]["stem"], pair["B"]["stem"])
            for form in ("A", "B"):
                q = pair[form]
                self.assertEqual(len(set(q["choices"])), 4)
                self.assertIn(q["answer"], q["choices"])
                self.assertTrue(q["explanation"])
                self.assertEqual(bool(q.get("image_file")), n >= 4)
                if q.get("image_file"):
                    self.assertNotIn("模拟病史", q["stem"])
                    source = next(i for i in atlas_disease["images"] if i["file"] == q["image_file"])
                    for key in ("provider", "source_label", "license", "caption", "links"):
                        self.assertEqual(q["image_source"][key], source.get(key, ""))
                    self.assertTrue(q["image_source"]["source_label"] and q["image_source"]["license"])
            if n >= 4:
                self.assertNotEqual(pair["A"]["image_file"], pair["B"]["image_file"])
            for variant in (pair["A"], pair["B"]):
                self.assertNotRegex(variant["stem"], r"模拟病史|用药|服药|服用|新药|药物")

    def test_bank_upgrade_keeps_matching_post_form_for_started_student(self):
        self.finish_pre()
        with self.store.db() as c:
            user = dict(c.execute("SELECT * FROM students WHERE student_no='2026001'").fetchone())
            pre = dict(c.execute("SELECT * FROM attempts WHERE student=? AND phase='pre'", (user["id"],)).fetchone())
        with patch.object(study, "VERSION", "clinical-test-next"):
            upgraded = study.Store(self.store.path)
            with upgraded.db(write=True) as c:
                c.execute("UPDATE settings SET value='true' WHERE key='post_open'")
            post = upgraded.start(user, "post")
        self.assertEqual(post["version"], pre["version"])
        self.assertNotEqual(post["form"], pre["form"])

    def test_pretest_gate_server_side_and_no_answer_leak(self):
        for path in ("/api/cases", "/api/knowledge", "/api/rash-atlas", "/assets/rash-atlas/atlas.json"):
            self.assertEqual(self.client.get(path).status_code, 401)
        self.login()
        for path in ("/api/cases", "/api/knowledge", "/api/rash-atlas", "/assets/rash-atlas/atlas.json"):
            self.assertEqual(self.client.get(path).status_code, 403)
        self.assertEqual(self.client.post("/api/chat/knowledge", json={"messages": [{"role": "user", "content": "测试"}]}).status_code, 403)
        p = self.start()
        for q in p["questions"]:
            for key in ("correct", "answer", "explanation", "pair", "sources", "disease", "image_file", "image_source", "source"):
                self.assertNotIn(key, q)
            self.assertIn(q["section"], SECTION_TOTALS)
        self.assertEqual(self.client.get("/api/assessment-results").json(), {"ready": False})
        with self.store.db() as c:
            row = dict(c.execute("SELECT * FROM attempts WHERE id=?", (p["id"],)).fetchone())
        self.assertNotIn("correct", study.public_attempt(row, review=True)["questions"][0])
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
        self.assertEqual(status["results"][0]["score"], 100)
        feedback = self.client.get("/api/assessment-results").json()
        self.assertTrue(feedback["ready"])
        self.assertEqual(len(feedback["attempts"]), 1)
        self.assertEqual(feedback["attempts"][0]["phase"], "pre")
        self.assertEqual(len(feedback["attempts"][0]["questions"]), 36)
        for q in feedback["attempts"][0]["questions"]:
            self.assertTrue(q["explanation"] and q["sources"] and q["point"] and q["disease"])
            self.assertEqual(q["correct"], feedback["attempts"][0]["answers"][q["id"]])
        self.assertIn("correct", self.client.get(f"/api/assessments/{pre['id']}").json()["questions"][0])
        self.assertEqual(self.client.get("/api/cases").status_code, 200)
        self.client.post("/api/session/logout")
        self.assertTrue(self.login()["pre_completed"])
        self.assertEqual(self.client.post("/api/assessments/start", json={"phase": "post"}).status_code, 403)
        self.assertEqual(self.client.put("/api/admin/study/release", json={"open": True}).status_code, 401)
        self.client.put("/api/admin/study/release", headers=self.admin, json={"open": True})
        post = self.start("post")
        self.assertNotEqual(post["form"], pre["form"])
        self.assertEqual(self.client.get("/api/cases").status_code, 403)
        self.assertEqual(self.client.get("/api/assessment-results").status_code, 403)
        self.assertNotIn("correct", self.client.get(f"/api/assessments/{pre['id']}").json()["questions"][0])
        self.assertNotIn("correct", self.client.get(f"/api/assessments/{post['id']}").json()["questions"][0])
        self.client.put("/api/admin/study/release", headers=self.admin, json={"open": False})
        key = self.answer_key(post)
        key["q01"] = next(o["id"] for o in post["questions"][0]["options"] if o["id"] != key["q01"])
        path = f"/api/assessments/{post['id']}"
        done = self.client.post(path + "/submit", json={"answers": key, "revision": 0})
        self.assertEqual(done.status_code, 200)
        self.assertEqual([r["score"] for r in done.json()["results"]], [100, 97])
        self.assertEqual(self.client.get("/api/cases").status_code, 200)
        reviewed = self.client.get("/api/assessment-results").json()
        self.assertEqual(len(reviewed["attempts"]), 2)
        self.assertTrue(all("correct" in q for a in reviewed["attempts"] for q in a["questions"]))
        self.assertEqual(self.client.post(path + "/submit", json={"answers": {}, "revision": 0}).json(), done.json())
        self.assertEqual(self.client.put(path + "/draft", json={"answers": {}, "revision": 1}).status_code, 409)
        summary = self.client.get("/api/admin/study", headers=self.admin).json()
        self.assertEqual(summary["mean_gain"], -3)
        items = self.client.get("/api/admin/study/export?kind=items", headers=self.admin)
        self.assertIn("no-store", items.headers["cache-control"])
        self.assertIn("配对知识点ID", items.text)
        self.assertIn("2026001", items.text)

    def test_active_learning_automatically_opens_posttest_and_manual_release_remains(self):
        self.finish_pre()
        initial = self.client.get("/api/session").json()
        self.assertFalse(initial["post_open"])
        self.assertEqual(initial["auto_post_seconds"], 1800)
        self.assertEqual(initial["auto_post_remaining"], 1800)

        # A first heartbeat establishes the active-use clock without crediting
        # time before the learning page was actually in the foreground.
        baseline = self.client.post("/api/study/heartbeat", json={"module": "knowledge", "seconds": 15})
        self.assertEqual(baseline.status_code, 200, baseline.text)
        self.assertEqual(baseline.json()["learning_seconds"], 0)
        with self.store.db(write=True) as c:
            user_id = c.execute("SELECT id FROM students WHERE student_no='2026001'").fetchone()[0]
            c.execute("UPDATE learning_time SET seconds=?,last_seen=? WHERE student=?",
                      (1789, time.time() - 20, user_id))

        opened = self.client.post("/api/study/heartbeat", json={"module": "cases", "seconds": 15})
        self.assertEqual(opened.status_code, 200, opened.text)
        self.assertTrue(opened.json()["post_open"])
        self.assertEqual(opened.json()["post_open_reason"], "time")
        self.assertGreaterEqual(opened.json()["learning_seconds"], 1800)

        # The teacher's global control remains available. Turning it off does
        # not revoke a student's independently earned 30-minute access.
        self.client.put("/api/admin/study/release", headers=self.admin, json={"open": True})
        self.assertEqual(self.client.get("/api/session").json()["post_open_reason"], "teacher")
        self.client.put("/api/admin/study/release", headers=self.admin, json={"open": False})
        self.assertEqual(self.client.get("/api/session").json()["post_open_reason"], "time")
        self.assertEqual(self.client.post("/api/assessments/start", json={"phase": "post"}).status_code, 200)

        exported = self.export_rows()
        self.assertIn("有效学习秒数", exported[0])
        self.assertEqual(exported[0]["后测开放方式"], "学习满30分钟")

    def test_learning_heartbeat_requires_completed_pretest_and_caps_payload(self):
        self.login()
        self.assertEqual(self.client.post("/api/study/heartbeat", json={"module": "knowledge", "seconds": 1}).status_code, 403)
        self.finish_pre()
        self.assertEqual(self.client.post("/api/study/heartbeat", json={"module": "knowledge", "seconds": 21}).status_code, 422)

    def test_identity_cookie_origin_and_teacher_authorization(self):
        response = self.client.post("/api/session/login", json={"student_no": "2026003", "name": "测试学生"})
        self.assertIn("HttpOnly", response.headers["set-cookie"])
        self.assertIn("SameSite=lax", response.headers["set-cookie"])
        self.assertIn("no-store", response.headers["cache-control"])
        self.assertEqual(self.client.post("/api/session/login", json={"student_no": "2026003", "name": "其他姓名"}).status_code, 409)
        self.assertEqual(self.client.post("/api/session/logout", headers={"Origin": "https://evil.example"}).status_code, 403)
        self.assertEqual(self.client.get("/api/admin/study", headers={"X-Admin-Password": "wrong"}).status_code, 401)

    def test_all_36_answers_autosave_resume_and_reject_over_limit(self):
        self.login()
        paper = self.start()
        key = self.answer_key(paper)
        self.assertEqual(len(key), 36)
        path = f"/api/assessments/{paper['id']}"
        response = self.client.put(path + "/draft", json={"answers": key, "revision": 0})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["revision"], 1)
        self.client.post("/api/session/logout")
        self.login()
        resumed = self.start()
        self.assertEqual(resumed["id"], paper["id"])
        self.assertEqual(resumed["answers"], key)
        self.assertEqual(resumed["revision"], 1)
        for method, endpoint in (("PUT", "/draft"), ("POST", "/submit")):
            response = self.client.request(method, path + endpoint, json={"answers": {**key, "extra": "invalid"}, "revision": 1})
            self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(self.client.get(path).json()["revision"], 1)
        self.assertEqual(self.client.get(path).json()["answers"], key)
        response = self.client.post(path + "/submit", json={"answers": key, "revision": 1})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["results"][0]["score"], 100)

    def test_missing_answer_in_each_section_does_not_submit_or_unlock(self):
        self.login()
        paper = self.start()
        key = self.answer_key(paper)
        path = f"/api/assessments/{paper['id']}"
        for missing in ("q20", "r04", "r08", "c2_4"):
            with self.subTest(missing=missing):
                response = self.client.post(path + "/submit", json={"answers": {k: v for k, v in key.items() if k != missing}, "revision": 0})
                self.assertEqual(response.status_code, 422, response.text)
                current = self.client.get(path).json()
                self.assertIsNone(current["submitted"])
                self.assertEqual(current["revision"], 0)
                self.assertEqual(current["answers"], {})
                self.assertEqual(self.client.get("/api/cases").status_code, 403)

    def test_weighted_section_scores_keep_knowledge_breakdown(self):
        self.login()
        paper = self.start()
        private = self.private_paper(paper)
        key = self.answer_key(paper)
        wrong = {"q01", "r01", "r05", "c1_1"}
        expected_breakdown = {}
        for q in private["questions"]:
            if q["id"] in wrong:
                key[q["id"]] = next(o["id"] for o in q["options"] if o["id"] != q["correct"])
            bucket = expected_breakdown.setdefault(q["domain"], {"score": 0, "total": 0})
            bucket["total"] += q["points"]
            bucket["score"] += 0 if q["id"] in wrong else q["points"]
        response = self.client.post(f"/api/assessments/{paper['id']}/submit", json={"answers": key, "revision": 0})
        self.assertEqual(response.status_code, 200, response.text)
        expected_scores = {"basic": 57, "rash": 12, "case": 21}
        reviewed = self.client.get("/api/assessment-results").json()["attempts"][0]
        for result in (response.json()["results"][0], self.client.get("/api/session").json()["results"][0], reviewed["result"]):
            self.assertEqual(result["score"], 90)
            self.assertEqual(set(result["sections"]), set(SECTION_TOTALS))
            self.assertEqual(result["breakdown"], expected_breakdown)
            for section, total in SECTION_TOTALS.items():
                self.assertEqual(result["sections"][section]["score"], expected_scores[section])
                self.assertEqual(result["sections"][section]["total"], total)
        self.assertEqual(sum(i["earned"] for i in reviewed["result"]["items"]), 90)
        self.assertEqual(sum(i["points"] for i in reviewed["result"]["items"]), 100)

    def test_zero_score_still_unlocks_learning(self):
        self.login()
        paper = self.start()
        answers = {q["id"]: next(o["id"] for o in q["options"] if o["id"] != q["correct"])
                   for q in self.private_paper(paper)["questions"]}
        response = self.client.post(f"/api/assessments/{paper['id']}/submit", json={"answers": answers, "revision": 0})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["pre_completed"])
        self.assertEqual(response.json()["results"][0]["score"], 0)
        for section, total in SECTION_TOTALS.items():
            score = response.json()["results"][0]["sections"][section]
            self.assertEqual((score["score"], score["total"]), (0, total))
        self.assertEqual(self.client.get("/api/cases").status_code, 200)

    def test_assessment_images_owner_access_review_and_posttest_lock(self):
        self.login()
        pre = self.start()
        private = self.private_paper(pre)
        private_by_id = {q["id"]: q for q in private["questions"]}
        pictures = [q for q in pre["questions"] if q.get("image_url")]
        self.assertEqual([q["id"] for q in pictures], ["r05", "r06", "r07", "r08"])
        image_bytes = {}
        for q in pictures:
            self.assertEqual(q["image_url"], f"/api/assessments/{pre['id']}/image/{q['id']}")
            self.assertTrue(q["image_alt"])
            self.assertNotIn(private_by_id[q["id"]]["disease"], q["image_alt"])
            response = self.client.get(q["image_url"])
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["content-type"], "image/webp")
            self.assertIn("no-store", response.headers["cache-control"])
            self.assertNotIn("content-disposition", response.headers)
            self.assertEqual(response.content[:4], b"RIFF")
            self.assertEqual(response.content[8:12], b"WEBP")
            image_bytes[q["id"]] = response.content
            self.assertEqual(response.content, (study.ROOT / "assets/rash-atlas/images" / private_by_id[q["id"]]["image_file"]).read_bytes())
        with TestClient(main.app) as other:
            self.assertEqual(other.get(pictures[0]["image_url"]).status_code, 401)
            self.login("2026002", client=other)
            for q in pictures:
                self.assertEqual(other.get(q["image_url"]).status_code, 404)
            self.assertEqual(other.get(pictures[0]["image_url"], headers=self.admin).status_code, 404)
        for qid in ("q01", "r01", "c1_1", "missing"):
            self.assertEqual(self.client.get(f"/api/assessments/{pre['id']}/image/{qid}").status_code, 404)
        self.assertEqual(self.client.get("/api/assessments/" + "0" * 32 + "/image/r05").status_code, 404)
        self.assertEqual(self.client.post(f"/api/assessments/{pre['id']}/submit", json={"answers": self.answer_key(pre), "revision": 0}).status_code, 200)
        review = self.client.get("/api/assessment-results").json()["attempts"][0]
        for q in review["questions"]:
            self.assertNotIn("image_file", q)
            if q.get("image_url"):
                self.assertEqual(q["image_source"], private_by_id[q["id"]]["image_source"])
                self.assertEqual(self.client.get(q["image_url"]).content, image_bytes[q["id"]])
        self.client.put("/api/admin/study/release", headers=self.admin, json={"open": True})
        post = self.start("post")
        pre_rash = {q["id"]: q for q in private["questions"] if q["section"] == "rash"}
        post_rash = {q["id"]: q for q in self.private_paper(post)["questions"] if q["section"] == "rash"}
        self.assertEqual(set(pre_rash), set(post_rash))
        for qid, q in pre_rash.items():
            self.assertEqual(q["pair"], post_rash[qid]["pair"])
            self.assertNotEqual(q["stem"], post_rash[qid]["stem"])
            if q.get("image_file"):
                self.assertNotEqual(q["image_file"], post_rash[qid]["image_file"])
        for q in pictures:
            self.assertEqual(self.client.get(q["image_url"]).status_code, 403)
        hidden_pre = self.client.get(f"/api/assessments/{pre['id']}").json()
        for q in hidden_pre["questions"]:
            for key in ("correct", "image_file", "image_source", "sources"):
                self.assertNotIn(key, q)
        for q in post["questions"]:
            if q.get("image_url"):
                response = self.client.get(q["image_url"])
                self.assertEqual(response.status_code, 200)
                self.assertNotEqual(response.content, image_bytes[q["id"]])
        self.assertEqual(self.client.post(f"/api/assessments/{post['id']}/submit", json={"answers": self.answer_key(post), "revision": 0}).status_code, 200)
        reviews = self.client.get("/api/assessment-results").json()["attempts"]
        self.assertEqual(sum(len(p["questions"]) for p in reviews), 72)
        for p in reviews:
            for q in p["questions"]:
                if q.get("image_url"):
                    self.assertTrue(q["image_source"])
                    self.assertEqual(self.client.get(q["image_url"]).status_code, 200)

    def test_teacher_preview_images_require_faculty_and_keep_neutral_urls(self):
        response = self.client.get("/api/admin/study/papers", headers=self.admin)
        self.assertEqual(response.status_code, 200, response.text)
        forms = response.json()["forms"]
        self.assertEqual({p["form"] for p in forms}, {"A", "B"})
        for paper in forms:
            self.assertEqual(len(paper["questions"]), 36)
            self.assertEqual(paper["version"], VERSION)
            images = [q for q in paper["questions"] if q.get("image_url")]
            self.assertEqual(len(images), 4)
            for q in paper["questions"]:
                self.assertIn("correct", q)
                self.assertNotIn("image_file", q)
            for q in images:
                url = f"/api/admin/study/papers/{paper['form']}/image/{q['id']}"
                self.assertEqual(q["image_url"], url)
                self.assertTrue(q["image_source"] and q["image_alt"])
                self.assertEqual(self.client.get(url).status_code, 401)
                self.assertEqual(self.client.get(url, headers={"X-Admin-Password": "wrong"}).status_code, 401)
                result = self.client.get(url, headers=self.admin)
                self.assertEqual(result.status_code, 200)
                self.assertEqual(result.headers["content-type"], "image/webp")
                self.assertIn("no-store", result.headers["cache-control"])
                self.assertNotIn("content-disposition", result.headers)
        self.login()
        self.assertEqual(self.client.get("/api/admin/study/papers/A/image/r05").status_code, 401)
        for form, qid in (("A", "q01"), ("B", "r01"), ("A", "missing")):
            self.assertEqual(self.client.get(f"/api/admin/study/papers/{form}/image/{qid}", headers=self.admin).status_code, 404)
        self.assertEqual(self.client.get("/api/admin/study/papers/C/image/r05", headers=self.admin).status_code, 422)
        with patch.dict("os.environ", {"TEACHER_STUDENT_NO": "TEACHER-TEST", "TEACHER_NAME": "本地测试教师"}):
            self.login("TEACHER-TEST", "本地测试教师")
            self.assertEqual(self.client.get("/api/admin/study/papers/B/image/r05").status_code, 200)

    def assert_export_sections(self, row, phase, scores, totals):
        for section, name in (("basic", "基础"), ("rash", "皮疹"), ("case", "案例")):
            for metric, expected in (("得分", scores.get(section, "")), ("满分", totals.get(section, ""))):
                columns = [key for key in row if phase in key and name in key and metric in key]
                self.assertEqual(len(columns), 1, f"Missing/ambiguous {phase}{name}{metric}: {list(row)}")
                self.assertEqual(row[columns[0]], str(expected))

    def test_summary_and_item_exports_include_sections_and_maxima(self):
        self.finish_pre()
        before = self.export_rows()[0]
        self.assert_export_sections(before, "前测", SECTION_TOTALS, SECTION_TOTALS)
        self.assert_export_sections(before, "后测", {}, {})
        self.client.put("/api/admin/study/release", headers=self.admin, json={"open": True})
        post = self.start("post")
        key = self.answer_key(post)
        for q in post["questions"]:
            if q["id"] in ("r05", "c1_1"):
                key[q["id"]] = next(o["id"] for o in q["options"] if o["id"] != key[q["id"]])
        self.assertEqual(self.client.post(f"/api/assessments/{post['id']}/submit", json={"answers": key, "revision": 0}).status_code, 200)
        row = self.export_rows()[0]
        self.assert_export_sections(row, "前测", SECTION_TOTALS, SECTION_TOTALS)
        self.assert_export_sections(row, "后测", {"basic": 60, "rash": 14, "case": 21}, SECTION_TOTALS)
        self.assertEqual(row["前测成绩"], "100")
        self.assertEqual(row["后测成绩"], "95")
        self.assertEqual(row["试卷版本"], VERSION)
        items = self.export_rows("items")
        self.assertEqual(len(items), 72)
        by_phase = {phase: {r["题号"]: r for r in items if r["阶段"] == phase} for phase in ("pre", "post")}
        for phase, rows in by_phase.items():
            self.assertEqual(len(rows), 36)
            self.assertEqual(sum(int(r["满分"]) for r in rows.values()), 100)
            self.assertEqual([rows[f"r{n:02}"]["满分"] for n in range(1, 9)], ["2"] * 8)
            self.assertEqual(rows["c1_1"]["满分"], "3")
            self.assertEqual(Counter(r["测验模块"] for r in rows.values()), {"基础知识": 20, "皮疹辨别": 8, "模拟案例": 8})
            self.assertEqual(Counter(r["题目形式"] for r in rows.values()), {"文字题": 32, "图片题": 4})
            for qid, item in rows.items():
                self.assertEqual(bool(item["图片出处"]), qid in {"r05", "r06", "r07", "r08"})
        for qid in by_phase["pre"]:
            self.assertEqual(by_phase["pre"][qid]["配对知识点ID"], by_phase["post"][qid]["配对知识点ID"])
        self.assertEqual(by_phase["post"]["r05"]["得分"], "0")
        self.assertEqual(by_phase["post"]["c1_1"]["得分"], "0")

    def test_legacy_in_progress_28_questions_resume_and_pair_after_upgrade(self):
        before, forms = self.seed_legacy_pre(first_form="B")
        with self.store.db() as c:
            self.assertEqual(dict(c.execute("SELECT * FROM attempts WHERE id=?", (before["id"],)).fetchone()), before)
            self.assertEqual(c.execute("SELECT COUNT(*) FROM rash_quizzes WHERE id='retired-record'").fetchone()[0], 1)
        self.assertEqual(self.store.settings()["version"], VERSION)
        for form in ("A", "B"):
            self.assertEqual(json.loads(self.store.settings()[self.store.paper_key(LEGACY_VERSION, form)]), forms[form])
        pre = self.start()
        self.assertEqual(pre["id"], before["id"])
        self.assertEqual(pre["version"], LEGACY_VERSION)
        self.assertEqual(len(pre["questions"]), 28)
        self.assertEqual(pre["answers"], json.loads(before["answers"]))
        self.assertEqual(Counter(q["section"] for q in pre["questions"]), {"basic": 20, "case": 8})
        key = self.answer_key(pre)
        path = f"/api/assessments/{pre['id']}"
        self.assertEqual(self.client.put(path + "/draft", json={"answers": key, "revision": 0}).status_code, 200)
        response = self.client.post(path + "/submit", json={"answers": key, "revision": 1})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["results"][0]["score"], 100)
        self.client.put("/api/admin/study/release", headers=self.admin, json={"open": True})
        post = self.start("post")
        self.assertEqual(post["version"], LEGACY_VERSION)
        self.assertEqual(post["form"], "A")
        self.assertEqual(len(post["questions"]), 28)
        self.assertEqual(sum(q["points"] for q in post["questions"]), 100)
        self.assertEqual([q["pair"] for q in self.private_paper(pre)["questions"]], [q["pair"] for q in self.private_paper(post)["questions"]])
        self.assertFalse(any(q.get("image_url") for q in post["questions"]))
        self.assertEqual(self.client.post(f"/api/assessments/{post['id']}/submit", json={"answers": self.answer_key(post), "revision": 0}).status_code, 200)
        reviews = self.client.get("/api/assessment-results").json()["attempts"]
        self.assertEqual(sum(len(p["questions"]) for p in reviews), 56)
        for p in reviews:
            self.assertEqual(p["result"]["sections"]["case"]["total"], 40)
            self.assertNotIn("rash", p["result"]["sections"])
        self.login("NEW-001", "新版学生")
        self.assertEqual(self.start()["version"], VERSION)

    def test_legacy_submitted_results_derive_sections_without_rewriting_history(self):
        before, _ = self.seed_legacy_pre(submitted=True)
        result = self.client.get("/api/session").json()["results"][0]
        expected = {"basic": {"score": 60, "total": 60}, "case": {"score": 40, "total": 40}}
        for section, values in expected.items():
            for key, value in values.items():
                self.assertEqual(result["sections"][section][key], value)
        self.assertNotIn("rash", result["sections"])
        self.assertEqual(result["breakdown"], json.loads(before["result"])["breakdown"])
        row = self.export_rows()[0]
        self.assert_export_sections(row, "前测", {"basic": 60, "case": 40}, {"basic": 60, "case": 40})
        self.assert_export_sections(row, "后测", {}, {})
        self.assertEqual(row["试卷版本"], LEGACY_VERSION)
        items = self.export_rows("items")
        self.assertEqual(len(items), 28)
        self.assertEqual(Counter(r["满分"] for r in items), {"3": 20, "5": 8})
        self.assertEqual(Counter(r["测验模块"] for r in items), {"基础知识": 20, "模拟案例": 8})
        self.assertTrue(all(r["题目形式"] == "文字题" and not r["图片出处"] for r in items))
        reviewed = self.client.get("/api/assessment-results").json()["attempts"][0]
        self.assertEqual(len(reviewed["questions"]), 28)
        self.assertEqual(reviewed["result"]["sections"], result["sections"])
        with self.store.db() as c:
            self.assertEqual(dict(c.execute("SELECT * FROM attempts WHERE id=?", (before["id"],)).fetchone()), before)

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
