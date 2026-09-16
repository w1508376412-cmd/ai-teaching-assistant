# AI教学工具 · 传染病学教学工作台

面向临床医学学生传染病学教学的一体化工作台。项目采用 **FastAPI + 原生 HTML/CSS/JavaScript**，不依赖 Streamlit。

## 功能模块

1. **临床皮疹图谱**：收录 8 个疾病类别、30 个病种和 72 张临床图像；支持病名与症状检索、疾病类别筛选、皮损形态筛选、病种详情和 2–3 病种并排鉴别。
2. **AI 鉴别训练**：根据学员的皮损观察记录，在完整图谱或已选择候选病种中梳理支持证据、冲突证据、下一步验证与危重红旗。
3. **RAG 知识问答**：基于 267 个结构化知识块、33 个病种执行 BM25 与本地 TF-IDF 向量混合检索、加权 RRF 融合和确定性重排序，并通过流式响应实时显示模型答案；证据标签仅在后端上下文中使用，问答界面保持干净，不显示引用标注。
4. **情景演练**：围绕知识库覆盖的传染病提供 10 个临床情景，训练症候识别、鉴别诊断、检查选择、隔离与治疗原则，并给出基于权威指南的教学反馈。
5. **知识测验**：首次登录完成前测后解锁学习；教师统一开放后测。A/B配对试卷包含基础知识20题×3分、皮疹辨别8题×2分、模拟案例8小题×3分，共36小题、100分。皮疹辨别前4题纯文字、后4题配图；前后卷设问与图片不同，考点对应。前测即时出分，提供逐题解析和知识问答跳转。
6. **教师管理**：教师身份登录后统一开放/关闭后测、预览A/B试卷与图片、导出配对成绩及逐题作答。知识库与情景内容均由版本化文件维护，不提供网页上传入口。

图谱已移除独立小测验，保留原有浏览功能。已有测验按版本冻结，不因升级改写旧成绩；详细题量、配对规则和数据说明见[教师使用说明](docs/知识测验教师使用说明.md)。

> 图谱和 AI 输出仅用于教学训练，不能替代面诊、病理或实验室诊断。

## 技术结构

```text
├── assets/rash-atlas/
│   ├── atlas.json          # 结构化病种、鉴别要点与逐图来源
│   ├── images/             # 72 张网页尺寸 WebP 图片
│   └── sources.csv         # 图片来源清单
├── cases/                  # JSON 临床教学情景
├── rag_data/
│   └── chunks.jsonl        # 结构化知识块与原始来源 URL
├── scripts/
│   └── import_rash_atlas.py
├── src/
│   ├── main.py             # FastAPI、AI 接口与教师接口
│   ├── study.py            # 登录、持久化作答、前后测权限与计分
│   ├── assessment_bank.py  # 配对基础题与临床案例
│   ├── rash_assessment_bank.py # 图谱来源的配对皮疹题
│   ├── rag.py              # BM25、向量检索、RRF、上下文与引用构建
│   └── static/             # 独立网页前端
├── Dockerfile
└── requirements.txt
```

## 本地运行

建议使用 Python 3.11+。

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn src.main:app --host 127.0.0.1 --port 8501
```

浏览器访问：`http://127.0.0.1:8501`

教师管理入口：`http://127.0.0.1:8501/?admin=true`

不要直接双击 `src/static/index.html`。页面依赖后端接口和 `/assets` 静态资源路径，必须通过 FastAPI 地址打开。

## 环境变量

```text
DEEPSEEK_API_KEY=你的 API Key
OPENAI_BASE_URL=https://api.deepseek.com
MODEL_NAME=deepseek-v4-flash
ADMIN_PASSWORD=请设置一个安全密码
TEACHER_NAME=教师姓名
TEACHER_STUDENT_NO=教师学号
STUDY_DATA_DIR=var
STUDY_REQUIRE_VOLUME=false
RAG_CANDIDATE_K=16
RAG_CONTEXT_K=8
RAG_LLM_RERANK_ENABLED=false
AI_MAX_TOKENS=1200
AI_TIMEOUT_SECONDS=45
KNOWLEDGE_HISTORY_MAX_MESSAGES=8
KNOWLEDGE_HISTORY_MAX_CHARACTERS=12000
RETRIEVAL_HISTORY_QUESTIONS=2
RETRIEVAL_QUERY_MAX_CHARACTERS=4000
```

