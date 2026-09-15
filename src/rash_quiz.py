"""Source-mapped image practice; diagnoses and captions are revealed after answering."""
import json
import secrets
import time
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from src.study import ROOT, encode, get_store, require_learning, same_origin

router = APIRouter(prefix="/api/rash-quiz", dependencies=[Depends(require_learning)])
IMAGE_DIR = ROOT / "assets/rash-atlas/images"

# Histories are teaching vignettes, not claims about the photographed patients.
ITEMS = [
    dict(disease="measles", file="measles_16469.webp",
         context="模拟病史：患者高热4天，伴咳嗽、流涕和结膜充血，随后出现图示皮损。近期未服用新药。",
         choices=["麻疹", "风疹", "猩红热", "发疹型药疹"],
         explanation="图中面颈部和上胸部可见红色斑丘疹，部分融合。结合出疹前高热、咳嗽、流涕和结膜充血，最支持麻疹。风疹全身症状通常较轻；猩红热以细密砂纸样疹及咽炎为特征；药疹需要相应用药时序。临床疑似麻疹应送检核酸及IgM获得实验室证据。"),
    dict(disease="rubella", file="rubella_22142.webp",
         context="模拟病史：患者低热1天后出疹，耳后及枕后淋巴结肿大，咳嗽和流涕不明显。近期未服用新药。",
         choices=["风疹", "麻疹", "猩红热", "发疹型药疹"],
         explanation="图中面部和躯干为红色斑疹、斑丘疹。外观可与其他病毒疹重叠；轻度发热和耳后、枕后淋巴结肿大使风疹更符合。麻疹常有明显高热和卡他症状，猩红热常伴咽痛及细密砂纸样疹；缺少相应新用药史不支持药疹。风疹需结合实验室检查确认。"),
    dict(disease="varicella", file="varicella_book00_p93.webp",
         context="模拟病史：患者发热后出现瘙痒性皮疹，躯干较多，过去两天仍有新皮损出现。",
         choices=["水痘", "猴痘", "带状疱疹", "脓疱疮"],
         explanation="图示躯干散在丘疹、疱疹及结痂，结合分批出现、瘙痒和躯干为主的分布，符合水痘。带状疱疹多沿单侧皮节，猴痘皮损通常更深在且可伴明显淋巴结肿大，脓疱疮更突出浅表糜烂和蜜黄色痂。"),
    dict(disease="zoster", file="zoster_book00_p93.webp",
         context="模拟病史：图A患者左侧躯干先出现灼痛，2天后出现图示皮损。图B展示同病种的另一受累部位。请以图A判断。",
         choices=["带状疱疹", "水痘", "接触性皮炎", "单纯疱疹"],
         explanation="图A成簇疱疹位于红斑基础上，沿左侧躯干呈带状分布；先疼痛后出疹支持带状疱疹。水痘常全身分批出疹，接触性皮炎符合接触范围且瘙痒更常见，单纯疱疹常在口唇或生殖器局部复发。图B眼周受累需评估眼部并发症。"),
    dict(disease="hfmd", file="hfmd_pmc04_PMC10699830.webp",
         context="模拟病史：成人低热、咽痛后手掌出现图示皮损，伴口腔疼痛性糜烂，近期照护过有类似口腔和手足皮损的幼儿。",
         choices=["手足口病", "二期梅毒", "汗疱疹", "多形红斑"],
         explanation="图示掌部多发红色丘疹、丘疱疹，结合急性发热、疼痛性口腔损害及相似接触史，支持成人手足口病。二期梅毒掌跖疹常不痛不痒并需血清学评估；汗疱疹多为瘙痒性深在小疱；多形红斑以典型靶形损害为识别重点。"),
    dict(disease="mpox", file="mpox_12779.webp",
         context="模拟病史：患者发热伴淋巴结肿大，躯干和上肢出现图示皮损，触痛明显。",
         choices=["猴痘", "水痘", "脓疱疮", "播散性带状疱疹"],
         explanation="图中皮损边界较清楚，部分呈中央凹陷或结痂的疱疹、脓疱。深在皮损、疼痛和淋巴结肿大共同支持猴痘。水痘常以瘙痒和多期皮损并存为特点，脓疱疮多为浅表脓疱和蜜黄色痂，播散性带状疱疹常有起始皮节性损害及免疫抑制背景。需规范采集皮损材料进行核酸检测。"),
    dict(disease="scarlet", file="scarlet_5163.webp",
         context="模拟病史：患者发热、咽痛2天，扁桃体充血，继而出现皮疹，触之粗糙。近期未服用新药。",
         choices=["猩红热", "麻疹", "风疹", "发疹型药疹"],
         explanation="图示弥漫充血基础上的密集细小丘疹，结合粗糙触感、发热和咽炎，支持猩红热。麻疹和风疹以斑丘疹为主，分别更常伴卡他症状或耳后淋巴结肿大；药疹需要相应药物暴露。可通过咽拭子A群链球菌检测协助确认。"),
    dict(disease="syphilis", file="syphilis_book00_p235.webp",
         context="模拟病史：图中为同病种的不同皮肤黏膜表现。掌部皮损患者同时有无明显瘙痒的躯干疹，数周前曾出现自行愈合的无痛性生殖器溃疡。",
         choices=["二期梅毒", "手足口病", "玫瑰糠疹", "多形红斑"],
         explanation="图中可见躯干斑丘疹、掌部带鳞屑的斑丘疹及肛周扁平湿疣。掌跖受累和既往无痛溃疡的时序支持二期梅毒；手足口病常急性起病并有疼痛性口腔损害，玫瑰糠疹多沿躯干皮纹分布，多形红斑以靶形损害为特征。应结合梅毒螺旋体及非梅毒螺旋体血清学试验。"),
]


