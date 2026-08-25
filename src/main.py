import io
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Literal

import docx
import PyPDF2
from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from openai import OpenAI
from pydantic import BaseModel, Field
from spire.doc import Document


ROOT_DIR = Path(__file__).resolve().parent.parent
KNOWLEDGE_DIR = ROOT_DIR / "knowledge_base"
CASES_DIR = ROOT_DIR / "cases"
ASSETS_DIR = ROOT_DIR / "assets"
STATIC_DIR = Path(__file__).resolve().parent / "static"

for directory in (KNOWLEDGE_DIR, CASES_DIR):
    directory.mkdir(parents=True, exist_ok=True)

API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com")
MODEL_NAME = os.getenv("MODEL_NAME", "deepseek-v4-flash")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")

app = FastAPI(
    title="口岸卫生检疫教学工作台",
    description="知识库问答、现场案例推演与教师内容管理",
    version="2.0.0",
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=12000)


class KnowledgeChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=30)


class DecisionRequest(BaseModel):
    possible_diseases: list[str] = Field(default_factory=list)
    measures: list[str] = Field(default_factory=list)
    treatments: list[str] = Field(default_factory=list)


class StageCoachRequest(BaseModel):
    stage_index: int = Field(ge=0)
    messages: list[ChatMessage] = Field(min_length=1, max_length=30)


def get_client() -> OpenAI:
    if not API_KEY:
        raise HTTPException(
            status_code=503,
            detail="AI 服务尚未配置，请在 Zeabur 中设置 DEEPSEEK_API_KEY。",
        )
    return OpenAI(api_key=API_KEY, base_url=BASE_URL)


def require_admin(x_admin_password: str | None = Header(default=None)) -> None:
    if not ADMIN_PASSWORD:
        raise HTTPException(
            status_code=503,
            detail="教师管理尚未启用，请先设置 ADMIN_PASSWORD。",
        )
    if x_admin_password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="教师管理密码不正确。")


def load_knowledge() -> dict[str, str]:
    documents: dict[str, str] = {}
    for file in sorted(KNOWLEDGE_DIR.glob("*.md")):
        documents[file.stem] = file.read_text(encoding="utf-8")
    return documents


def load_cases() -> list[dict]:
    cases: list[dict] = []
    for file in sorted(CASES_DIR.glob("*.json")):
        try:
            data = json.loads(file.read_text(encoding="utf-8"))
            data["_filename"] = file.name
            data.setdefault("id", file.stem)
            data.setdefault("title", f"未命名案例（{file.stem}）")
            cases.append(data)
        except (OSError, json.JSONDecodeError) as exc:
            cases.append(
                {
                    "_filename": file.name,
                    "id": file.stem,
                    "title": f"损坏的案例（{file.name}）",
                    "error": str(exc),
                }
            )
    return cases


def find_case(case_id: str) -> dict:
    for case in load_cases():
        if case.get("id") == case_id:
            if case.get("error"):
                raise HTTPException(status_code=422, detail=case["error"])
            return case
    raise HTTPException(status_code=404, detail="未找到该案例。")


def public_case(case: dict) -> dict:
    hidden = {"correct_answers", "reference_sop", "_filename", "error"}
    return {key: value for key, value in case.items() if key not in hidden}


def safe_stem(filename: str) -> str:
    stem = Path(filename).stem.strip()
    cleaned = re.sub(r"[^\w\-（）()]+", "_", stem, flags=re.UNICODE).strip("_")
    if not cleaned:
        raise HTTPException(status_code=400, detail="文件名无效。")
    return cleaned[:100]


def extract_document(filename: str, content: bytes) -> str:
    extension = Path(filename).suffix.lower()
    try:
        if extension == ".md":
            return content.decode("utf-8")
        if extension == ".docx":
            document = docx.Document(io.BytesIO(content))
            return "\n".join(paragraph.text for paragraph in document.paragraphs)
        if extension == ".pdf":
            reader = PyPDF2.PdfReader(io.BytesIO(content))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        if extension == ".doc":
            temp_path = ""
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".doc") as temp_file:
                    temp_file.write(content)
                    temp_path = temp_file.name
                document = Document()
                document.LoadFromFile(temp_path)
                return document.GetText()
            finally:
                if temp_path and os.path.exists(temp_path):
                    os.remove(temp_path)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"文档解析失败：{exc}") from exc
    raise HTTPException(status_code=415, detail="仅支持 .md、.docx、.doc 和 .pdf 文件。")


