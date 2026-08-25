# AI 教学助手 - 流行病学与卫生统计

这是一个为公共卫生课程设计的 AI 教学工作台，采用 **FastAPI + 原生 HTML/CSS/JavaScript**，包含知识库问答、互动案例模拟和教师内容管理。

## 功能模块

1.  **知识库问答 (RAG Prototype):** 学生可以基于老师上传的讲义、教材内容进行提问。AI 会优先根据知识库内容进行回答。
2.  **案例模拟训练:** 沉浸式案例学习。AI 扮演引导员，带学生一步步完成突发事件调查、数据分析等任务。
3.  **教师管理端:** 老师可以直接在界面上更新知识库 Markdown 文档或上传 JSON 格式的案例。

## 目录结构

- `knowledge_base/`: 存放 Markdown 格式的课程资料。
- `cases/`: 存放 JSON 格式的模拟案例。
- `src/main.py`: FastAPI 后端和 API 入口。
- `src/static/`: 独立网页前端。

## 如何运行

### 1. 安装依赖
建议使用 Python 3.11+。
```bash
pip install -r requirements.txt
```

### 2. 启动应用
```bash
uvicorn src.main:app --host 0.0.0.0 --port 8501
```

浏览器访问 `http://127.0.0.1:8501`。

### 3. 配置 API
请通过环境变量配置 API Key（支持 DeepSeek、智谱 AI 等 OpenAI 兼容接口）：
```bash
export DEEPSEEK_API_KEY="你的 API Key"
export OPENAI_BASE_URL="https://api.deepseek.com"
export MODEL_NAME="deepseek-v4-flash"
export ADMIN_PASSWORD="教师管理密码"
```

教师管理入口为 `http://127.0.0.1:8501/?admin=true`。

### 4. 部署到 Zeabur

项目根目录已经包含 `Dockerfile`。将代码推送到 GitHub 后，在 Zeabur 中选择 **GitHub** 部署此仓库。Zeabur 会自动使用 Dockerfile 构建并启动应用。

在 Zeabur 服务的环境变量中设置：
```text
DEEPSEEK_API_KEY=你的 API Key
OPENAI_BASE_URL=https://api.deepseek.com
MODEL_NAME=deepseek-v4-flash
ADMIN_PASSWORD=请设置一个安全密码
```

部署完成后，在 Zeabur 服务的 Networking / Domains 中生成访问域名。

## 如何添加案例

案例以 JSON 格式存储在 `cases/` 目录下。系统同时支持 `interactive_v2` 决策判断格式和包含 `stages` 的分步推演格式，具体结构可参考现有案例文件。