未配置 `DEEPSEEK_API_KEY` 时，图谱检索、图片查看和并排比较仍可使用；AI 问答、鉴别训练与情景反馈会提示等待配置。通过 `TEACHER_NAME` 和 `TEACHER_STUDENT_NO` 识别教师账号；`ADMIN_PASSWORD` 是可选的管理API验证方式。生产环境需挂载持久卷，设置 `STUDY_DATA_DIR=/data` 和 `STUDY_REQUIRE_VOLUME=true`。

## 知识问答架构

`rag_data/chunks.jsonl` 中的每行都是一个独立知识块，包含病种、类别、病原体、法定分类、文档、章节、正文、来源 URL 和唯一 ID。服务启动后在内存中完成以下流程：

1. **结构化索引**：正文与病种、文档、章节等元数据共同参与索引，并校验必填字段和唯一 ID。
2. **混合召回**：中文 2–4 字 n-gram BM25 与 2048 维 TF-IDF feature-hashing 向量同时召回候选块。
3. **融合与重排序**：通过加权 RRF 融合两路排序，默认使用本地确定性相关度重排序，以避免回答前额外等待一次模型请求；如更看重模型重排效果，可设置 `RAG_LLM_RERANK_ENABLED=true`。
4. **答案生成**：只把重排后的证据块交给回答模型，并将生成内容实时推送到页面。证据标签和来源元数据用于内部检索审计，最终问答界面不显示 `[K#]` 或引用卡片。

运行本地接口与检索测试（测试依赖为 httpx）：

```bash
pip install httpx
python -m unittest discover -s tests -v
```

## 情景演练作答

- 病例编号统一显示为 Clinical Case 1–10。病例资料保留症状、体征、初步检查和客观暴露史，不直接写目标病名或教学目标。
- 页面同时展示诊断判断、检查、治疗、临床处置四栏，每栏四项；诊断判断为单选，其余三栏为多选。
- 点击“提交判断”后统一展示反馈、参考答案与依据。切换案例会保留本页各案例的选择和反馈；刷新网页会开始新的练习。
- 初始接口使用白名单，只返回病例资料、匿名标识和随机排序后的四组选项，不返回病种标签、教学目标、答案或解析。后端会校验提交内容是否属于当前案例提供的选项。

浏览器回归测试见 `tests/browser_case_training.cjs`。先启动不调用真实模型的本地服务，再在另一终端运行测试：

```bash
PYTHONPATH=. python tests/run_study_server.py
# 另一个终端，安装或提供 Playwright 后运行：
node tests/browser_case_training.cjs
node tests/browser_study.cjs
```

可用 `PLAYWRIGHT_MODULE` 指定 Playwright 模块路径、`CHROME_PATH` 指定浏览器、`CASE_TEST_OUTPUT` 指定截图目录。测试覆盖全部10个病例、四栏同时展示、跨案例异步隔离、提交失败重试，以及1440/842/390像素布局。勿对生产服务运行此脚本，以免产生真实模型调用。

## 图谱数据更新

独立图谱网站的内容可通过导入脚本重新生成结构化资源：

```bash
python scripts/import_rash_atlas.py \
  "/path/to/rash-atlas" \
  "assets/rash-atlas"
```

脚本只读取源项目，复制网页尺寸图片并生成 `atlas.json`；不会修改原图谱项目。

## 图片来源与许可

- **CDC PHIL**：仅收录经原站核对为公有领域的图像。
- **PubMed Central**：仅收录 CC BY / CC0 开放许可文献配图。
- **《皮肤性病学》第 10 版（人民卫生出版社，2024）**：版权归出版社与原作者，仅供个人教学参考。

网页病种详情会逐图显示来源、许可和原始链接。完整清单见 `assets/rash-atlas/sources.csv`。

## Zeabur 部署

项目根目录包含 `Dockerfile`，推送到 GitHub 后可在 Zeabur 中直接按仓库部署。服务监听 Zeabur 提供的 `PORT` 环境变量。

部署后在 Zeabur 服务中配置上述环境变量，并在 Networking / Domains 中生成访问域名。
