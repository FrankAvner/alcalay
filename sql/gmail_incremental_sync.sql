BEGIN;

-- ================================================================
-- ALCALAY
-- Gmail Incremental COPY / PARSE / INDEX
--
-- Database upgrade
--
-- IMPORTANT:
-- This script does NOT delete existing Gmail data.
-- It does NOT re-import messages.
-- It does NOT parse messages.
-- It does NOT index messages.
--
-- It only creates the infrastructure required for:
--   1. Incremental Gmail label import
--   2. COPY audit
--   3. Duplicate tracking
--   4. INDEX audit
--   5. Incremental INDEX processing
-- ================================================================


-- ================================================================
-- 1. GMAIL LABELS
--
-- last_history_id already exists in the current database.
-- Add only the incremental-import statistics that are missing.
-- ================================================================

ALTER TABLE gmail_labels
    ADD COLUMN IF NOT EXISTS last_import_started_at TIMESTAMPTZ;

ALTER TABLE gmail_labels
    ADD COLUMN IF NOT EXISTS last_import_completed_at TIMESTAMPTZ;

ALTER TABLE gmail_labels
    ADD COLUMN IF NOT EXISTS last_imported_message_count INTEGER NOT NULL DEFAULT 0;

ALTER TABLE gmail_labels
    ADD COLUMN IF NOT EXISTS last_new_message_count INTEGER NOT NULL DEFAULT 0;

ALTER TABLE gmail_labels
    ADD COLUMN IF NOT EXISTS last_duplicate_message_count INTEGER NOT NULL DEFAULT 0;

ALTER TABLE gmail_labels
    ADD COLUMN IF NOT EXISTS last_failed_message_count INTEGER NOT NULL DEFAULT 0;

ALTER TABLE gmail_labels
    ADD COLUMN IF NOT EXISTS total_import_runs BIGINT NOT NULL DEFAULT 0;

ALTER TABLE gmail_labels
    ADD COLUMN IF NOT EXISTS total_messages_imported BIGINT NOT NULL DEFAULT 0;

ALTER TABLE gmail_labels
    ADD COLUMN IF NOT EXISTS total_duplicate_messages BIGINT NOT NULL DEFAULT 0;

ALTER TABLE gmail_labels
    ADD COLUMN IF NOT EXISTS last_error TEXT;


-- ================================================================
-- 2. GMAIL IMPORT RUNS
--
-- One row = one COPY operation for one Gmail label.
--
-- gmail_label_db_id:
--     Internal Alcalay gmail_labels.id
--
-- gmail_label_id:
--     Real Gmail label ID, e.g. Label_8
-- ================================================================

CREATE TABLE IF NOT EXISTS gmail_import_runs (
    id BIGSERIAL PRIMARY KEY,

    gmail_account_id BIGINT NOT NULL,

    gmail_label_db_id BIGINT,

    gmail_label_id VARCHAR(500),

    label_name VARCHAR(1000),

    started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    completed_at TIMESTAMPTZ,

    status VARCHAR(50) NOT NULL DEFAULT 'RUNNING',

    previous_history_id VARCHAR(500),

    new_history_id VARCHAR(500),

    messages_found INTEGER NOT NULL DEFAULT 0,

    messages_new INTEGER NOT NULL DEFAULT 0,

    messages_already_exists INTEGER NOT NULL DEFAULT 0,

    messages_downloaded INTEGER NOT NULL DEFAULT 0,

    messages_duplicate INTEGER NOT NULL DEFAULT 0,

    messages_failed INTEGER NOT NULL DEFAULT 0,

    messages_skipped INTEGER NOT NULL DEFAULT 0,

    error_message TEXT,

    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);


CREATE INDEX IF NOT EXISTS idx_gmail_import_runs_account
    ON gmail_import_runs(gmail_account_id);

CREATE INDEX IF NOT EXISTS idx_gmail_import_runs_label_db
    ON gmail_import_runs(gmail_label_db_id);

CREATE INDEX IF NOT EXISTS idx_gmail_import_runs_label_gmail
    ON gmail_import_runs(gmail_label_id);

CREATE INDEX IF NOT EXISTS idx_gmail_import_runs_started
    ON gmail_import_runs(started_at);

CREATE INDEX IF NOT EXISTS idx_gmail_import_runs_status
    ON gmail_import_runs(status);


-- ================================================================
-- 3. GMAIL IMPORT EVENTS
--
-- One row = one Gmail message encountered during COPY.
--
-- Possible event_type values:
--
-- DOWNLOADED
-- ALREADY_EXISTS
-- DUPLICATE
-- FAILED
-- SKIPPED
-- ================================================================

