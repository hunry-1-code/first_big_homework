ALTER TABLE event
    ADD COLUMN IF NOT EXISTS lifecycle_status VARCHAR(24) NOT NULL DEFAULT 'data_insufficient';
ALTER TABLE event
    ADD COLUMN IF NOT EXISTS lifecycle_confidence DOUBLE NOT NULL DEFAULT 0;
ALTER TABLE event
    ADD COLUMN IF NOT EXISTS lifecycle_evidence JSON NULL;
ALTER TABLE event
    ADD COLUMN IF NOT EXISTS lifecycle_updated_at DATETIME NULL;

UPDATE event
SET lifecycle_status = COALESCE(lifecycle_status, 'data_insufficient'),
    lifecycle_confidence = COALESCE(lifecycle_confidence, 0)
WHERE lifecycle_status IS NULL OR lifecycle_confidence IS NULL;
