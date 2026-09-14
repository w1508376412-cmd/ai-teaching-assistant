"""Local-only acceptance server: temporary records, fake AI, known test password."""
import os
import tempfile

os.environ["ADMIN_PASSWORD"] = "local-study-test-only"
os.environ["TEACHER_STUDENT_NO"] = "TEACHER-TEST"
os.environ["TEACHER_NAME"] = "本地测试教师"
os.environ["STUDY_DATA_DIR"] = tempfile.mkdtemp(prefix="teaching-study-e2e-")
os.environ["STUDY_REQUIRE_VOLUME"] = "false"

import uvicorn
from src import main

main.complete = lambda *args, **kwargs: "结论：本地功能测试。请核对诊断与检查。"

if __name__ == "__main__":
    uvicorn.run(main.app, host="127.0.0.1", port=8766)