def complete(messages: list[dict]) -> str:
    try:
        response = get_client().chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
        )
        return response.choices[0].message.content or ""
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI 服务调用失败：{exc}") from exc


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "framework": "fastapi"}


@app.get("/api/config")
def config() -> dict:
    return {
        "ai_configured": bool(API_KEY),
        "admin_configured": bool(ADMIN_PASSWORD),
        "model": MODEL_NAME,
        "knowledge_count": len(load_knowledge()),
        "case_count": len(load_cases()),
    }


@app.get("/api/knowledge")
def knowledge_index() -> dict:
    documents = load_knowledge()
    return {
        "documents": [
            {"name": name, "characters": len(content)}
            for name, content in documents.items()
        ]
    }


@app.post("/api/chat/knowledge")
def knowledge_chat(request: KnowledgeChatRequest) -> dict:
    context = "\n\n".join(load_knowledge().values())
    system_prompt = f"""你是一个专业的口岸卫生检疫与现场流行病学教学助手。
请严格优先根据下方知识库回答学员问题；知识库没有依据时，明确说明依据不足。回答应直接、专业、便于教学，不要在结尾添加扩展建议。

图片规则：只有当学员专门询问猴痘皮疹形态、特点或演变时，回答中才可包含标记 [显示猴痘皮疹图]。普通定义或症状列表不得包含该标记。

知识库内容：
{context}"""
    answer = complete(
        [
            {"role": "system", "content": system_prompt},
            *[message.model_dump() for message in request.messages],
        ]
    )
    return {
        "answer": answer.replace("[显示猴痘皮疹图]", "").strip(),
        "show_mpox_image": "[显示猴痘皮疹图]" in answer,
    }


@app.get("/api/cases")
def cases_index() -> dict:
    return {"cases": [public_case(case) for case in load_cases() if not case.get("error")]}


@app.post("/api/cases/{case_id}/evaluate")
def evaluate_case(case_id: str, request: DecisionRequest) -> dict:
    case = find_case(case_id)
    if case.get("format") != "interactive_v2":
        raise HTTPException(status_code=400, detail="该案例不是决策判断格式。")

    correct = case.get("correct_answers", {})
    user_answer = f"""学员选择：
- 可能疾病：{', '.join(request.possible_diseases) or '未选择'}
- 处置措施：{', '.join(request.measures) or '未选择'}
- 诊断方法：{', '.join(request.treatments) or '未选择'}"""
    system_prompt = f"""你是专业的现场流行病学案例导师。
当前案例：{case.get('title')}
标准答案：
- 疾病：{', '.join(correct.get('possible_diseases', []))}
- 措施：{', '.join(correct.get('measures', []))}
- 诊断：{', '.join(correct.get('treatments', []))}
参考 SOP：{case.get('reference_sop', '未提供')}

评价学员选择是否正确、完整，先给结论，再指出做对、遗漏或错误之处，最后给出基于 SOP 的专业解析。内容控制在 500 字以内。"""
    feedback = complete(
        [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": f"病例背景：{case.get('background', '')}\n{user_answer}",
            },
        ]
    )
    return {"feedback": feedback, "reference_sop": case.get("reference_sop", "")}


