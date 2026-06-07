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

```json
{
  "start_page": 1,
  "max_pages": 10
}
```

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
  "provider": "deepseek/deepseek-v4-flash",
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

## Review Outline

`POST /courses/{course_id}/review-outline`

生成复习提纲，返回 `content` 和 `sources`。

## Practice

`POST /courses/{course_id}/practice`

```json
{
  "count": 10
}
```

生成练习题，返回 `content` 和 `sources`。
