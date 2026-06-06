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
