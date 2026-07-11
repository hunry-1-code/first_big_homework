CREATE TABLE IF NOT EXISTS sentiment_run (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    aggregation_run_id BIGINT NOT NULL,
    source_task_id BIGINT NULL,
    user_id INT NULL,
    scope VARCHAR(24) NOT NULL,
    mode VARCHAR(20) NOT NULL,
    attempt INT NOT NULL DEFAULT 1,
    dataset_hash VARCHAR(64) NOT NULL,
    config_hash VARCHAR(64) NOT NULL,
    config JSON NULL,
    versions JSON NULL,
    statistics JSON NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    warnings JSON NULL,
    error_code VARCHAR(64) NULL,
    error_message TEXT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    started_at DATETIME NULL,
    completed_at DATETIME NULL,
    CONSTRAINT uq_sentiment_run_fingerprint UNIQUE
        (aggregation_run_id, scope, mode, config_hash, attempt),
    INDEX ix_sentiment_run_status_created (status, created_at)
);

CREATE TABLE IF NOT EXISTS article_sentiment_result (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    sentiment_run_id BIGINT NOT NULL,
    article_id INT NOT NULL,
    content_identity VARCHAR(80) NOT NULL,
    aggregation_cluster_id BIGINT NULL,
    event_id INT NULL,
    label VARCHAR(16) NOT NULL,
    score DOUBLE NOT NULL,
    confidence DOUBLE NOT NULL,
    dimension VARCHAR(16) NOT NULL,
    target VARCHAR(200) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    method VARCHAR(24) NOT NULL,
    model_name VARCHAR(255) NULL,
    model_version VARCHAR(64) NULL,
    prompt_version VARCHAR(64) NOT NULL,
    preprocess_version VARCHAR(64) NOT NULL,
    raw_response JSON NULL,
    inherited_from_result_id BIGINT NULL,
    weight_details JSON NULL,
    warnings JSON NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_article_sentiment_run_article UNIQUE (sentiment_run_id, article_id),
    INDEX ix_article_sentiment_cache (article_id, content_identity),
    INDEX ix_article_sentiment_event (event_id)
);

CREATE TABLE IF NOT EXISTS event_sentiment_snapshot (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    sentiment_run_id BIGINT NOT NULL,
    event_id INT NULL,
    aggregation_cluster_id BIGINT NULL,
    calculated_at DATETIME NOT NULL,
    article_count INT NOT NULL DEFAULT 0,
    representative_count INT NOT NULL DEFAULT 0,
    raw_counts JSON NULL,
    weighted_ratios JSON NULL,
    dominant_label VARCHAR(16) NULL,
    average_score DOUBLE NOT NULL DEFAULT 0,
    daily_trend JSON NULL,
    platform_distribution JSON NULL,
    time_confidence VARCHAR(20) NOT NULL DEFAULT 'low',
    calculation_details JSON NULL,
    algorithm_version VARCHAR(64) NOT NULL,
    warnings JSON NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_sentiment_snapshot_run_event UNIQUE (sentiment_run_id, event_id),
    CONSTRAINT uq_sentiment_snapshot_run_cluster UNIQUE (sentiment_run_id, aggregation_cluster_id),
    INDEX ix_sentiment_snapshot_event_time (event_id, calculated_at)
);

ALTER TABLE article ADD COLUMN IF NOT EXISTS sentiment_confidence DOUBLE NULL;
ALTER TABLE article ADD COLUMN IF NOT EXISTS sentiment_dimension VARCHAR(16) NULL;
ALTER TABLE article ADD COLUMN IF NOT EXISTS sentiment_target VARCHAR(200) NULL;
ALTER TABLE article ADD COLUMN IF NOT EXISTS sentiment_content_identity VARCHAR(80) NULL;
ALTER TABLE article ADD COLUMN IF NOT EXISTS current_sentiment_result_id BIGINT NULL;
ALTER TABLE article ADD COLUMN IF NOT EXISTS sentiment_analyzed_at DATETIME NULL;

ALTER TABLE event ADD COLUMN IF NOT EXISTS current_sentiment_snapshot_id BIGINT NULL;
ALTER TABLE event ADD COLUMN IF NOT EXISTS sentiment_score DOUBLE NULL DEFAULT 0;
ALTER TABLE event ADD COLUMN IF NOT EXISTS sentiment_updated_at DATETIME NULL;
