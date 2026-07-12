-- One-time migration from the original project skeleton schema to the
-- crawler and preprocessing schema. Back up the database before running.

ALTER TABLE article DROP INDEX url;

ALTER TABLE article
    MODIFY COLUMN url VARCHAR(2048) NOT NULL,
    MODIFY COLUMN raw_content LONGTEXT NULL,
    MODIFY COLUMN clean_content LONGTEXT NULL,
    MODIFY COLUMN publish_time DATETIME NULL,
    MODIFY COLUMN author_followers BIGINT NULL,
    MODIFY COLUMN author_verified BOOLEAN NULL,
    MODIFY COLUMN comments_count BIGINT NULL,
    MODIFY COLUMN reposts_count BIGINT NULL,
    MODIFY COLUMN likes_count BIGINT NULL,
    ADD COLUMN source_type VARCHAR(20) NOT NULL DEFAULT 'news' AFTER platform,
    ADD COLUMN source_article_id VARCHAR(255) NULL AFTER source_type,
    ADD COLUMN url_hash CHAR(64) NULL AFTER url,
    ADD COLUMN content_type VARCHAR(20) NULL AFTER raw_json,
    ADD COLUMN language VARCHAR(20) NOT NULL DEFAULT 'unknown' AFTER content_type,
    ADD COLUMN extraction_method VARCHAR(32) NULL AFTER clean_error,
    ADD COLUMN extraction_degraded BOOLEAN NOT NULL DEFAULT FALSE AFTER extraction_method,
    ADD COLUMN processing_warnings JSON NULL AFTER extraction_degraded,
    ADD COLUMN normalize_version VARCHAR(20) NULL AFTER processing_warnings,
    ADD COLUMN preprocess_version VARCHAR(20) NULL AFTER normalize_version,
    ADD COLUMN quality_score FLOAT NULL AFTER preprocess_version,
    ADD COLUMN quality_level VARCHAR(20) NULL AFTER quality_score,
    ADD COLUMN quality_flags JSON NULL AFTER quality_level,
    ADD COLUMN nlp_weight FLOAT NOT NULL DEFAULT 1 AFTER quality_flags,
    ADD COLUMN is_advertisement BOOLEAN NOT NULL DEFAULT FALSE AFTER nlp_weight,
    ADD COLUMN advertisement_score FLOAT NULL AFTER is_advertisement,
    ADD COLUMN advertisement_reasons JSON NULL AFTER advertisement_score,
    ADD COLUMN is_duplicate BOOLEAN NOT NULL DEFAULT FALSE AFTER advertisement_reasons,
    ADD COLUMN duplicate_of_id INT NULL AFTER is_duplicate,
    ADD COLUMN duplicate_group_id VARCHAR(64) NULL AFTER duplicate_of_id,
    ADD COLUMN duplicate_method VARCHAR(30) NULL AFTER duplicate_group_id,
    ADD COLUMN duplicate_score FLOAT NULL AFTER duplicate_method,
    ADD COLUMN content_hash CHAR(64) NULL AFTER duplicate_score,
    ADD COLUMN simhash CHAR(16) NULL AFTER content_hash,
    ADD COLUMN dedup_version VARCHAR(20) NULL AFTER simhash,
    ADD COLUMN author_id VARCHAR(255) NULL AFTER author,
    ADD COLUMN views_count BIGINT NULL AFTER likes_count,
    ADD COLUMN engagement_score FLOAT NULL AFTER views_count,
    ADD COLUMN duplicate_weight FLOAT NOT NULL DEFAULT 1 AFTER engagement_score,
    ADD COLUMN spam_weight FLOAT NOT NULL DEFAULT 1 AFTER duplicate_weight,
    ADD COLUMN heat_contribution FLOAT NULL AFTER spam_weight,
    ADD COLUMN source_reliability_score FLOAT NULL AFTER heat_contribution,
    ADD COLUMN first_crawled_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ADD COLUMN last_crawled_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ADD COLUMN content_version INT NOT NULL DEFAULT 1,
    ADD COLUMN latest_snapshot_id BIGINT NULL;

-- PYTHON_URL_HASH_BACKFILL
-- The migration runner normalizes article.url and fills article.url_hash here.

UPDATE article
SET first_crawled_at = COALESCE(crawled_at, CURRENT_TIMESTAMP),
    last_crawled_at = COALESCE(crawled_at, CURRENT_TIMESTAMP)
WHERE first_crawled_at IS NULL OR last_crawled_at IS NULL;

ALTER TABLE article
    MODIFY COLUMN url_hash CHAR(64) NOT NULL,
    ADD UNIQUE KEY uq_article_url_hash (url_hash),
    ADD UNIQUE KEY uq_article_platform_source_id (platform, source_article_id),
    ADD CONSTRAINT fk_article_duplicate_of
        FOREIGN KEY (duplicate_of_id) REFERENCES article(id);

ALTER TABLE task
    ADD COLUMN payload JSON NULL AFTER message,
    ADD COLUMN result JSON NULL AFTER payload,
    ADD COLUMN heartbeat_at DATETIME NULL AFTER started_at,
    ADD COLUMN lease_token VARCHAR(64) NULL AFTER heartbeat_at,
    ADD COLUMN attempt INT NOT NULL DEFAULT 0 AFTER lease_token,
    ADD INDEX ix_task_created_by (created_by);

CREATE TABLE article_snapshot (
    id BIGINT NOT NULL AUTO_INCREMENT,
    article_id INT NOT NULL,
    crawled_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    http_status INT NULL,
    fetch_status VARCHAR(20) NOT NULL,
    content_hash CHAR(64) NULL,
    raw_content LONGTEXT NULL,
    raw_json JSON NULL,
    comments_count BIGINT NULL,
    reposts_count BIGINT NULL,
    likes_count BIGINT NULL,
    views_count BIGINT NULL,
    fetch_error TEXT NULL,
    PRIMARY KEY (id),
    INDEX ix_article_snapshot_article_id (article_id),
    CONSTRAINT fk_article_snapshot_article
        FOREIGN KEY (article_id) REFERENCES article(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE document_features (
    id BIGINT NOT NULL AUTO_INCREMENT,
    article_id INT NOT NULL,
    tokens JSON NULL,
    tfidf_tokens JSON NULL,
    sentiment_tokens JSON NULL,
    topics JSON NULL,
    mentions JSON NULL,
    tfidf_vector JSON NULL,
    segment_version VARCHAR(20) NULL,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_document_features_article_id (article_id),
    CONSTRAINT fk_document_features_article
        FOREIGN KEY (article_id) REFERENCES article(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE processing_log (
    id BIGINT NOT NULL AUTO_INCREMENT,
    task_id INT NULL,
    article_id INT NOT NULL,
    snapshot_id BIGINT NULL,
    stage VARCHAR(30) NOT NULL,
    status VARCHAR(20) NOT NULL,
    error_code VARCHAR(80) NULL,
    message TEXT NULL,
    retryable BOOLEAN NOT NULL DEFAULT FALSE,
    duration_ms INT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX ix_processing_log_task_id (task_id),
    INDEX ix_processing_log_article_id (article_id),
    CONSTRAINT fk_processing_log_task FOREIGN KEY (task_id) REFERENCES task(id),
    CONSTRAINT fk_processing_log_article FOREIGN KEY (article_id) REFERENCES article(id),
    CONSTRAINT fk_processing_log_snapshot FOREIGN KEY (snapshot_id) REFERENCES article_snapshot(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