CREATE TABLE IF NOT EXISTS gmail_import_events (
    id BIGSERIAL PRIMARY KEY,

    import_run_id BIGINT,

    gmail_account_id BIGINT NOT NULL,

    gmail_label_db_id BIGINT,

    gmail_label_id VARCHAR(500),

    label_name VARCHAR(1000),

    gmail_message_id VARCHAR(1000) NOT NULL,

    gmail_thread_id VARCHAR(1000),

    event_type VARCHAR(50) NOT NULL,

    message_path TEXT,

    message_size BIGINT,

    raw_sha256 VARCHAR(128),

    event_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    error_message TEXT,

    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);


CREATE INDEX IF NOT EXISTS idx_gmail_import_events_run
    ON gmail_import_events(import_run_id);

CREATE INDEX IF NOT EXISTS idx_gmail_import_events_account
    ON gmail_import_events(gmail_account_id);

CREATE INDEX IF NOT EXISTS idx_gmail_import_events_label_db
    ON gmail_import_events(gmail_label_db_id);

CREATE INDEX IF NOT EXISTS idx_gmail_import_events_label_gmail
    ON gmail_import_events(gmail_label_id);

CREATE INDEX IF NOT EXISTS idx_gmail_import_events_message
    ON gmail_import_events(gmail_message_id);

CREATE INDEX IF NOT EXISTS idx_gmail_import_events_type
    ON gmail_import_events(event_type);

CREATE INDEX IF NOT EXISTS idx_gmail_import_events_time
    ON gmail_import_events(event_at);


-- ================================================================
-- 4. GMAIL INDEX RUNS
--
-- One row = one INDEX operation.
-- ================================================================

CREATE TABLE IF NOT EXISTS gmail_index_runs (
    id BIGSERIAL PRIMARY KEY,

    gmail_account_id BIGINT NOT NULL,

    started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    completed_at TIMESTAMPTZ,

    status VARCHAR(50) NOT NULL DEFAULT 'RUNNING',

    messages_found INTEGER NOT NULL DEFAULT 0,

    messages_indexed INTEGER NOT NULL DEFAULT 0,

    messages_already_indexed INTEGER NOT NULL DEFAULT 0,

    messages_updated INTEGER NOT NULL DEFAULT 0,

    messages_failed INTEGER NOT NULL DEFAULT 0,

    messages_skipped INTEGER NOT NULL DEFAULT 0,

    index_version VARCHAR(100),

    error_message TEXT,

    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);


CREATE INDEX IF NOT EXISTS idx_gmail_index_runs_account
    ON gmail_index_runs(gmail_account_id);

CREATE INDEX IF NOT EXISTS idx_gmail_index_runs_started
    ON gmail_index_runs(started_at);

CREATE INDEX IF NOT EXISTS idx_gmail_index_runs_status
    ON gmail_index_runs(status);


-- ================================================================
-- 5. GMAIL INDEX EVENTS
--
-- One row = one message encountered during INDEX.
--
-- Possible event_type values:
--
-- INDEXED
-- ALREADY_INDEXED
-- UPDATED
-- FAILED
-- SKIPPED
-- ================================================================

CREATE TABLE IF NOT EXISTS gmail_index_events (
    id BIGSERIAL PRIMARY KEY,

    index_run_id BIGINT,

    gmail_account_id BIGINT NOT NULL,

    gmail_message_id VARCHAR(1000) NOT NULL,

    gmail_message_key VARCHAR(1000),

    event_type VARCHAR(50) NOT NULL,

    index_version VARCHAR(100),

    indexed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    error_message TEXT,

    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);


CREATE INDEX IF NOT EXISTS idx_gmail_index_events_run
    ON gmail_index_events(index_run_id);

CREATE INDEX IF NOT EXISTS idx_gmail_index_events_account
    ON gmail_index_events(gmail_account_id);

CREATE INDEX IF NOT EXISTS idx_gmail_index_events_message
    ON gmail_index_events(gmail_message_id);

CREATE INDEX IF NOT EXISTS idx_gmail_index_events_type
    ON gmail_index_events(event_type);

CREATE INDEX IF NOT EXISTS idx_gmail_index_events_time
    ON gmail_index_events(indexed_at);


-- ================================================================
-- 6. EXISTING GMAIL MESSAGE INDEX
--
-- The database already has a UNIQUE constraint on:
--
--     (gmail_account_id, message_id)
--
-- We keep that protection.
--
-- This additional index is not strictly necessary because the
-- UNIQUE constraint already provides an index, so we deliberately
-- do not create another duplicate index here.
-- ================================================================


