CREATE TABLE courses (
  id INTEGER PRIMARY KEY,
  name VARCHAR(120) NOT NULL UNIQUE,
  description TEXT DEFAULT '',
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  last_asked_at DATETIME
);

CREATE TABLE documents (
  id INTEGER PRIMARY KEY,
  course_id INTEGER NOT NULL REFERENCES courses(id),
  original_filename VARCHAR(255) NOT NULL,
  stored_filename VARCHAR(255) NOT NULL,
  file_type VARCHAR(20) NOT NULL,
  file_path TEXT NOT NULL,
  status VARCHAR(40) NOT NULL DEFAULT 'processing',
  page_count INTEGER NOT NULL DEFAULT 0,
  chunk_count INTEGER NOT NULL DEFAULT 0,
  error_message TEXT DEFAULT '',
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL
);

CREATE TABLE document_chunks (
  id INTEGER PRIMARY KEY,
  course_id INTEGER NOT NULL REFERENCES courses(id),
  document_id INTEGER NOT NULL REFERENCES documents(id),
  chunk_index INTEGER NOT NULL,
  page_number INTEGER NOT NULL DEFAULT 1,
  content TEXT NOT NULL,
  token_weights TEXT NOT NULL,
  vector_norm FLOAT NOT NULL DEFAULT 0,
  created_at DATETIME NOT NULL
);

CREATE TABLE chat_messages (
  id INTEGER PRIMARY KEY,
  course_id INTEGER NOT NULL REFERENCES courses(id),
  question TEXT NOT NULL,
  answer TEXT NOT NULL,
  sources_json TEXT DEFAULT '[]',
  created_at DATETIME NOT NULL
);

CREATE TABLE generated_materials (
  id INTEGER PRIMARY KEY,
  course_id INTEGER NOT NULL REFERENCES courses(id),
  kind VARCHAR(40) NOT NULL,
  content TEXT NOT NULL,
  sources_json TEXT DEFAULT '[]',
  created_at DATETIME NOT NULL
);

CREATE TABLE knowledge_points (
  id INTEGER PRIMARY KEY,
  course_id INTEGER NOT NULL REFERENCES courses(id),
  name VARCHAR(120) NOT NULL,
  description TEXT DEFAULT '',
  parent_id INTEGER REFERENCES knowledge_points(id),
  source_document_id INTEGER REFERENCES documents(id),
  source_page INTEGER NOT NULL DEFAULT 0,
  evidence TEXT DEFAULT '',
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  UNIQUE(course_id, name)
);

CREATE TABLE chunk_knowledge_points (
  id INTEGER PRIMARY KEY,
  course_id INTEGER NOT NULL REFERENCES courses(id),
  chunk_id INTEGER NOT NULL REFERENCES document_chunks(id),
  knowledge_point_id INTEGER NOT NULL REFERENCES knowledge_points(id),
  weight FLOAT NOT NULL DEFAULT 1,
  created_at DATETIME NOT NULL,
  UNIQUE(chunk_id, knowledge_point_id)
);

CREATE TABLE user_knowledge_status (
  id INTEGER PRIMARY KEY,
  user_id VARCHAR(80) NOT NULL DEFAULT 'demo-user',
  course_id INTEGER NOT NULL REFERENCES courses(id),
  knowledge_point_id INTEGER NOT NULL REFERENCES knowledge_points(id),
  mastery_score FLOAT NOT NULL DEFAULT 50,
  wrong_count INTEGER NOT NULL DEFAULT 0,
  review_count INTEGER NOT NULL DEFAULT 0,
  last_review_time DATETIME,
  updated_at DATETIME NOT NULL,
  UNIQUE(user_id, course_id, knowledge_point_id)
);

CREATE TABLE question_attempts (
  id INTEGER PRIMARY KEY,
  user_id VARCHAR(80) NOT NULL DEFAULT 'demo-user',
  course_id INTEGER NOT NULL REFERENCES courses(id),
  knowledge_point_id INTEGER REFERENCES knowledge_points(id),
  question_text TEXT NOT NULL,
  user_answer TEXT DEFAULT '',
  correct_answer TEXT DEFAULT '',
  is_correct BOOLEAN NOT NULL DEFAULT 0,
  error_reason TEXT DEFAULT '',
  difficulty VARCHAR(20) NOT NULL DEFAULT 'basic',
  created_at DATETIME NOT NULL
);

CREATE TABLE review_tasks (
  id INTEGER PRIMARY KEY,
  user_id VARCHAR(80) NOT NULL DEFAULT 'demo-user',
  course_id INTEGER NOT NULL REFERENCES courses(id),
  knowledge_point_id INTEGER REFERENCES knowledge_points(id),
  task_type VARCHAR(40) NOT NULL DEFAULT 'review',
  title VARCHAR(160) NOT NULL,
  description TEXT DEFAULT '',
  deadline DATETIME,
  status VARCHAR(40) NOT NULL DEFAULT 'pending',
  estimated_minutes INTEGER NOT NULL DEFAULT 25,
  priority INTEGER NOT NULL DEFAULT 1,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL
);
