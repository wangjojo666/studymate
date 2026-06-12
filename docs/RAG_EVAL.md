# RAG 评估说明

`scripts/rag_eval.py` 用来做课程设计级的 RAG 冒烟评估。它不是复杂 benchmark，而是帮助答辩时说明系统不是随便返回答案：每个问题都会展示 top sources、score、关键词命中和来源 hint 命中情况。

## 准备数据

1. 启动后端。
2. 登录前端，新建课程并上传一份小型 TXT/PDF/DOCX 资料。
3. 等资料状态变为 `indexed`。
4. 记下课程 ID。
5. 复制 `docs/rag_eval_cases.example.json`，把 `course_id` 改成本地课程 ID。

示例：

```json
[
  {
    "course_id": 1,
    "question": "虚函数为什么能支持运行时多态？",
    "expected_keywords": ["虚函数", "多态"],
    "expected_source_hint": "virtual"
  }
]
```

字段说明：

- `course_id`：已上传资料的课程 ID。
- `question`：要测试的问题。
- `expected_keywords`：期望答案中出现的关键词，用于粗略检查回答是否覆盖重点。
- `expected_source_hint`：期望来源文件名或片段预览中出现的提示词，用于粗略检查检索是否命中相关资料。

## 运行

```powershell
cd D:\sunny\studymate
python scripts\rag_eval.py docs\rag_eval_cases.example.json
```

默认脚本会用演示账号登录：

```text
demo@studymate.local / studymate-demo
```

也可以使用已有 token：

```powershell
$env:STUDYMATE_API_TOKEN="..."
python scripts\rag_eval.py docs\rag_eval_cases.example.json
```

如后端不是默认地址：

```powershell
$env:STUDYMATE_API_BASE_URL="http://127.0.0.1:8000/api"
python scripts\rag_eval.py docs\rag_eval_cases.example.json
```

## 解读结果

输出中重点看：

- `answer_status`：`answered` 表示证据足够；`low_confidence` 表示证据不足已拒答。
- `confidence`：由最高检索分数粗略映射为 high/medium/low。
- `top_sources`：查看文件名、页码、chunk、score、preview。
- `keyword_hit`：答案是否覆盖期望关键词。
- `source_hint_hit`：来源片段是否命中预期提示词。

如果 `answer_status=low_confidence`，这是预期安全行为：系统没有找到足够证据，不应硬编答案。

## 默认 hash embedding 的限制

默认 `EMBEDDING_PROVIDER=hash` 是课程设计演示方案，主要保证本地稳定运行。它不是深度语义模型，跨表达、同义改写和复杂语义匹配会比较弱。

如果要更真实地评估语义检索效果，建议切换：

```env
EMBEDDING_PROVIDER=sentence_transformers
EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5
```

或接入 OpenAI-compatible embedding 服务。切换后需要重新上传或重新索引资料，确保向量库使用新的 embedding。
