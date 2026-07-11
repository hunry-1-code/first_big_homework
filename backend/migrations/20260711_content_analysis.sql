-- Add run-scoped content analysis persistence. Run after the crawler/preprocessing migration.

CREATE TABLE IF NOT EXISTS analysis_run (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NULL,
    source_task_id BIGINT NULL,
    mode VARCHAR(20) NOT NULL DEFAULT 'search',
    keyword VARCHAR(255) NULL,
    platforms JSON NULL,
    query_fingerprint CHAR(64) NOT NULL,
    dataset_hash CHAR(64) NOT NULL,
    config_hash CHAR(64) NOT NULL,
    article_count INT NOT NULL DEFAULT 0,
    representative_count INT NOT NULL DEFAULT 0,
    tfidf_config JSON NULL,
    versions JSON NULL,
    statistics JSON NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    warnings JSON NULL,
    error_code VARCHAR(64) NULL,
    error_message TEXT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at DATETIME NULL,
    completed_at DATETIME NULL,
    INDEX ix_analysis_run_user_created (user_id, created_at),
    INDEX ix_analysis_run_status (status),
    INDEX ix_analysis_run_fingerprint (query_fingerprint, dataset_hash),
    INDEX ix_analysis_run_dataset_hash (dataset_hash),
    INDEX ix_analysis_run_config_hash (config_hash),
    CONSTRAINT fk_analysis_run_user FOREIGN KEY (user_id) REFERENCES user(id),
    CONSTRAINT fk_analysis_run_task FOREIGN KEY (source_task_id) REFERENCES task(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS analysis_run_article (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    analysis_run_id BIGINT NOT NULL,
    article_id INT NOT NULL,
    article_snapshot_id BIGINT NULL,
    content_version INT NOT NULL DEFAULT 1,
    content_identity VARCHAR(80) NOT NULL,
    is_representative BOOLEAN NOT NULL DEFAULT FALSE,
    nlp_weight FLOAT NOT NULL DEFAULT 1,
    feature_status VARCHAR(30) NOT NULL DEFAULT 'pending',
    keywords JSON NULL,
    warnings JSON NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_analysis_run_article (analysis_run_id, article_id),
    INDEX ix_analysis_run_article_run_status (analysis_run_id, feature_status),
    INDEX ix_analysis_run_article_article (article_id),
    CONSTRAINT fk_analysis_run_article_run FOREIGN KEY (analysis_run_id) REFERENCES analysis_run(id) ON DELETE CASCADE,
    CONSTRAINT fk_analysis_run_article_article FOREIGN KEY (article_id) REFERENCES article(id),
    CONSTRAINT fk_analysis_run_article_snapshot FOREIGN KEY (article_snapshot_id) REFERENCES article_snapshot(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS article_embedding (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    article_id INT NOT NULL,
    article_snapshot_id BIGINT NULL,
    content_version INT NOT NULL DEFAULT 1,
    content_identity VARCHAR(80) NOT NULL,
    model_name VARCHAR(255) NOT NULL,
    model_version VARCHAR(64) NOT NULL DEFAULT 'default',
    preprocess_version VARCHAR(64) NOT NULL DEFAULT 'v1',
    dimension INT NOT NULL,
    vector JSON NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_article_embedding_version (article_id, content_identity, model_name, model_version, preprocess_version),
    INDEX ix_article_embedding_lookup (article_id, model_name, model_version),
    CONSTRAINT fk_article_embedding_article FOREIGN KEY (article_id) REFERENCES article(id),
    CONSTRAINT fk_article_embedding_snapshot FOREIGN KEY (article_snapshot_id) REFERENCES article_snapshot(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

