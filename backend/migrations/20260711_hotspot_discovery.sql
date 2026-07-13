-- Add hotspot topic discovery and event heat persistence after content analysis.

CREATE TABLE IF NOT EXISTS hotspot_run (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    analysis_run_id BIGINT NOT NULL,
    source_task_id BIGINT NULL,
    user_id INT NULL,
    mode VARCHAR(20) NOT NULL DEFAULT 'hot',
    scope VARCHAR(20) NOT NULL DEFAULT 'global',
    attempt INT NOT NULL DEFAULT 1,
    window_start DATETIME NULL,
    window_end DATETIME NULL,
    dataset_hash CHAR(64) NOT NULL,
    config_hash CHAR(64) NOT NULL,
    lda_config JSON NULL,
    selected_k INT NULL,
    metrics JSON NULL,
    versions JSON NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    topic_status VARCHAR(20) NOT NULL DEFAULT 'pending',
    heat_status VARCHAR(20) NOT NULL DEFAULT 'pending',
    warnings JSON NULL,
    error_code VARCHAR(64) NULL,
    error_message TEXT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at DATETIME NULL,
    completed_at DATETIME NULL,
    UNIQUE KEY uq_hotspot_run_fingerprint (analysis_run_id, config_hash, scope, mode, attempt),
    INDEX ix_hotspot_run_status_created (status, created_at),
    INDEX ix_hotspot_run_user_created (user_id, created_at),
    CONSTRAINT fk_hotspot_run_analysis FOREIGN KEY (analysis_run_id) REFERENCES analysis_run(id),
    CONSTRAINT fk_hotspot_run_task FOREIGN KEY (source_task_id) REFERENCES task(id),
    CONSTRAINT fk_hotspot_run_user FOREIGN KEY (user_id) REFERENCES user(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS hot_seed_expansion (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    seed_article_id INT NOT NULL,
    query VARCHAR(255) NOT NULL,
    crawl_task_id BIGINT NULL,
    platform VARCHAR(50) NOT NULL,
    article_id INT NOT NULL,
    source_rank INT NULL,
    discovered_at DATETIME NOT NULL,
    UNIQUE KEY uq_hot_seed_expansion_seed_query_article (seed_article_id, query, article_id),
    INDEX ix_hot_seed_expansion_article (article_id),
    INDEX ix_hot_seed_expansion_seed_query (seed_article_id, query),
    CONSTRAINT fk_hot_seed_expansion_seed FOREIGN KEY (seed_article_id) REFERENCES article(id),
    CONSTRAINT fk_hot_seed_expansion_task FOREIGN KEY (crawl_task_id) REFERENCES task(id),
    CONSTRAINT fk_hot_seed_expansion_article FOREIGN KEY (article_id) REFERENCES article(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS topic_result (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    hotspot_run_id BIGINT NULL,
    topic_index INT NOT NULL,
    keywords JSON NULL,
    category VARCHAR(30) NOT NULL DEFAULT '其他',
    topic_name VARCHAR(100) NOT NULL,
    naming_method VARCHAR(40) NOT NULL,
    naming_confidence FLOAT NOT NULL DEFAULT 0,
    document_count INT NOT NULL DEFAULT 0,
    probability_mass FLOAT NOT NULL DEFAULT 0,
    topic_signature CHAR(64) NOT NULL,
    warnings JSON NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_topic_result_run_index (hotspot_run_id, topic_index),
    INDEX ix_topic_result_run_category (hotspot_run_id, category),
    INDEX ix_topic_result_signature (topic_signature),
    CONSTRAINT fk_topic_result_run FOREIGN KEY (hotspot_run_id) REFERENCES hotspot_run(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS topic_article_assignment (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    hotspot_run_id BIGINT NOT NULL,
    topic_result_id BIGINT NOT NULL,
    article_id INT NOT NULL,
    content_identity VARCHAR(80) NOT NULL,
    probability FLOAT NOT NULL,
    probabilities JSON NULL,
    is_primary BOOLEAN NOT NULL DEFAULT TRUE,
    warnings JSON NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_topic_assignment_run_topic_article (hotspot_run_id, topic_result_id, article_id),
    INDEX ix_topic_assignment_run_article (hotspot_run_id, article_id),
    CONSTRAINT fk_topic_assignment_run FOREIGN KEY (hotspot_run_id) REFERENCES hotspot_run(id) ON DELETE CASCADE,
    CONSTRAINT fk_topic_assignment_topic FOREIGN KEY (topic_result_id) REFERENCES topic_result(id) ON DELETE CASCADE,
    CONSTRAINT fk_topic_assignment_article FOREIGN KEY (article_id) REFERENCES article(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS event_heat_snapshot (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    hotspot_run_id BIGINT NOT NULL,
    event_id INT NOT NULL,
    calculated_at DATETIME NOT NULL,
    raw_statistics JSON NULL,
    component_scores JSON NULL,
    core_heat FLOAT NOT NULL,
    spread_heat FLOAT NULL,
    final_heat FLOAT NOT NULL,
    eligible_as_hot BOOLEAN NOT NULL DEFAULT FALSE,
    rank INT NULL,
    status_change VARCHAR(20) NULL,
    time_confidence VARCHAR(20) NOT NULL DEFAULT 'low',
    formula_version VARCHAR(30) NOT NULL DEFAULT 'v1',
    calculation_details JSON NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_event_heat_run_event (hotspot_run_id, event_id),
    INDEX ix_event_heat_event_calculated (event_id, calculated_at),
    INDEX ix_event_heat_hot_rank (eligible_as_hot, rank),
    CONSTRAINT fk_event_heat_run FOREIGN KEY (hotspot_run_id) REFERENCES hotspot_run(id) ON DELETE CASCADE,
    CONSTRAINT fk_event_heat_event FOREIGN KEY (event_id) REFERENCES event(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

ALTER TABLE event ADD COLUMN current_heat_snapshot_id BIGINT NULL;
ALTER TABLE event ADD COLUMN core_heat FLOAT NOT NULL DEFAULT 0;
ALTER TABLE event ADD COLUMN spread_heat FLOAT NULL;
ALTER TABLE event ADD COLUMN is_hot BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE event ADD COLUMN hot_rank INT NULL;
ALTER TABLE event ADD COLUMN topic_category VARCHAR(30) NULL;
ALTER TABLE event ADD COLUMN topic_name VARCHAR(100) NULL;
ALTER TABLE event ADD COLUMN first_publish_time DATETIME NULL;
ALTER TABLE event ADD COLUMN last_activity_time DATETIME NULL;
ALTER TABLE event ADD COLUMN independent_report_count INT NOT NULL DEFAULT 0;
ALTER TABLE event ADD COLUMN platform_count INT NOT NULL DEFAULT 0;
ALTER TABLE event ADD COLUMN time_confidence VARCHAR(20) NOT NULL DEFAULT 'low';
ALTER TABLE event ADD CONSTRAINT fk_event_current_heat_snapshot FOREIGN KEY (current_heat_snapshot_id) REFERENCES event_heat_snapshot(id);
