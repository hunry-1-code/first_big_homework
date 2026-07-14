ALTER TABLE article ADD COLUMN source_layer VARCHAR(24) NOT NULL DEFAULT 'unknown';
ALTER TABLE article ADD COLUMN source_role VARCHAR(32) NOT NULL DEFAULT 'unknown';
CREATE TABLE IF NOT EXISTS comment (
 id INTEGER PRIMARY KEY,
 article_id INTEGER NOT NULL, parent_comment_id INTEGER,
 platform VARCHAR(50) NOT NULL, source_comment_id VARCHAR(255) NOT NULL,
 content TEXT NOT NULL, content_hash VARCHAR(64) NOT NULL,
 content_kind VARCHAR(20) NOT NULL DEFAULT 'comment', author VARCHAR(255),
 likes_count BIGINT DEFAULT 0, replies_count BIGINT DEFAULT 0,
 sentiment_label VARCHAR(20), sentiment_score FLOAT,
 analysis_status VARCHAR(20) DEFAULT 'pending', raw_json JSON,
 created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
 UNIQUE(platform, source_comment_id)
);
