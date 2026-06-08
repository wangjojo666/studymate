# StudyMate API

Base URL: `http://127.0.0.1:8000/api`

## Health

`GET /health`

## Courses

`GET /courses`

返回课程列表，包含资料数量、知识片段数量、最近提问时间。

`POST /courses`

```json
{
  "name": "高等数学",
  "description": "函数、极限、导数、积分"
}
```

`GET /courses/{course_id}`

返回课程详情和资料列表。

`DELETE /courses/{course_id}`

删除课程及其资料记录、chunk 和生成内容。

## Documents

`POST /courses/{course_id}/documents`

`multipart/form-data` 上传字段：

- `file`: PDF、PPTX、DOCX 或 TXT

大小限制：

- PDF / PPTX / DOCX：最大 100MB
- TXT：最大 10MB

返回解析状态：

```json
{
  "id": 1,
  "original_filename": "C++ 第三章.pdf",
  "status": "indexed",
  "page_count": 20,
  "chunk_count": 35,
  "error_message": ""
}
```

`POST /courses/{course_id}/documents/{document_id}/ocr`

创建后台 OCR 任务。后端会调用本地 `qwen3-vl:30b` 做 OCR，并把识别结果切分入库。
单次 OCR 最多 20 页，建议优先使用 `fast` 模式处理 5-10 页。

```json
{
  "start_page": 1,
  "max_pages": 8,
  "mode": "fast"
}
```

`mode` 可选：

- `fast`: 快速索引模式，低分辨率读取页面并抽取标题、公式、概念、题型和易错点，优先让资料尽快进入可检索知识库。
- `full`: 精确 OCR 模式，尽量逐字识别整页，适合少量关键页，速度明显更慢。

返回 OCR 任务和资料状态：

```json
{
  "id": 1,
  "document_id": 2,
  "status": "queued",
  "start_page": 1,
  "max_pages": 10,
  "processed_pages": 0,
  "document": {
    "id": 2,
    "status": "ocr_queued"
  }
}
```

`GET /courses/{course_id}/documents/{document_id}/ocr-jobs/{job_id}`

查询 OCR 任务进度。`status` 可能是 `queued`、`running`、`completed`、`failed`。

`POST /courses/{course_id}/documents/{document_id}/ocr-jobs/{job_id}/cancel`

停止正在运行的 OCR 任务；已入库的页面片段会保留。

`DELETE /courses/{course_id}/documents/{document_id}`

删除单个资料，同时删除对应 `DocumentChunk`、`ChunkKnowledgePoint`、OCR 任务和本地上传文件。若知识点来源于该资料，会清空来源信息但保留学习画像中的知识点记录。

## RAG Question Answering

`POST /courses/{course_id}/ask`

```json
{
  "question": "第三章的重点是什么？",
  "top_k": 5
}
```

返回：

```json
{
  "answer": "根据课程资料，第三章重点包括……",
  "provider": "mock/offline",
  "sources": [
    {
      "document_name": "C++ 第三章.pdf",
      "page": 12,
      "score": 0.62,
      "preview": "第三章主要介绍类与对象……"
    }
  ]
}
```

`provider` 会返回后端实际使用的链路，例如 `mock/offline`、`deepseek/deepseek-v4-flash` 或 `ollama/qwen3-vl:30b`。

## Review Outline

`POST /courses/{course_id}/review-outline`

生成复习提纲，返回 `content` 和 `sources`。

## Practice

`POST /courses/{course_id}/practice`

```json
{
  "count": 10,
  "difficulty": "mistake",
  "knowledge_point_id": 3
}
```

生成练习题，返回 `content` 和 `sources`。`difficulty` 可选：

- `basic`: 基础题
- `advanced`: 提高题
- `exam`: 考试题
- `mistake`: 易错题

## Learning Diagnosis

`POST /courses/{course_id}/learning/sync`

根据课程资料 chunk 同步知识点和 chunk-知识点绑定。

`GET /courses/{course_id}/learning/profile`

返回学习画像，包含总学习行为、提问次数、练习正确率、总体掌握度、知识点掌握列表、薄弱知识点、推荐复习路径、最近练习记录和待办复习任务。

`GET /courses/{course_id}/learning/graph`

返回课程知识图谱：

```json
{
  "nodes": [
    {
      "id": 1,
      "name": "格林公式",
      "mastery_score": 42,
      "wrong_count": 2,
      "source_page": 45,
      "state": "weak"
    }
  ],
  "edges": [
    {
      "source": 1,
      "target": 2,
      "relation": "co_occurs"
    }
  ]
}
```

`POST /courses/{course_id}/learning/attempts`

记录一次练习结果，并更新知识点掌握度；答错时会自动生成错题复盘任务。

```json
{
  "knowledge_point_id": 1,
  "question_text": "使用格林公式时为什么需要补全边界？",
  "user_answer": "直接套公式",
  "correct_answer": "需要保证曲线为正向闭合曲线，新增边界积分要按方向加减。",
  "is_correct": false,
  "error_reason": "边界条件理解不清",
  "difficulty": "mistake"
}
```

`GET /courses/{course_id}/learning/wrong-attempts`

返回错题本列表，包含题目、用户答案、参考答案、错因、难度和关联知识点。

`POST /courses/{course_id}/learning/review-plan`

根据考试日期、每天可复习时间和目标知识点生成复习计划。

```json
{
  "exam_date": "2026-06-20",
  "daily_minutes": 90,
  "goals": "曲线积分、多重积分"
}
```

`PATCH /courses/{course_id}/learning/tasks/{task_id}`

更新复习任务状态：

```json
{
  "status": "done"
}
```
