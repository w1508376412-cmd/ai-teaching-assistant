# AI教学工具 · 临床流行病教学工作台

面向公共卫生、口岸卫生检疫与临床流行病学教学的一体化工作台。项目采用 **FastAPI + 原生 HTML/CSS/JavaScript**，不依赖 Streamlit。

## 功能模块

1. **临床皮疹图谱**：收录 8 个疾病类别、30 个病种和 72 张临床图像；支持病名与症状检索、疾病类别筛选、皮损形态筛选、病种详情和 2–3 病种并排鉴别。
2. **AI 鉴别训练**：根据学员的皮损观察记录，在完整图谱或已选择候选病种中梳理支持证据、冲突证据、下一步验证与危重红旗。
3. **RAG 知识问答**：基于 180 个结构化知识块执行 BM25 与本地 TF-IDF 向量混合检索、加权 RRF 融合和模型 Reranker 重排序；证据标签仅在后端上下文中使用，问答界面保持干净，不显示引用标注。
4. **案例推演**：支持决策判断题和分阶段引导案例，提供基于 SOP 的教学反馈。
5. **教师管理**：通过受保护入口维护案例，以及从参考材料生成案例。知识库为经过结构化处理的版本化数据，不提供网页上传入口。

> 图谱和 AI 输出仅用于教学训练，不能替代面诊、病理或实验室诊断。

## 技术结构

```text
├── assets/rash-atlas/
│   ├── atlas.json          # 结构化病种、鉴别要点与逐图来源
│   ├── images/             # 72 张网页尺寸 WebP 图片
│   └── sources.csv         # 图片来源清单
├── cases/                  # JSON 教学案例
├── rag_data/
│   └── chunks.jsonl        # 结构化知识块与原始来源 URL
├── scripts/
│   └── import_rash_atlas.py
├── src/
│   ├── main.py             # FastAPI、AI 接口与教师接口
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
RAG_CANDIDATE_K=16
RAG_CONTEXT_K=8
```

未配置 `DEEPSEEK_API_KEY` 时，图谱检索、图片查看和并排比较仍可使用；AI 问答、鉴别训练与案例反馈会提示等待配置。未配置 `ADMIN_PASSWORD` 时，教师管理功能保持关闭。

## 知识问答架构

`rag_data/chunks.jsonl` 中的每行都是一个独立知识块，包含病种、类别、病原体、法定分类、文档、章节、正文、来源 URL 和唯一 ID。服务启动后在内存中完成以下流程：

1. **结构化索引**：正文与病种、文档、章节等元数据共同参与索引，并校验必填字段和唯一 ID。
2. **混合召回**：中文 2–4 字 n-gram BM25 与 2048 维 TF-IDF feature-hashing 向量同时召回候选块。
3. **融合与重排序**：通过加权 RRF 融合两路排序，再用当前配置的 DeepSeek 模型执行第二阶段 Reranker；模型不可用时使用确定性相关度排序降级。
4. **答案生成**：只把重排后的证据块交给回答模型。证据标签和来源元数据用于内部检索审计，最终问答界面不显示 `[K#]` 或引用卡片。

运行本地检索测试：

```bash
python -m unittest discover -s tests -v
```

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