@lru_cache(maxsize=1)
def bank():
    atlas = json.loads((ROOT / "assets/rash-atlas/atlas.json").read_text())
    diseases = {d["id"]: d for c in atlas["categories"] for d in c["diseases"]}
    result = []
    for item in ITEMS:
        disease = diseases[item["disease"]]
        image = next(i for i in disease["images"] if i["file"] == item["file"])
        if not (IMAGE_DIR / item["file"]).is_file():
            raise ValueError("Missing quiz image")
        result.append({**item, "answer": disease["name"], "image": image})
    return result


def owned(conn, user, ident):
    row = conn.execute("SELECT * FROM rash_quizzes WHERE id=? AND student=?", (ident, user["id"])).fetchone()
    if not row:
        raise HTTPException(404, "本轮小测验不存在，请重新开始。")
    return dict(row)


def snapshot(row, index=None):
    questions, answers = json.loads(row["questions"]), json.loads(row["answers"])
    done = len(answers)
    index = done if index is None else index
    if index > done or index > len(questions):
        raise HTTPException(409, "请按顺序完成本轮题目。")
    history = []
    for q in questions:
        if q["id"] in answers:
            history.append({"id": q["id"], "answer": q["answer"], "selected": answers[q["id"]],
                            "correct": answers[q["id"]] == q["answer"], "explanation": q["explanation"]})
    current = None
    if index < len(questions):
        q = questions[index]
        current = {"id": q["id"], "context": q["context"], "options": q["options"],
                   "image_url": f"/api/rash-quiz/{row['id']}/image/{q['id']}",
                   "alt": "看图辨病教学图片"}
        if q["id"] in answers:
            current.update(answer=q["answer"], selected=answers[q["id"]],
                           correct=answers[q["id"]] == q["answer"], explanation=q["explanation"],
                           source={k: q["image"].get(k, "") for k in ("source_label", "provider", "license", "caption", "links")})
    return {"id": row["id"], "index": index, "total": len(questions), "answered": done,
            "correct_count": sum(h["correct"] for h in history), "question": current,
            "completed": done == len(questions), "history": history}


@router.post("", dependencies=[Depends(same_origin)])
def start(user=Depends(require_learning)):
    rng = secrets.SystemRandom()
    questions = [{**q, "id": secrets.token_hex(8), "options": rng.sample(q["choices"], 4)} for q in rng.sample(bank(), 5)]
    ident = secrets.token_hex(16)
    store = get_store()
    with store.db(write=True) as c:
        c.execute("INSERT INTO rash_quizzes (id,student,questions,started) VALUES (?,?,?,?)",
                  (ident, user["id"], encode(questions), time.time()))
        return snapshot(owned(c, user, ident))


@router.get("/{ident}")
def resume(ident: str, index: int | None = Query(default=None, ge=0, le=5), user=Depends(require_learning)):
    with get_store().db() as c:
        return snapshot(owned(c, user, ident), index)


class Answer(BaseModel):
    question_id: str = Field(max_length=32)
    choice: str = Field(min_length=1, max_length=80)


@router.post("/{ident}/answer", dependencies=[Depends(same_origin)])
def answer(ident: str, body: Answer, user=Depends(require_learning)):
    with get_store().db(write=True) as c:
        row = owned(c, user, ident)
        questions, answers = json.loads(row["questions"]), json.loads(row["answers"])
        index = next((n for n, q in enumerate(questions) if q["id"] == body.question_id), None)
        if index is None or body.choice not in questions[index]["options"]:
            raise HTTPException(422, "请选择当前图片对应的一个疾病选项。")
        if body.question_id in answers:
            if answers[body.question_id] != body.choice:
                raise HTTPException(409, "本题已作答，请继续下一题。")
            return snapshot(row, index)
        if index != len(answers):
            raise HTTPException(409, "请先完成当前题目。")
        answers[body.question_id] = body.choice
        row["answers"] = encode(answers)
        c.execute("UPDATE rash_quizzes SET answers=? WHERE id=?", (row["answers"], ident))
        return snapshot(row, index)


@router.get("/{ident}/image/{question_id}")
def quiz_image(ident: str, question_id: str, user=Depends(require_learning)):
    with get_store().db() as c:
        row = owned(c, user, ident)
    questions, answers = json.loads(row["questions"]), json.loads(row["answers"])
    q = next((q for n, q in enumerate(questions) if q["id"] == question_id and n <= len(answers)), None)
    if not q:
        raise HTTPException(404, "图片不存在。")
    return FileResponse(IMAGE_DIR / q["file"], media_type="image/webp")