-- ================================================================
-- 7. MESSAGE/LABEL RELATION INDEX
--
-- Existing table:
--
-- gmail_message_labels
--     message_id
--     label_id
--
-- These are internal PostgreSQL IDs.
-- ================================================================

CREATE INDEX IF NOT EXISTS idx_gmail_message_labels_label_message
    ON gmail_message_labels(label_id, message_id);


-- ================================================================
-- 8. VIEW: DUPLICATE IMPORTS
--
-- Shows messages which were encountered during COPY but were
-- already present locally.
-- ================================================================

CREATE OR REPLACE VIEW gmail_duplicate_imports AS
SELECT
    e.id,
    e.import_run_id,
    e.gmail_account_id,
    e.gmail_label_db_id,
    e.gmail_label_id,
    e.label_name,
    e.gmail_message_id,
    e.gmail_thread_id,
    e.event_type,
    e.message_path,
    e.message_size,
    e.raw_sha256,
    e.event_at,
    e.error_message,
    e.metadata
FROM gmail_import_events e
WHERE e.event_type IN (
    'ALREADY_EXISTS',
    'DUPLICATE'
);


-- ================================================================
-- 9. VIEW: INDEX HISTORY
--
-- Complete history of INDEX operations.
-- ================================================================

CREATE OR REPLACE VIEW gmail_index_history AS
SELECT
    e.id,
    e.index_run_id,
    e.gmail_account_id,
    e.gmail_message_id,
    e.gmail_message_key,
    e.event_type,
    e.index_version,
    e.indexed_at,
    e.error_message,
    e.metadata
FROM gmail_index_events e;


-- ================================================================
-- 10. VIEW: MESSAGES PENDING INDEX
--
-- Parsed messages that do not yet have a row in the search index.
--
-- This allows the INDEX process to work incrementally.
-- ================================================================

CREATE OR REPLACE VIEW gmail_messages_pending_index AS
SELECT
    p.id AS parsed_id,
    p.gmail_message_id,
    p.gmail_message_key,
    p.subject,
    p.sender_email,
    p.date_sent,
    p.parser_version
FROM gmail_parsed_messages p
LEFT JOIN gmail_search_index i
    ON i.gmail_message_id = p.gmail_message_id
WHERE i.id IS NULL;


-- ================================================================
-- 11. VIEW: SELECTED GMAIL LABELS
--
-- Convenient view for the COPY process.
-- Only selected AND enabled labels are eligible for import.
-- ================================================================

CREATE OR REPLACE VIEW gmail_selected_labels AS
SELECT
    l.id AS gmail_label_db_id,
    l.gmail_account_id,
    l.label_id AS gmail_label_id,
    l.label_name,
    l.label_type,
    l.selected_for_sync,
    l.enabled,
    l.last_history_id,
    l.last_import_started_at,
    l.last_import_completed_at,
    l.last_imported_message_count,
    l.last_new_message_count,
    l.last_duplicate_message_count,
    l.last_failed_message_count,
    l.total_import_runs,
    l.total_messages_imported,
    l.total_duplicate_messages,
    l.last_error
FROM gmail_labels l
WHERE l.selected_for_sync = TRUE
  AND l.enabled = TRUE;


-- ================================================================
-- 12. VIEW: IMPORT RUN SUMMARY
--
-- Useful for the future GUI.
-- ================================================================

CREATE OR REPLACE VIEW gmail_import_run_summary AS
SELECT
    r.id,
    r.gmail_account_id,
    r.gmail_label_db_id,
    r.gmail_label_id,
    r.label_name,
    r.started_at,
    r.completed_at,
    r.status,
    r.previous_history_id,
    r.new_history_id,
    r.messages_found,
    r.messages_new,
    r.messages_already_exists,
    r.messages_downloaded,
    r.messages_duplicate,
    r.messages_failed,
    r.messages_skipped,
    r.error_message
FROM gmail_import_runs r;


-- ================================================================
-- 13. VIEW: INDEX RUN SUMMARY
-- ================================================================

CREATE OR REPLACE VIEW gmail_index_run_summary AS
SELECT
    r.id,
    r.gmail_account_id,
    r.started_at,
    r.completed_at,
    r.status,
    r.messages_found,
    r.messages_indexed,
    r.messages_already_indexed,
    r.messages_updated,
    r.messages_failed,
    r.messages_skipped,
    r.index_version,
    r.error_message
FROM gmail_index_runs r;


COMMIT;