@app.post("/api/cases/{case_id}/coach")
def coach_stage(case_id: str, request: StageCoachRequest) -> dict:
    case = find_case(case_id)
    stages = case.get("stages", [])
    if request.stage_index >= len(stages):
        raise HTTPException(status_code=400, detail="案例阶段不存在。")
    stage = stages[request.stage_index]
    context = "\n\n".join(load_knowledge().values())
    system_prompt = f"""你是专业的口岸卫生检疫案例教学引导员。
案例：《{case.get('title', '未知')}》
当前阶段：第 {stage.get('step', request.stage_index + 1)} 步 — {stage.get('title', '')}
任务：{stage.get('task', '')}
引导问题：{', '.join(stage.get('guiding_questions', []))}

参考规范：
{context}

评价准则：正确时给予具体肯定并引向下一步；有疏漏时指出疏漏并通过追问引导；不要直接泄露完整答案；保持专业、严谨。"""
    answer = complete(
        [
            {"role": "system", "content": system_prompt},
            *[message.model_dump() for message in request.messages],
        ]
    )
    return {"answer": answer}


@app.get("/api/admin/content")
def admin_content(_: None = Depends(require_admin)) -> dict:
    documents = load_knowledge()
    return {
        "documents": [
            {"name": name, "characters": len(content)}
            for name, content in documents.items()
        ],
        "cases": [
            {
                "id": case.get("id"),
                "title": case.get("title"),
                "filename": case.get("_filename"),
                "error": case.get("error"),
            }
            for case in load_cases()
        ],
    }


@app.post("/api/admin/knowledge")
async def upload_knowledge(
    file: UploadFile = File(...), _: None = Depends(require_admin)
) -> dict:
    content = extract_document(file.filename or "", await file.read())
    name = safe_stem(file.filename or "")
    (KNOWLEDGE_DIR / f"{name}.md").write_text(content, encoding="utf-8")
    return {"message": f"文档《{name}》已加入知识库。", "name": name}


@app.delete("/api/admin/knowledge/{name}")
def delete_knowledge(name: str, _: None = Depends(require_admin)) -> dict:
    path = KNOWLEDGE_DIR / f"{safe_stem(name)}.md"
    if not path.exists():
        raise HTTPException(status_code=404, detail="文档不存在。")
    path.unlink()
    return {"message": f"文档《{path.stem}》已移除。"}


@app.delete("/api/admin/cases/{filename}")
def delete_case(filename: str, _: None = Depends(require_admin)) -> dict:
    candidate = Path(filename).name
    if not candidate.endswith(".json"):
        raise HTTPException(status_code=400, detail="案例文件名无效。")
    path = CASES_DIR / candidate
    if not path.exists():
        raise HTTPException(status_code=404, detail="案例不存在。")
    path.unlink()
    return {"message": f"案例《{path.stem}》已移除。"}


@app.post("/api/admin/cases/generate")
async def generate_case(
    file: UploadFile = File(...), _: None = Depends(require_admin)
) -> dict:
    filename = file.filename or ""
    content = extract_document(filename, await file.read())
    document_name = safe_stem(filename)
    prompt = f"""你是专业的海关卫生检疫业务教学设计师。根据下方文档设计一个交互式决策判断案例。

参考文档：
{content[:8000]}

要求：
1. 场景限定为口岸卫生检疫，海关人员不得开具处方或实施临床治疗。
2. 背景与病例信息不得直接出现目标传染病名称，学员应根据表现和流行病学史推断。
3. 处置措施聚焦流调、采样、防护、通报与闭环转运；诊断方法聚焦实验室检测。
4. 只返回合法 JSON，不要使用 Markdown 代码块。

JSON 结构：
{{
  "id": "gen_{document_name[:24]}",
  "format": "interactive_v2",
  "title": "案例标题",
  "background": "客观场景背景",
  "patient_info": {{"年龄":"", "性别":"", "旅行史":"", "症状":[], "发病时间":"", "接触史":""}},
  "options": {{"possible_diseases":[], "measures":[], "treatments":[]}},
  "correct_answers": {{"possible_diseases":[], "measures":[], "treatments":[]}},
  "reference_sop": "引用依据"
}}"""
    raw = complete([{"role": "system", "content": prompt}]).strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    try:
        case = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail="AI 返回的案例不是合法 JSON。") from exc

    case_id = safe_stem(str(case.get("id") or f"gen_{document_name}"))
    case["id"] = case_id
    destination = CASES_DIR / f"{case_id}.json"
    destination.write_text(json.dumps(case, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"message": f"案例《{case.get('title', case_id)}》已生成。", "case": public_case(case)}
