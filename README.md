# AI 教学助手 - 流行病学与卫生统计

这是一个为公共卫生课程设计的 AI 教学助手原型，包含**知识库问答**和**互动案例模拟**两大核心功能。

## 功能模块

1.  **知识库问答 (RAG Prototype):** 学生可以基于老师上传的讲义、教材内容进行提问。AI 会优先根据知识库内容进行回答。
2.  **案例模拟训练:** 沉浸式案例学习。AI 扮演引导员，带学生一步步完成突发事件调查、数据分析等任务。
3.  **教师管理端:** 老师可以直接在界面上更新知识库 Markdown 文档或上传 JSON 格式的案例。

## 目录结构

- `knowledge_base/`: 存放 Markdown 格式的课程资料。
- `cases/`: 存放 JSON 格式的模拟案例。
- `src/app.py`: Streamlit 应用主程序。

## 如何运行

### 1. 安装依赖
建议使用 Python 3.9+。
```bash
pip install streamlit openai
```

### 2. 启动应用
```bash
streamlit run src/app.py
```

### 3. 配置 API
请通过环境变量配置 API Key（支持 DeepSeek、智谱 AI 等 OpenAI 兼容接口）：
```bash
export DEEPSEEK_API_KEY="你的 API Key"
export OPENAI_BASE_URL="https://api.deepseek.com"
export MODEL_NAME="deepseek-v4-flash"
```

### 4. 部署到 Zeabur

项目根目录已经包含 `Dockerfile`。将代码推送到 GitHub 后，在 Zeabur 中选择 **GitHub** 部署此仓库。Zeabur 会自动使用 Dockerfile 构建并启动应用。

在 Zeabur 服务的环境变量中设置：
```text
DEEPSEEK_API_KEY=你的 API Key
OPENAI_BASE_URL=https://api.deepseek.com
MODEL_NAME=deepseek-v4-flash
```

部署完成后，在 Zeabur 服务的 Networking / Domains 中生成访问域名。

## 如何添加案例

案例以 JSON 格式存储在 `cases/` 目录下。每个案例包含 `id`, `title`, `background`, `stages` (步骤), 和 `answers_summary`。
具体格式可参考 `cases/food_poisoning.json`。
