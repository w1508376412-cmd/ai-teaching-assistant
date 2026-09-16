"""Eight parallel rash-recognition items, authored from the existing atlas.

The first four pairs are text-only; the last four use distinct atlas images
in A and B. Histories are teaching simulations, not photographed-patient data.
Image filenames and diagnostic captions stay in the frozen server-side paper.
"""
import json
from pathlib import Path

from src.assessment_bank import item

ROOT = Path(__file__).resolve().parents[1]
IMAGE_DIR = ROOT / "assets/rash-atlas/images"


def variant(stem, correct, distractors, explanation, image_file=None):
    return {**item(stem, correct, *distractors), "explanation": explanation,
            **({"image_file": image_file} if image_file else {})}


RASH_PAIRS = [
    dict(id="rash-varicella", atlas_id="varicella", difficulty="基础",
         point="分批出疹与多期皮损并存的识别",
         reference="https://www.cdc.gov/chickenpox/hcp/clinical-signs/index.html",
         A=variant("患者发热后躯干部出现瘙痒性皮疹，查体同时见红色丘疹、薄壁水疱和结痂，四肢远端皮损较少。最符合哪种疾病？",
                   "水痘", ["猴痘", "播散性带状疱疹", "大疱性脓疱疮"],
                   "躯干为主的向心性分布、分批出现及不同阶段皮损并存支持水痘。猴痘常见较深在的皮损并可伴淋巴结肿大；播散性带状疱疹需注意起始的皮节分布及免疫抑制背景；大疱性脓疱疮主要为浅表松弛性大疱、糜烂与痂皮。"),
         B=variant("患者全身皮疹2天，头皮和胸背部较多，瘙痒明显；今日仍出现新水疱，原有皮损部分已结痂。最可能的诊断是？",
                   "水痘", ["播散性带状疱疹", "大疱性脓疱疮", "猴痘"],
                   "头皮、躯干较多，持续有新疱出现且旧疹已结痂，符合水痘的分批出疹和多期皮损共存。其他选项虽可有疱疹，但需分别结合皮节性起病、浅表大疱或深在疼痛性皮损等特征鉴别。")),
    dict(id="rash-zoster", atlas_id="zoster", difficulty="基础",
         point="单侧皮节分布与神经痛的识别",
         reference="https://www.cdc.gov/shingles/hcp/clinical-signs/index.html",
         A=variant("56岁患者右胸部灼痛3天后出疹，红斑上见成簇水疱，从背部延伸至同侧胸前，沿肋间分布，未越过中线。最可能的诊断是？",
                   "带状疱疹", ["接触性皮炎", "单纯疱疹", "水痘"],
                   "先有局部神经痛，再出现沿单侧皮节排列的成簇水疱，是带状疱疹的典型组合。接触性皮炎符合接触部位且以瘙痒更常见；单纯疱疹常在局部复发；水痘通常呈全身分批出疹。"),
         B=variant("61岁患者左腰部触痛，次日出现簇集性小水疱，沿左侧腰腹形成带状分布，对侧皮肤正常。哪项诊断最能解释皮损分布与疼痛的关系？",
                   "带状疱疹", ["单纯疱疹", "水痘", "接触性皮炎"],
                   "单侧腰腹沿皮节的带状疱疹与出疹前疼痛相吻合，支持带状疱疹。接触性皮炎由接触范围决定分布，单纯疱疹常为局限复发性皮损，水痘的皮损不局限于单一皮节。")),
    dict(id="rash-scarlet", atlas_id="scarlet", difficulty="应用",
         point="砂纸样疹伴咽炎的鉴别",
         reference="https://www.cdc.gov/group-a-strep/hcp/clinical-guidance/scarlet-fever.html",
         A=variant("患者发热、咽痛2天，胸腹部出现弥漫细小红色丘疹，触之粗糙，腋窝与肘窝皮疹加深，舌乳头突出。近期未使用新药。最可能的诊断是？",
                   "猩红热", ["麻疹", "风疹", "发疹型药疹"],
                   "细密砂纸样皮疹、皮肤皱褶处加深及咽炎、草莓舌共同支持猩红热，可通过咽拭子A群链球菌检测确认。麻疹更常伴明显卡他症状，风疹常伴耳后或枕后淋巴结肿大；药疹需结合用药与出疹时序。"),
         B=variant("青年患者急性咽痛、高热后出现躯干细密皮疹，按压可褪色、触感如砂纸，伴口周苍白、扁桃体充血。发病前后未用药。首先考虑哪种疾病？",
                   "猩红热", ["发疹型药疹", "风疹", "麻疹"],
                   "急性咽炎、砂纸样皮疹及口周苍白相结合，最支持猩红热。病毒性斑丘疹与药疹外观可重叠，需结合卡他症状、淋巴结分布和用药史鉴别，诊断需A群链球菌检测支持。")),
    dict(id="rash-syphilis", atlas_id="syphilis", difficulty="应用",
         point="掌跖斑丘疹与二期梅毒的识别",
         reference="https://www.cdc.gov/syphilis/about/index.html",
         A=variant("成人躯干、手掌及足底出现铜红色斑丘疹，部分边缘有薄鳞屑，瘙痒不明显，伴全身淋巴结肿大。两个月前曾有自行愈合的无痛性生殖器溃疡。最可能的诊断是？",
                   "二期梅毒", ["玫瑰糠疹", "手足口病", "多形红斑"],
                   "掌跖受累、无明显瘙痒的泛发斑丘疹及既往无痛性溃疡的病程支持二期梅毒。玫瑰糠疹常沿躯干皮纹分布，手足口病常有急性发热和疼痛性口腔损害，多形红斑以靶形损害为特征；需梅毒血清学试验确认。"),
         B=variant("患者掌跖及躯干部持续出疹10天，皮损为带薄鳞屑的红褐色斑丘疹，无明显瘙痒，口腔见黏膜斑并有斑片状脱发。最需要优先排查哪种疾病？",
                   "二期梅毒", ["多形红斑", "玫瑰糠疹", "手足口病"],
                   "掌跖斑丘疹合并黏膜斑和斑片状脱发符合二期梅毒的多系统表现。其外观可模拟其他皮肤病，应结合梅毒螺旋体及非梅毒螺旋体试验判断；其他选项不能同样充分解释这一组合。")),
    dict(id="rash-measles-image", atlas_id="measles", difficulty="应用",
         point="斑丘疹图像与高热卡他症状的综合识别",
         reference="https://www.cdc.gov/measles/hcp/clinical-overview/index.html",
         A=variant("模拟病史：患者高热4天，伴咳嗽、流涕和结膜充血，随后出现图示皮损。近期未服用新药。结合图片及病史，最可能的诊断是？",
                   "麻疹", ["风疹", "猩红热", "发疹型药疹"],
                   "图中面颈部与胸部可见红色斑丘疹，部分融合。持续高热、咳嗽、流涕和结膜充血后出疹支持麻疹。风疹全身症状通常较轻，猩红热更突出砂纸样疹与咽炎，药疹需相应用药时序；疑似麻疹需实验室确认。",
                   "measles_16469.webp"),
         B=variant("模拟病史：患者发热伴流泪、畏光和干咳3天后出疹，背部皮损如下图，出疹期间仍有高热。近期无新用药。哪种疾病与图像及病程最相符？",
                   "麻疹", ["发疹型药疹", "风疹", "猩红热"],
                   "图中背部广泛红色斑丘疹，部分融合，结合出疹前后高热与明显呼吸道、结膜症状，支持麻疹。图片外观不能单独确诊，需结合核酸和血清学检测；风疹、猩红热及药疹的伴随表现与病程不同。",
                   "measles_24434.webp")),
    dict(id="rash-rubella-image", atlas_id="rubella", difficulty="应用",
         point="斑丘疹图像与轻度发热淋巴结肿大的综合识别",
         reference="https://www.cdc.gov/rubella/hcp/clinical-overview/index.html",
         A=variant("模拟病史：患者低热1天后出现图示皮疹，耳后及枕后淋巴结肿大，咳嗽和流涕不明显，近期未用药。结合图像，首先考虑哪种疾病？",
                   "风疹", ["麻疹", "猩红热", "发疹型药疹"],
                   "图中为红色斑疹、斑丘疹。轻度发热、耳后和枕后淋巴结肿大使风疹更符合；麻疹通常有明显高热及卡他症状，猩红热常伴咽炎和砂纸样疹。风疹的皮疹缺乏足够特异性，需实验室检查确认。",
                   "rubella_22142.webp"),
         B=variant("模拟病史：患者先有枕后淋巴结肿大，次日面颈部出疹，24小时内扩展至躯干，体温37.8℃，精神状态良好，无用药史。图示皮损最应考虑哪种疾病？",
                   "风疹", ["猩红热", "发疹型药疹", "麻疹"],
                   "图示面颈、上胸部斑丘疹，结合淋巴结肿大早于出疹、低热及迅速扩展的病程，支持风疹。仅凭照片不能与其他发疹性疾病可靠区分；应结合病史和实验室结果。猩红热的咽炎、麻疹的卡他症状及药疹的用药时序均不突出。",
                   "rubella_24378.webp")),
    dict(id="rash-mpox-image", atlas_id="mpox", difficulty="应用",
         point="疱疹脓疱图像与疼痛淋巴结表现的鉴别",
         reference="https://www.who.int/news-room/fact-sheets/detail/mpox",
         A=variant("模拟病史：患者发热后躯干与上肢出现图示皮损，触痛明显，伴腋窝和腹股沟淋巴结肿大。结合皮损形态，最可能的诊断是？",
                   "猴痘", ["水痘", "脓疱疮", "播散性带状疱疹"],
                   "图中疱疹、脓疱边界较清楚，部分中央凹陷或结痂，结合疼痛和淋巴结肿大支持猴痘。水痘更常瘙痒且分批出疹，脓疱疮以浅表脓疱和蜜黄色痂为主，播散性带状疱疹需关注起始皮节病变。需采集皮损材料进行核酸检测。",
                   "mpox_12779.webp"),
         B=variant("模拟病史：患者发热、淋巴结肿大后掌部出现图示皮损，部分触之质实并有疼痛，口腔未见溃疡。观察图片，哪项诊断最符合？",
                   "猴痘", ["汗疱疹", "手足口病", "二期梅毒"],
                   "图中掌部圆形皮损边界较清楚，部分见中央凹陷、结痂及周围脱屑，结合质实触感、疼痛与淋巴结肿大支持猴痘。汗疱疹常为瘙痒性小疱，手足口病常伴急性口腔损害，二期梅毒更常为无明显痛痒的斑丘疹；需病原学确认。",
                   "mpox_12761.webp")),
    dict(id="rash-hfmd-image", atlas_id="hfmd", difficulty="应用",
         point="掌跖皮损图像与口腔损害的综合识别",
         reference="https://www.cdc.gov/hand-foot-mouth/signs-symptoms/index.html",
         A=variant("模拟病史：成人低热、咽痛后出现图示手部皮损，同时有疼痛性口腔糜烂，近期照护过有类似症状的幼儿。最可能的诊断是？",
                   "手足口病", ["二期梅毒", "汗疱疹", "多形红斑"],
                   "图中掌部多发红色丘疹、丘疱疹，与急性发热和疼痛性口腔损害相结合，支持成人手足口病。二期梅毒需结合病程及血清学；汗疱疹通常瘙痒且不解释发热口腔损害；多形红斑以典型靶形皮损为识别重点。",
                   "hfmd_pmc04_PMC10699830.webp"),
         B=variant("模拟病史：患者发热后进食时口腔疼痛，查体见口腔小疱及糜烂，掌跖皮损如下图。结合皮损部位和形态，最符合哪种疾病？",
                   "手足口病", ["多形红斑", "二期梅毒", "汗疱疹"],
                   "图示掌跖散在红色丘疹、疱疹，结合发热及疼痛性口腔损害，支持手足口病。汗疱疹、二期梅毒及多形红斑虽然也可累及手足，但需分别结合瘙痒、慢性病程与血清学、靶形损害等线索鉴别。",
                   "hfmd_pmc01_PMC10846910.webp")),
]


def bank():
    atlas = json.loads((ROOT / "assets/rash-atlas/atlas.json").read_text())
    diseases = {d["id"]: d for c in atlas["categories"] for d in c["diseases"]}
    pairs = []
    for n, pair in enumerate(RASH_PAIRS):
        disease = diseases[pair["atlas_id"]]
        result = {**pair, "disease": disease["name"], "domain": "皮疹辨别",
                  "sources": [{"id": "atlas-" + disease["id"], "document": "皮疹图谱 · " + disease["name"], "url": ""},
                              {"id": pair["id"] + "-clinical", "document": "临床表现参考资料", "url": pair["reference"]}]}
        for form in ("A", "B"):
            q = dict(pair[form])
            assert len(set(q["choices"])) == 4 and q["answer"] in q["choices"]
            assert bool(q.get("image_file")) == (n >= 4)
            if q.get("image_file"):
                source = next(i for i in disease["images"] if i["file"] == q["image_file"])
                if not (IMAGE_DIR / q["image_file"]).is_file():
                    raise ValueError("Missing assessment image: " + q["image_file"])
                q["image_source"] = {k: source.get(k, "") for k in ("provider", "source_label", "license", "caption", "links")}
            result[form] = q
        pairs.append(result)
    return pairs
