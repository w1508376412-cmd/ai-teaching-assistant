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
streamlit run ai-teaching-assistant/src/app.py
```

### 3. 配置 API
启动后，在侧边栏输入你的国内大模型 API Key（支持 DeepSeek, 智谱 AI 等 OpenAI 兼容接口）。

## 如何添加案例

案例以 JSON 格式存储在 `cases/` 目录下。每个案例包含 `id`, `title`, `background`, `stages` (步骤), 和 `answers_summary`。
具体格式可参考 `cases/food_poisoning.json`。
