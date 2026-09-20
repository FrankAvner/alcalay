BEGIN;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version VARCHAR(100) PRIMARY KEY,
    description TEXT NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS source_types (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO source_types (code, name, description)
VALUES
    ('LOCAL', 'Local Folder', 'Local filesystem source'),
    ('GMAIL', 'Gmail', 'Gmail account and selected labels'),
    ('GOOGLE_DRIVE', 'Google Drive', 'Google Drive source')
ON CONFLICT (code) DO NOTHING;


CREATE TABLE IF NOT EXISTS sources (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_type_id BIGINT NOT NULL REFERENCES source_types(id),
    name VARCHAR(255) NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    description TEXT,
    configuration JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_sources_type
    ON sources(source_type_id);

CREATE INDEX IF NOT EXISTS idx_sources_enabled
    ON sources(enabled);


CREATE TABLE IF NOT EXISTS source_accounts (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_id BIGINT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    external_account_id VARCHAR(500),
    account_name VARCHAR(255),
    account_email VARCHAR(320),
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_source_accounts_source
    ON source_accounts(source_id);

CREATE INDEX IF NOT EXISTS idx_source_accounts_email
    ON source_accounts(account_email);


CREATE TABLE IF NOT EXISTS source_locations (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_id BIGINT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    account_id BIGINT REFERENCES source_accounts(id) ON DELETE CASCADE,
    parent_location_id BIGINT REFERENCES source_locations(id) ON DELETE CASCADE,

    external_id VARCHAR(1000),
    name VARCHAR(1000) NOT NULL,
    location_type VARCHAR(100) NOT NULL,

    local_path TEXT,
    selected_for_sync BOOLEAN NOT NULL DEFAULT TRUE,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,

    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_source_locations_source
    ON source_locations(source_id);

CREATE INDEX IF NOT EXISTS idx_source_locations_account
    ON source_locations(account_id);

CREATE INDEX IF NOT EXISTS idx_source_locations_parent
    ON source_locations(parent_location_id);

CREATE INDEX IF NOT EXISTS idx_source_locations_external
    ON source_locations(external_id);

CREATE INDEX IF NOT EXISTS idx_source_locations_selected
    ON source_locations(selected_for_sync);


CREATE TABLE IF NOT EXISTS documents (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    title TEXT NOT NULL,
    file_name TEXT,

    mime_type VARCHAR(255),
    file_extension VARCHAR(50),

    file_size BIGINT,
    content_hash VARCHAR(128),

    document_date TIMESTAMPTZ,
    created_at_source TIMESTAMPTZ,
    modified_at_source TIMESTAMPTZ,

    author TEXT,
    sender TEXT,
    recipients TEXT,

    subject TEXT,

    status VARCHAR(50) NOT NULL DEFAULT 'ACTIVE',

    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_documents_file_size
        CHECK (file_size IS NULL OR file_size >= 0),

    CONSTRAINT chk_documents_status
        CHECK (status IN ('ACTIVE', 'ARCHIVED', 'DELETED', 'ERROR'))
);

CREATE INDEX IF NOT EXISTS idx_documents_title
    ON documents(title);

CREATE INDEX IF NOT EXISTS idx_documents_mime_type
    ON documents(mime_type);

CREATE INDEX IF NOT EXISTS idx_documents_document_date
    ON documents(document_date);

CREATE INDEX IF NOT EXISTS idx_documents_modified_source
    ON documents(modified_at_source);

CREATE INDEX IF NOT EXISTS idx_documents_content_hash
    ON documents(content_hash);

CREATE INDEX IF NOT EXISTS idx_documents_status
    ON documents(status);


CREATE TABLE IF NOT EXISTS document_sources (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    document_id BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    source_id BIGINT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    source_location_id BIGINT REFERENCES source_locations(id) ON DELETE SET NULL,
    source_account_id BIGINT REFERENCES source_accounts(id) ON DELETE SET NULL,

    source_item_id VARCHAR(2000),
    source_path TEXT,

    source_name TEXT,
    source_hash VARCHAR(128),

    source_created_at TIMESTAMPTZ,
    source_modified_at TIMESTAMPTZ,

    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TIMESTAMPTZ,
    last_synced_at TIMESTAMPTZ,

    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,

    UNIQUE(source_id, source_item_id)
);

CREATE INDEX IF NOT EXISTS idx_document_sources_document
    ON document_sources(document_id);

CREATE INDEX IF NOT EXISTS idx_document_sources_source
    ON document_sources(source_id);

CREATE INDEX IF NOT EXISTS idx_document_sources_location
    ON document_sources(source_location_id);

CREATE INDEX IF NOT EXISTS idx_document_sources_hash
    ON document_sources(source_hash);


CREATE TABLE IF NOT EXISTS document_versions (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    document_id BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,

    version_number INTEGER NOT NULL,
    content_hash VARCHAR(128),

    file_size BIGINT,
    mime_type VARCHAR(255),

    source_id BIGINT REFERENCES sources(id) ON DELETE SET NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,

    UNIQUE(document_id, version_number),

    CONSTRAINT chk_document_versions_number
        CHECK (version_number > 0)
);

CREATE INDEX IF NOT EXISTS idx_document_versions_document
    ON document_versions(document_id);

CREATE INDEX IF NOT EXISTS idx_document_versions_hash
    ON document_versions(content_hash);


CREATE TABLE IF NOT EXISTS document_content (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    document_id BIGINT NOT NULL UNIQUE REFERENCES documents(id) ON DELETE CASCADE,

    extracted_text TEXT,
    ocr_text TEXT,

    extraction_status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
    ocr_status VARCHAR(50) NOT NULL DEFAULT 'NOT_PROCESSED',

    content_hash VARCHAR(128),

    extracted_at TIMESTAMPTZ,
    ocr_processed_at TIMESTAMPTZ,

    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_extraction_status
        CHECK (extraction_status IN (
            'PENDING',
            'PROCESSING',
            'COMPLETED',
            'ERROR',
            'NOT_SUPPORTED'
        )),

    CONSTRAINT chk_ocr_status
        CHECK (ocr_status IN (
            'NOT_PROCESSED',
            'PROCESSING',
            'COMPLETED',
            'ERROR',
            'NOT_SUPPORTED'
        ))
);


CREATE TABLE IF NOT EXISTS local_files (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    document_id BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,

    source_location_id BIGINT REFERENCES source_locations(id) ON DELETE SET NULL,

    local_path TEXT NOT NULL,

    file_name TEXT,
    file_size BIGINT,
    content_hash VARCHAR(128),

    exists_locally BOOLEAN NOT NULL DEFAULT TRUE,

    first_downloaded_at TIMESTAMPTZ,
    last_verified_at TIMESTAMPTZ,

    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(local_path)
);

CREATE INDEX IF NOT EXISTS idx_local_files_document
    ON local_files(document_id);

CREATE INDEX IF NOT EXISTS idx_local_files_hash
    ON local_files(content_hash);

CREATE INDEX IF NOT EXISTS idx_local_files_exists
    ON local_files(exists_locally);


CREATE TABLE IF NOT EXISTS gmail_accounts (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    source_account_id BIGINT NOT NULL UNIQUE
        REFERENCES source_accounts(id) ON DELETE CASCADE,

    email VARCHAR(320) NOT NULL UNIQUE,

    history_id VARCHAR(500),

    enabled BOOLEAN NOT NULL DEFAULT TRUE,

    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);


CREATE TABLE IF NOT EXISTS gmail_labels (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    gmail_account_id BIGINT NOT NULL
        REFERENCES gmail_accounts(id) ON DELETE CASCADE,

    label_id VARCHAR(500) NOT NULL,
    label_name VARCHAR(1000) NOT NULL,

    label_type VARCHAR(100),

    selected_for_sync BOOLEAN NOT NULL DEFAULT FALSE,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,

    last_history_id VARCHAR(500),

    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(gmail_account_id, label_id)
);

CREATE INDEX IF NOT EXISTS idx_gmail_labels_account
    ON gmail_labels(gmail_account_id);

CREATE INDEX IF NOT EXISTS idx_gmail_labels_selected
    ON gmail_labels(selected_for_sync);


CREATE TABLE IF NOT EXISTS gmail_messages (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    gmail_account_id BIGINT NOT NULL
        REFERENCES gmail_accounts(id) ON DELETE CASCADE,

    document_id BIGINT REFERENCES documents(id) ON DELETE SET NULL,

    message_id VARCHAR(1000) NOT NULL,
    thread_id VARCHAR(1000),
    history_id VARCHAR(500),

    internal_date TIMESTAMPTZ,

    sender TEXT,
    recipients TEXT,
    cc TEXT,
    bcc TEXT,

    subject TEXT,
    snippet TEXT,

    body_text TEXT,

    received_at TIMESTAMPTZ,

    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(gmail_account_id, message_id)
);

CREATE INDEX IF NOT EXISTS idx_gmail_messages_account
    ON gmail_messages(gmail_account_id);

CREATE INDEX IF NOT EXISTS idx_gmail_messages_document
    ON gmail_messages(document_id);

CREATE INDEX IF NOT EXISTS idx_gmail_messages_thread
    ON gmail_messages(thread_id);

CREATE INDEX IF NOT EXISTS idx_gmail_messages_date
    ON gmail_messages(internal_date);

CREATE INDEX IF NOT EXISTS idx_gmail_messages_subject
    ON gmail_messages(subject);


CREATE TABLE IF NOT EXISTS gmail_message_labels (
    message_id BIGINT NOT NULL
        REFERENCES gmail_messages(id) ON DELETE CASCADE,

    label_id BIGINT NOT NULL
        REFERENCES gmail_labels(id) ON DELETE CASCADE,

    PRIMARY KEY(message_id, label_id)
);


CREATE TABLE IF NOT EXISTS gmail_attachments (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    gmail_message_id BIGINT NOT NULL
        REFERENCES gmail_messages(id) ON DELETE CASCADE,

    document_id BIGINT REFERENCES documents(id) ON DELETE SET NULL,

    attachment_id VARCHAR(1000),
    file_name TEXT NOT NULL,

    mime_type VARCHAR(255),
    file_size BIGINT,

    content_hash VARCHAR(128),

    local_file_id BIGINT
        REFERENCES local_files(id) ON DELETE SET NULL,

    saved_to_local BOOLEAN NOT NULL DEFAULT FALSE,

    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(gmail_message_id, attachment_id)
);

CREATE INDEX IF NOT EXISTS idx_gmail_attachments_message
    ON gmail_attachments(gmail_message_id);

CREATE INDEX IF NOT EXISTS idx_gmail_attachments_document
    ON gmail_attachments(document_id);

CREATE INDEX IF NOT EXISTS idx_gmail_attachments_hash
    ON gmail_attachments(content_hash);


CREATE TABLE IF NOT EXISTS drive_files (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    document_id BIGINT NOT NULL UNIQUE
        REFERENCES documents(id) ON DELETE CASCADE,

    drive_file_id VARCHAR(1000) NOT NULL UNIQUE,
    drive_parent_id VARCHAR(1000),

    name TEXT NOT NULL,
    mime_type VARCHAR(255),

    drive_size BIGINT,
    drive_md5_checksum VARCHAR(128),

    drive_created_time TIMESTAMPTZ,
    drive_modified_time TIMESTAMPTZ,

    web_url TEXT,

    trashed BOOLEAN NOT NULL DEFAULT FALSE,

    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_drive_files_parent
    ON drive_files(drive_parent_id);

CREATE INDEX IF NOT EXISTS idx_drive_files_checksum
    ON drive_files(drive_md5_checksum);

CREATE INDEX IF NOT EXISTS idx_drive_files_modified
    ON drive_files(drive_modified_time);


CREATE TABLE IF NOT EXISTS sync_states (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    source_id BIGINT NOT NULL
        REFERENCES sources(id) ON DELETE CASCADE,

    source_location_id BIGINT
        REFERENCES source_locations(id) ON DELETE CASCADE,

    source_account_id BIGINT
        REFERENCES source_accounts(id) ON DELETE CASCADE,

    status VARCHAR(50) NOT NULL DEFAULT 'NEVER_RUN',

    last_sync_started_at TIMESTAMPTZ,
    last_sync_completed_at TIMESTAMPTZ,
    last_success_at TIMESTAMPTZ,

    last_fetched_at TIMESTAMPTZ,
    last_saved_at TIMESTAMPTZ,
    last_change_at TIMESTAMPTZ,

    history_id VARCHAR(1000),
    cursor_token TEXT,

    items_checked BIGINT NOT NULL DEFAULT 0,
    items_added BIGINT NOT NULL DEFAULT 0,
    items_already_exists BIGINT NOT NULL DEFAULT 0,
    items_skipped BIGINT NOT NULL DEFAULT 0,
    items_failed BIGINT NOT NULL DEFAULT 0,

    last_error TEXT,

    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(source_id, source_location_id, source_account_id),

    CONSTRAINT chk_sync_state_status
        CHECK (status IN (
            'NEVER_RUN',
            'RUNNING',
            'SUCCESS',
            'PARTIAL',
            'FAILED'
        ))
);

CREATE INDEX IF NOT EXISTS idx_sync_states_source
    ON sync_states(source_id);

CREATE INDEX IF NOT EXISTS idx_sync_states_location
    ON sync_states(source_location_id);

CREATE INDEX IF NOT EXISTS idx_sync_states_status
    ON sync_states(status);


CREATE TABLE IF NOT EXISTS sync_runs (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    source_id BIGINT NOT NULL
        REFERENCES sources(id) ON DELETE RESTRICT,

    source_location_id BIGINT
        REFERENCES source_locations(id) ON DELETE SET NULL,

    source_account_id BIGINT
        REFERENCES source_accounts(id) ON DELETE SET NULL,

    mode VARCHAR(50) NOT NULL DEFAULT 'INCREMENTAL',

    status VARCHAR(50) NOT NULL DEFAULT 'RUNNING',

    started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ,

    items_checked BIGINT NOT NULL DEFAULT 0,
    items_added BIGINT NOT NULL DEFAULT 0,
    items_already_exists BIGINT NOT NULL DEFAULT 0,
    items_skipped BIGINT NOT NULL DEFAULT 0,
    items_failed BIGINT NOT NULL DEFAULT 0,

    error_message TEXT,

    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,

    CONSTRAINT chk_sync_run_mode
        CHECK (mode IN (
            'INCREMENTAL',
            'FULL',
            'MANUAL'
        )),

    CONSTRAINT chk_sync_run_status
        CHECK (status IN (
            'RUNNING',
            'SUCCESS',
            'PARTIAL',
            'FAILED',
            'CANCELLED'
        ))
);

CREATE INDEX IF NOT EXISTS idx_sync_runs_source
    ON sync_runs(source_id);

CREATE INDEX IF NOT EXISTS idx_sync_runs_started
    ON sync_runs(started_at);

CREATE INDEX IF NOT EXISTS idx_sync_runs_status
    ON sync_runs(status);


CREATE TABLE IF NOT EXISTS sync_run_items (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    sync_run_id BIGINT NOT NULL
        REFERENCES sync_runs(id) ON DELETE CASCADE,

    document_id BIGINT
        REFERENCES documents(id) ON DELETE SET NULL,

    source_item_id VARCHAR(2000),

    action VARCHAR(50) NOT NULL,

    processed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    error_message TEXT,

    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,

    CONSTRAINT chk_sync_run_item_action
        CHECK (action IN (
            'ADDED',
            'ALREADY_EXISTS',
            'SKIPPED',
            'ERROR'
        ))
);

CREATE INDEX IF NOT EXISTS idx_sync_run_items_run
    ON sync_run_items(sync_run_id);

CREATE INDEX IF NOT EXISTS idx_sync_run_items_document
    ON sync_run_items(document_id);

CREATE INDEX IF NOT EXISTS idx_sync_run_items_action
    ON sync_run_items(action);


CREATE TABLE IF NOT EXISTS sync_errors (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    sync_run_id BIGINT
        REFERENCES sync_runs(id) ON DELETE CASCADE,

    source_id BIGINT
        REFERENCES sources(id) ON DELETE SET NULL,

    source_item_id VARCHAR(2000),

    error_type VARCHAR(255),
    error_message TEXT NOT NULL,

    retry_count INTEGER NOT NULL DEFAULT 0,
    resolved BOOLEAN NOT NULL DEFAULT FALSE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMPTZ,

    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_sync_errors_run
    ON sync_errors(sync_run_id);

CREATE INDEX IF NOT EXISTS idx_sync_errors_source
    ON sync_errors(source_id);

CREATE INDEX IF NOT EXISTS idx_sync_errors_resolved
    ON sync_errors(resolved);


CREATE TABLE IF NOT EXISTS search_index (
    document_id BIGINT PRIMARY KEY
        REFERENCES documents(id) ON DELETE CASCADE,

    search_text TEXT,

    search_vector TSVECTOR,

    indexed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_search_index_vector
    ON search_index USING GIN(search_vector);


CREATE TABLE IF NOT EXISTS dictionary_terms (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    term TEXT NOT NULL,
    normalized_term TEXT NOT NULL,

    language VARCHAR(20),

    category VARCHAR(100),

    enabled BOOLEAN NOT NULL DEFAULT TRUE,

    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(normalized_term, language)
);

CREATE INDEX IF NOT EXISTS idx_dictionary_terms_normalized
    ON dictionary_terms(normalized_term);

CREATE INDEX IF NOT EXISTS idx_dictionary_terms_category
    ON dictionary_terms(category);


CREATE TABLE IF NOT EXISTS dictionary_relations (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    term_id BIGINT NOT NULL
        REFERENCES dictionary_terms(id) ON DELETE CASCADE,

    related_term_id BIGINT NOT NULL
        REFERENCES dictionary_terms(id) ON DELETE CASCADE,

    relation_type VARCHAR(100) NOT NULL,

    UNIQUE(term_id, related_term_id, relation_type),

    CONSTRAINT chk_dictionary_relation_self
        CHECK (term_id <> related_term_id)
);

CREATE INDEX IF NOT EXISTS idx_dictionary_relations_term
    ON dictionary_relations(term_id);

CREATE INDEX IF NOT EXISTS idx_dictionary_relations_related
    ON dictionary_relations(related_term_id);


CREATE TABLE IF NOT EXISTS local_replica (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    name VARCHAR(255) NOT NULL,

    root_path TEXT NOT NULL,

    enabled BOOLEAN NOT NULL DEFAULT TRUE,

    last_sync_started_at TIMESTAMPTZ,
    last_sync_completed_at TIMESTAMPTZ,
    last_success_at TIMESTAMPTZ,

    status VARCHAR(50) NOT NULL DEFAULT 'NOT_INITIALIZED',

    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_local_replica_status
        CHECK (status IN (
            'NOT_INITIALIZED',
            'SYNCING',
            'READY',
            'PARTIAL',
            'ERROR'
        ))
);


CREATE TABLE IF NOT EXISTS local_replica_items (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    replica_id BIGINT NOT NULL
        REFERENCES local_replica(id) ON DELETE CASCADE,

    document_id BIGINT NOT NULL
        REFERENCES documents(id) ON DELETE CASCADE,

    local_path TEXT NOT NULL,

    drive_file_id VARCHAR(1000),

    drive_hash VARCHAR(128),
    local_hash VARCHAR(128),

    downloaded_at TIMESTAMPTZ,
    last_verified_at TIMESTAMPTZ,

    status VARCHAR(50) NOT NULL DEFAULT 'PENDING',

    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,

    UNIQUE(replica_id, document_id),

    CONSTRAINT chk_replica_item_status
        CHECK (status IN (
            'PENDING',
            'DOWNLOADED',
            'VERIFIED',
            'MISSING',
            'ERROR'
        ))
);

CREATE INDEX IF NOT EXISTS idx_replica_items_replica
    ON local_replica_items(replica_id);

CREATE INDEX IF NOT EXISTS idx_replica_items_document
    ON local_replica_items(document_id);

CREATE INDEX IF NOT EXISTS idx_replica_items_drive
    ON local_replica_items(drive_file_id);


CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


DROP TRIGGER IF EXISTS trg_sources_updated_at ON sources;
CREATE TRIGGER trg_sources_updated_at
BEFORE UPDATE ON sources
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();


DROP TRIGGER IF EXISTS trg_source_accounts_updated_at ON source_accounts;
CREATE TRIGGER trg_source_accounts_updated_at
BEFORE UPDATE ON source_accounts
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();


DROP TRIGGER IF EXISTS trg_source_locations_updated_at ON source_locations;
CREATE TRIGGER trg_source_locations_updated_at
BEFORE UPDATE ON source_locations
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();


DROP TRIGGER IF EXISTS trg_documents_updated_at ON documents;
CREATE TRIGGER trg_documents_updated_at
BEFORE UPDATE ON documents
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();


DROP TRIGGER IF EXISTS trg_document_content_updated_at ON document_content;
CREATE TRIGGER trg_document_content_updated_at
BEFORE UPDATE ON document_content
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();


DROP TRIGGER IF EXISTS trg_local_files_updated_at ON local_files;
CREATE TRIGGER trg_local_files_updated_at
BEFORE UPDATE ON local_files
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();


DROP TRIGGER IF EXISTS trg_gmail_accounts_updated_at ON gmail_accounts;
CREATE TRIGGER trg_gmail_accounts_updated_at
BEFORE UPDATE ON gmail_accounts
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();


DROP TRIGGER IF EXISTS trg_gmail_labels_updated_at ON gmail_labels;
CREATE TRIGGER trg_gmail_labels_updated_at
BEFORE UPDATE ON gmail_labels
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();


DROP TRIGGER IF EXISTS trg_gmail_messages_updated_at ON gmail_messages;
CREATE TRIGGER trg_gmail_messages_updated_at
BEFORE UPDATE ON gmail_messages
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();


DROP TRIGGER IF EXISTS trg_drive_files_updated_at ON drive_files;
CREATE TRIGGER trg_drive_files_updated_at
BEFORE UPDATE ON drive_files
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();


DROP TRIGGER IF EXISTS trg_sync_states_updated_at ON sync_states;
CREATE TRIGGER trg_sync_states_updated_at
BEFORE UPDATE ON sync_states
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();


DROP TRIGGER IF EXISTS trg_local_replica_updated_at ON local_replica;
CREATE TRIGGER trg_local_replica_updated_at
BEFORE UPDATE ON local_replica
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();


INSERT INTO schema_migrations (
    version,
    description
)
VALUES (
    '001',
    'Initial Alcalay local database schema'
)
ON CONFLICT (version) DO NOTHING;

COMMIT;
