"""Eight parallel image-based rash-recognition items from the existing atlas.

Every item requires inspection of a clinical image.  A and B use different
views or crops while testing the same paired knowledge point. Histories are
teaching simulations, not photographed-patient data. Image filenames and
diagnostic captions stay in the frozen server-side paper.
"""
import json
from pathlib import Path

from src.assessment_bank import item

ROOT = Path(__file__).resolve().parents[1]
IMAGE_DIR = ROOT / "assets/rash-atlas/images"


def variant(stem, correct, distractors, explanation, image_file, source_image_file=None,
            correct_index=None):
    return {**item(stem, correct, *distractors), "explanation": explanation,
            "image_file": image_file,
            **({"source_image_file": source_image_file} if source_image_file else {}),
            **({"correct_index": correct_index} if correct_index is not None else {})}


RASH_PAIRS = [
    dict(id="rash-varicella", atlas_id="varicella", difficulty="基础",
         point="分批出疹与多期皮损并存的识别",
         reference="https://www.cdc.gov/chickenpox/hcp/clinical-signs/index.html",
         A=variant("患者发热后出现瘙痒性皮疹，躯干较四肢远端明显。结合图示皮损形态和分布，最符合哪种疾病？",
                   "水痘", ["猴痘", "播散性带状疱疹", "大疱性脓疱疮"],
                   "图中躯干部可见散在、分批出现的丘疹与疱疹样皮损，结合向心性分布和瘙痒支持水痘。猴痘皮损通常更深在、质硬；播散性带状疱疹需关注起始的皮节性疼痛；大疱性脓疱疮以浅表松弛性大疱、糜烂和痂皮为主。",
                   "varicella_book00_p93.webp", correct_index=0),
         B=variant("患者全身皮疹2天，头皮和胸背部较多，瘙痒明显，今日仍有新疹出现。观察图示皮损，最可能的诊断是？",
                   "水痘", ["播散性带状疱疹", "大疱性脓疱疮", "猴痘"],
                   "图中可见不同阶段的散在丘疹、疱疹样皮损，结合头皮和躯干为主、持续出现新疹及明显瘙痒，符合水痘。其他选项需分别结合皮节性起病、浅表大疱或深在疼痛性皮损等特征鉴别。",
                   "varicella_book00_p93_detail.webp", "varicella_book00_p93.webp", correct_index=1)),
    dict(id="rash-zoster", atlas_id="zoster", difficulty="基础",
         point="单侧皮节分布与神经痛的识别",
         reference="https://www.cdc.gov/shingles/hcp/clinical-signs/index.html",
         A=variant("56岁患者右侧腰腹部灼痛3天后出现图示皮损，病变局限于一侧。结合疼痛与分布，最可能的诊断是？",
                   "带状疱疹", ["接触性皮炎", "单纯疱疹", "水痘"],
                   "图中红斑、水疱样皮损沿单侧皮节呈带状分布，结合出疹前局部神经痛，支持带状疱疹。接触性皮炎由接触范围决定分布且瘙痒更常见；单纯疱疹常局限复发；水痘通常为全身分批出疹。",
                   "zoster_book00_p93_trunk.webp", "zoster_book00_p93.webp", correct_index=3),
         B=variant("61岁患者左侧额部和眼周先有灼痛，随后出现图示簇集性皮损，病变未越过面部中线。哪项诊断最符合？",
                   "带状疱疹", ["单纯疱疹", "水痘", "接触性皮炎"],
                   "图示皮损局限于单侧额部及眼周，呈簇集性疱疹样改变，与出疹前神经痛相吻合，支持眼支带状疱疹；还需评估眼部受累。单纯疱疹、水痘和接触性皮炎通常不能同时解释这种单侧神经分布与疼痛。",
                   "zoster_book00_p93_face.webp", "zoster_book00_p93.webp", correct_index=1)),
    dict(id="rash-scarlet", atlas_id="scarlet", difficulty="应用",
         point="砂纸样疹伴咽炎的鉴别",
         reference="https://www.cdc.gov/group-a-strep/hcp/clinical-guidance/scarlet-fever.html",
         A=variant("患者发热、咽痛2天后出现图示弥漫性皮疹，舌乳头突出，腋窝与肘窝皮疹较深。最可能的诊断是？",
                   "猩红热", ["麻疹", "风疹", "发疹型药疹"],
                   "图中可见弥漫充血基础上的细密丘疹，结合急性咽炎、皮肤皱褶处加深和草莓舌，支持猩红热，可通过咽拭子A群链球菌检测确认。麻疹更常伴明显卡他症状，风疹常伴耳后或枕后淋巴结肿大。",
                   "scarlet_5163.webp", correct_index=1),
         B=variant("青年患者急性咽痛、高热后出现图示皮疹，伴口周苍白和扁桃体充血。结合近观皮损，首先考虑哪种疾病？",
                   "猩红热", ["发疹型药疹", "风疹", "麻疹"],
                   "图中近观可见弥漫性细小丘疹形成的砂纸样外观，结合急性咽炎及口周苍白，最支持猩红热。其他发疹性疾病可有相似红疹，但伴随体征和皮损质地不同，诊断需A群链球菌检测支持。",
                   "scarlet_5163_detail.webp", "scarlet_5163.webp", correct_index=1)),
    dict(id="rash-syphilis", atlas_id="syphilis", difficulty="应用",
         point="掌跖斑丘疹与二期梅毒的识别",
         reference="https://www.cdc.gov/syphilis/about/index.html",
         A=variant("成人出现图示躯干皮疹，瘙痒不明显，伴全身淋巴结肿大；两个月前有自行愈合的无痛性生殖器溃疡。最可能的诊断是？",
                   "二期梅毒", ["玫瑰糠疹", "手足口病", "多形红斑"],
                   "图中躯干可见泛发、较对称的斑丘疹，结合无明显瘙痒、全身淋巴结肿大和既往无痛性溃疡的病程，支持二期梅毒。玫瑰糠疹、手足口病及多形红斑不能同样充分解释这一组合，需梅毒血清学试验确认。",
                   "syphilis_book00_p235_trunk.webp", "syphilis_book00_p235.webp", correct_index=1),
         B=variant("患者持续出疹10天，口腔见黏膜斑并有斑片状脱发，掌部皮损如下图。最需要优先排查哪种疾病？",
                   "二期梅毒", ["多形红斑", "玫瑰糠疹", "手足口病"],
                   "图示掌部斑丘疹伴薄鳞屑，结合黏膜斑和斑片状脱发，符合二期梅毒的多系统表现。其外观可模拟其他皮肤病，应结合梅毒螺旋体及非梅毒螺旋体试验判断。",
                   "syphilis_book00_p235_palms.webp", "syphilis_book00_p235.webp", correct_index=3)),
    dict(id="rash-measles-image", atlas_id="measles", difficulty="应用",
         point="斑丘疹图像与高热卡他症状的综合识别",
         reference="https://www.cdc.gov/measles/hcp/clinical-overview/index.html",
         A=variant("患者高热4天，伴咳嗽、流涕和结膜充血，随后出现图示皮损。结合图片及病史，最可能的诊断是？",
                   "麻疹", ["风疹", "猩红热", "发疹型药疹"],
                   "图中面颈部与胸部可见红色斑丘疹，部分融合。持续高热、咳嗽、流涕和结膜充血后出疹支持麻疹。风疹全身症状通常较轻，猩红热更突出砂纸样疹与咽炎，药疹需相应用药时序；疑似麻疹需实验室确认。",
                   "measles_16469.webp"),
         B=variant("患者发热伴流泪、畏光和干咳3天后出疹，背部皮损如下图，出疹期间仍有高热。哪种疾病与图像及病程最相符？",
                   "麻疹", ["发疹型药疹", "风疹", "猩红热"],
                   "图中背部广泛红色斑丘疹，部分融合，结合出疹前后高热与明显呼吸道、结膜症状，支持麻疹。图片外观不能单独确诊，需结合核酸和血清学检测；风疹、猩红热及药疹的伴随表现与病程不同。",
                   "measles_24434.webp")),
    dict(id="rash-rubella-image", atlas_id="rubella", difficulty="应用",
         point="斑丘疹图像与轻度发热淋巴结肿大的综合识别",
         reference="https://www.cdc.gov/rubella/hcp/clinical-overview/index.html",
         A=variant("患者低热1天后出现图示皮疹，耳后及枕后淋巴结肿大，咳嗽和流涕不明显。结合图像，首先考虑哪种疾病？",
                   "风疹", ["麻疹", "猩红热", "发疹型药疹"],
                   "图中为红色斑疹、斑丘疹。轻度发热、耳后和枕后淋巴结肿大使风疹更符合；麻疹通常有明显高热及卡他症状，猩红热常伴咽炎和砂纸样疹。风疹的皮疹缺乏足够特异性，需实验室检查确认。",
                   "rubella_22142.webp"),
         B=variant("患者先有枕后淋巴结肿大，次日面颈部出疹，24小时内扩展至躯干，体温37.8℃，精神状态良好。图示皮损最应考虑哪种疾病？",
                   "风疹", ["猩红热", "发疹型药疹", "麻疹"],
                   "图示面颈、上胸部斑丘疹，结合淋巴结肿大早于出疹、低热及迅速扩展的病程，支持风疹。仅凭照片不能与其他发疹性疾病可靠区分；应结合病史和实验室结果。猩红热的咽炎、麻疹的卡他症状及药疹的用药时序均不突出。",
                   "rubella_24378.webp")),
    dict(id="rash-mpox-image", atlas_id="mpox", difficulty="应用",
         point="疱疹脓疱图像与疼痛淋巴结表现的鉴别",
         reference="https://www.who.int/news-room/fact-sheets/detail/mpox",
         A=variant("患者发热后躯干与上肢出现图示皮损，触痛明显，伴腋窝和腹股沟淋巴结肿大。结合皮损形态，最可能的诊断是？",
                   "猴痘", ["水痘", "脓疱疮", "播散性带状疱疹"],
                   "图中疱疹、脓疱边界较清楚，部分中央凹陷或结痂，结合疼痛和淋巴结肿大支持猴痘。水痘更常瘙痒且分批出疹，脓疱疮以浅表脓疱和蜜黄色痂为主，播散性带状疱疹需关注起始皮节病变。需采集皮损材料进行核酸检测。",
                   "mpox_12779.webp"),
         B=variant("患者发热、淋巴结肿大后掌部出现图示皮损，部分触之质实并有疼痛，口腔未见溃疡。观察图片，哪项诊断最符合？",
                   "猴痘", ["汗疱疹", "手足口病", "二期梅毒"],
                   "图中掌部圆形皮损边界较清楚，部分见中央凹陷、结痂及周围脱屑，结合质实触感、疼痛与淋巴结肿大支持猴痘。汗疱疹常为瘙痒性小疱，手足口病常伴急性口腔损害，二期梅毒更常为无明显痛痒的斑丘疹；需病原学确认。",
                   "mpox_12761.webp")),
    dict(id="rash-hfmd-image", atlas_id="hfmd", difficulty="应用",
         point="掌跖皮损图像与口腔损害的综合识别",
         reference="https://www.cdc.gov/hand-foot-mouth/signs-symptoms/index.html",
         A=variant("成人低热、咽痛后出现图示手部皮损，同时有疼痛性口腔糜烂，近期照护过有类似症状的幼儿。最可能的诊断是？",
                   "手足口病", ["二期梅毒", "汗疱疹", "多形红斑"],
                   "图中掌部多发红色丘疹、丘疱疹，与急性发热和疼痛性口腔损害相结合，支持成人手足口病。二期梅毒需结合病程及血清学；汗疱疹通常瘙痒且不解释发热口腔损害；多形红斑以典型靶形皮损为识别重点。",
                   "hfmd_pmc04_PMC10699830.webp"),
         B=variant("患者发热后进食时口腔疼痛，查体见口腔小疱及糜烂，掌跖皮损如下图。结合皮损部位和形态，最符合哪种疾病？",
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
            source_file = q.pop("source_image_file", q["image_file"])
            source = next(i for i in disease["images"] if i["file"] == source_file)
            if not (IMAGE_DIR / q["image_file"]).is_file():
                raise ValueError("Missing assessment image: " + q["image_file"])
            q["image_source"] = {k: source.get(k, "") for k in ("provider", "source_label", "license", "caption", "links")}
            if q["image_file"] != source_file:
                q["image_source"]["caption"] = (q["image_source"].get("caption", "") + "（测验中使用原图局部裁切。）").strip()
            result[form] = q
        pairs.append(result)
    return pairs
