-- ============================================================
-- Alcalay - Google Drive PostgreSQL Schema
-- ============================================================
--
-- Purpose:
--     PostgreSQL registry for Google Drive ingestion.
--
-- PostgreSQL is responsible for:
--     - Drive metadata
--     - folder hierarchy
--     - file state
--     - file versions
--     - duplicate detection
--     - keyword filtering
--     - local copy state
--     - synchronization history
--
-- This schema does NOT download files.
-- This schema does NOT communicate with Google Drive.
--
-- ============================================================


BEGIN;


-- ============================================================
-- 1. DRIVE REPOSITORIES
-- ============================================================

CREATE TABLE IF NOT EXISTS drive_repositories (
    id                  BIGSERIAL PRIMARY KEY,

    repository_key      VARCHAR(100) NOT NULL UNIQUE,

    display_name        VARCHAR(255) NOT NULL,

    root_folder_id      VARCHAR(255) NOT NULL UNIQUE,

    enabled             BOOLEAN NOT NULL DEFAULT TRUE,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- ============================================================
-- 2. DRIVE FOLDERS
-- ============================================================

CREATE TABLE IF NOT EXISTS drive_folders (
    id                  BIGSERIAL PRIMARY KEY,

    repository_id       BIGINT NOT NULL
                        REFERENCES drive_repositories(id)
                        ON DELETE CASCADE,

    drive_file_id       VARCHAR(255) NOT NULL,

    parent_drive_file_id VARCHAR(255),

    name                TEXT NOT NULL,

    mime_type            VARCHAR(255) NOT NULL,

    web_view_link        TEXT,

    created_time         TIMESTAMPTZ,

    modified_time        TIMESTAMPTZ,

    trashed              BOOLEAN NOT NULL DEFAULT FALSE,

    first_seen_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    last_seen_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (
        repository_id,
        drive_file_id
    )
);


CREATE INDEX IF NOT EXISTS idx_drive_folders_parent
    ON drive_folders(parent_drive_file_id);

CREATE INDEX IF NOT EXISTS idx_drive_folders_repository
    ON drive_folders(repository_id);

CREATE INDEX IF NOT EXISTS idx_drive_folders_name
    ON drive_folders(name);


-- ============================================================
-- 3. DRIVE FILES
-- ============================================================

CREATE TABLE IF NOT EXISTS drive_files (
    id                  BIGSERIAL PRIMARY KEY,

    repository_id       BIGINT NOT NULL
                        REFERENCES drive_repositories(id)
                        ON DELETE CASCADE,

    drive_file_id       VARCHAR(255) NOT NULL,

    parent_drive_file_id VARCHAR(255),

    name                TEXT NOT NULL,

    mime_type            VARCHAR(255) NOT NULL,

    size_bytes           BIGINT,

    created_time         TIMESTAMPTZ,

    modified_time        TIMESTAMPTZ,

    md5_checksum         VARCHAR(128),

    web_view_link        TEXT,

    is_trashed           BOOLEAN NOT NULL DEFAULT FALSE,

    is_relevant           BOOLEAN,

    relevance_reason      TEXT,

    keyword_checked_at    TIMESTAMPTZ,

    local_status          VARCHAR(50)
                          NOT NULL DEFAULT 'NOT_DOWNLOADED',

    local_path            TEXT,

    local_checksum        VARCHAR(128),

    local_size_bytes      BIGINT,

    first_seen_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    last_seen_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    last_checked_at       TIMESTAMPTZ,

    last_downloaded_at    TIMESTAMPTZ,

    last_error             TEXT,

    UNIQUE (
        repository_id,
        drive_file_id
    )
);


CREATE INDEX IF NOT EXISTS idx_drive_files_drive_id
    ON drive_files(drive_file_id);

CREATE INDEX IF NOT EXISTS idx_drive_files_parent
    ON drive_files(parent_drive_file_id);

CREATE INDEX IF NOT EXISTS idx_drive_files_modified
    ON drive_files(modified_time);

CREATE INDEX IF NOT EXISTS idx_drive_files_md5
    ON drive_files(md5_checksum);

CREATE INDEX IF NOT EXISTS idx_drive_files_relevant
    ON drive_files(is_relevant);

CREATE INDEX IF NOT EXISTS idx_drive_files_local_status
    ON drive_files(local_status);

CREATE INDEX IF NOT EXISTS idx_drive_files_name
    ON drive_files(name);


-- ============================================================
-- 4. DRIVE FILE VERSIONS
-- ============================================================

CREATE TABLE IF NOT EXISTS drive_file_versions (
    id                  BIGSERIAL PRIMARY KEY,

    drive_file_id_fk    BIGINT NOT NULL
                        REFERENCES drive_files(id)
                        ON DELETE CASCADE,

    version_number      INTEGER NOT NULL,

    drive_modified_time TIMESTAMPTZ,

    size_bytes           BIGINT,

    md5_checksum         VARCHAR(128),

    discovered_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    downloaded           BOOLEAN NOT NULL DEFAULT FALSE,

    local_path           TEXT,

    local_checksum       VARCHAR(128),

    downloaded_at        TIMESTAMPTZ,

    status               VARCHAR(50)
                        NOT NULL DEFAULT 'DISCOVERED',

    error_message        TEXT,

    UNIQUE (
        drive_file_id_fk,
        version_number
    )
);


CREATE INDEX IF NOT EXISTS idx_drive_versions_file
    ON drive_file_versions(drive_file_id_fk);

CREATE INDEX IF NOT EXISTS idx_drive_versions_md5
    ON drive_file_versions(md5_checksum);

CREATE INDEX IF NOT EXISTS idx_drive_versions_modified
    ON drive_file_versions(drive_modified_time);


-- ============================================================
-- 5. DRIVE CONTENT DUPLICATES
-- ============================================================

CREATE TABLE IF NOT EXISTS drive_duplicates (
    id                  BIGSERIAL PRIMARY KEY,

    checksum            VARCHAR(128) NOT NULL,

    checksum_type       VARCHAR(30) NOT NULL DEFAULT 'MD5',

    canonical_drive_file_id
                        BIGINT
                        REFERENCES drive_files(id)
                        ON DELETE SET NULL,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (
        checksum,
        checksum_type
    )
);


CREATE INDEX IF NOT EXISTS idx_drive_duplicates_checksum
    ON drive_duplicates(checksum);


-- ============================================================
-- 6. DRIVE FILE DUPLICATE MEMBERS
-- ============================================================

CREATE TABLE IF NOT EXISTS drive_duplicate_members (
    id                  BIGSERIAL PRIMARY KEY,

    duplicate_group_id  BIGINT NOT NULL
                        REFERENCES drive_duplicates(id)
                        ON DELETE CASCADE,

    drive_file_id_fk    BIGINT NOT NULL
                        REFERENCES drive_files(id)
                        ON DELETE CASCADE,

    detected_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    is_canonical        BOOLEAN NOT NULL DEFAULT FALSE,

    UNIQUE (
        duplicate_group_id,
        drive_file_id_fk
    )
);


CREATE INDEX IF NOT EXISTS idx_drive_duplicate_members_group
    ON drive_duplicate_members(duplicate_group_id);

CREATE INDEX IF NOT EXISTS idx_drive_duplicate_members_file
    ON drive_duplicate_members(drive_file_id_fk);


-- ============================================================
-- 7. KEYWORD RULE SETS
-- ============================================================

CREATE TABLE IF NOT EXISTS drive_keyword_rule_sets (
    id                  BIGSERIAL PRIMARY KEY,

    name                VARCHAR(255) NOT NULL UNIQUE,

    description         TEXT,

    enabled             BOOLEAN NOT NULL DEFAULT TRUE,

    match_mode          VARCHAR(30)
                        NOT NULL DEFAULT 'ANY',

    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- ============================================================
-- 8. KEYWORD RULES
-- ============================================================

CREATE TABLE IF NOT EXISTS drive_keyword_rules (
    id                  BIGSERIAL PRIMARY KEY,

    rule_set_id         BIGINT NOT NULL
                        REFERENCES drive_keyword_rule_sets(id)
                        ON DELETE CASCADE,

    keyword             TEXT NOT NULL,

    enabled             BOOLEAN NOT NULL DEFAULT TRUE,

    case_sensitive      BOOLEAN NOT NULL DEFAULT FALSE,

    search_filename     BOOLEAN NOT NULL DEFAULT TRUE,

    search_description  BOOLEAN NOT NULL DEFAULT TRUE,

    search_path         BOOLEAN NOT NULL DEFAULT TRUE,

    search_metadata     BOOLEAN NOT NULL DEFAULT TRUE,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (
        rule_set_id,
        keyword
    )
);


CREATE INDEX IF NOT EXISTS idx_drive_keyword_rules_set
    ON drive_keyword_rules(rule_set_id);

CREATE INDEX IF NOT EXISTS idx_drive_keyword_rules_keyword
    ON drive_keyword_rules(keyword);


-- ============================================================
-- 9. DRIVE FILE KEYWORD MATCHES
-- ============================================================

CREATE TABLE IF NOT EXISTS drive_file_keyword_matches (
    id                  BIGSERIAL PRIMARY KEY,

    drive_file_id_fk    BIGINT NOT NULL
                        REFERENCES drive_files(id)
                        ON DELETE CASCADE,

    keyword_rule_id     BIGINT NOT NULL
                        REFERENCES drive_keyword_rules(id)
                        ON DELETE CASCADE,

    matched_text        TEXT,

    matched_in          VARCHAR(50),

    matched_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (
        drive_file_id_fk,
        keyword_rule_id
    )
);


CREATE INDEX IF NOT EXISTS idx_drive_keyword_matches_file
    ON drive_file_keyword_matches(drive_file_id_fk);

CREATE INDEX IF NOT EXISTS idx_drive_keyword_matches_rule
    ON drive_file_keyword_matches(keyword_rule_id);


-- ============================================================
-- 10. LOCAL FILE OBJECTS
-- ============================================================

CREATE TABLE IF NOT EXISTS drive_local_files (
    id                  BIGSERIAL PRIMARY KEY,

    drive_file_id_fk    BIGINT NOT NULL
                        REFERENCES drive_files(id)
                        ON DELETE CASCADE,

    drive_file_version_id
                        BIGINT
                        REFERENCES drive_file_versions(id)
                        ON DELETE SET NULL,

    local_path          TEXT NOT NULL,

    file_name           TEXT NOT NULL,

    size_bytes          BIGINT,

    checksum            VARCHAR(128),

    checksum_type       VARCHAR(30)
                        NOT NULL DEFAULT 'MD5',

    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    last_verified_at    TIMESTAMPTZ,

    is_current          BOOLEAN NOT NULL DEFAULT TRUE,

    UNIQUE (
        local_path
    )
);


CREATE INDEX IF NOT EXISTS idx_drive_local_files_drive
    ON drive_local_files(drive_file_id_fk);

CREATE INDEX IF NOT EXISTS idx_drive_local_files_checksum
    ON drive_local_files(checksum);


-- ============================================================
-- 11. DRIVE SYNC RUNS
-- ============================================================

CREATE TABLE IF NOT EXISTS drive_sync_runs (
    id                  BIGSERIAL PRIMARY KEY,

    repository_id       BIGINT NOT NULL
                        REFERENCES drive_repositories(id)
                        ON DELETE CASCADE,

    sync_type           VARCHAR(50) NOT NULL,

    started_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    finished_at         TIMESTAMPTZ,

    status              VARCHAR(50)
                        NOT NULL DEFAULT 'RUNNING',

    scanned_count       INTEGER NOT NULL DEFAULT 0,

    folders_count       INTEGER NOT NULL DEFAULT 0,

    files_count         INTEGER NOT NULL DEFAULT 0,

    relevant_count      INTEGER NOT NULL DEFAULT 0,

    skipped_count       INTEGER NOT NULL DEFAULT 0,

    downloaded_count    INTEGER NOT NULL DEFAULT 0,

    updated_count       INTEGER NOT NULL DEFAULT 0,

    duplicate_count     INTEGER NOT NULL DEFAULT 0,

    error_count         INTEGER NOT NULL DEFAULT 0,

    error_message       TEXT
);


CREATE INDEX IF NOT EXISTS idx_drive_sync_runs_repository
    ON drive_sync_runs(repository_id);

CREATE INDEX IF NOT EXISTS idx_drive_sync_runs_started
    ON drive_sync_runs(started_at);

CREATE INDEX IF NOT EXISTS idx_drive_sync_runs_status
    ON drive_sync_runs(status);


-- ============================================================
-- 12. DRIVE SYNC ITEMS
-- ============================================================

CREATE TABLE IF NOT EXISTS drive_sync_items (
    id                  BIGSERIAL PRIMARY KEY,

    sync_run_id         BIGINT NOT NULL
                        REFERENCES drive_sync_runs(id)
                        ON DELETE CASCADE,

    drive_file_id_fk    BIGINT
                        REFERENCES drive_files(id)
                        ON DELETE SET NULL,

    action              VARCHAR(50) NOT NULL,

    status              VARCHAR(50)
                        NOT NULL DEFAULT 'PENDING',

    reason              TEXT,

    started_at          TIMESTAMPTZ,

    finished_at         TIMESTAMPTZ,

    error_message       TEXT
);


CREATE INDEX IF NOT EXISTS idx_drive_sync_items_run
    ON drive_sync_items(sync_run_id);

CREATE INDEX IF NOT EXISTS idx_drive_sync_items_file
    ON drive_sync_items(drive_file_id_fk);

CREATE INDEX IF NOT EXISTS idx_drive_sync_items_status
    ON drive_sync_items(status);


-- ============================================================
-- 13. TRIGGER FUNCTION FOR updated_at
-- ============================================================

CREATE OR REPLACE FUNCTION drive_set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;


-- ============================================================
-- 14. UPDATED_AT TRIGGERS
-- ============================================================

DROP TRIGGER IF EXISTS trg_drive_repositories_updated_at
ON drive_repositories;

CREATE TRIGGER trg_drive_repositories_updated_at
BEFORE UPDATE ON drive_repositories
FOR EACH ROW
EXECUTE FUNCTION drive_set_updated_at();


DROP TRIGGER IF EXISTS trg_drive_keyword_rule_sets_updated_at
ON drive_keyword_rule_sets;

CREATE TRIGGER trg_drive_keyword_rule_sets_updated_at
BEFORE UPDATE ON drive_keyword_rule_sets
FOR EACH ROW
EXECUTE FUNCTION drive_set_updated_at();


-- ============================================================
-- 15. INITIAL ALCALAY DRIVE REPOSITORY
-- ============================================================

INSERT INTO drive_repositories (
    repository_key,
    display_name,
    root_folder_id,
    enabled
)
VALUES (
    'alcalay',
    'Alcalay Google Drive Repository',
    '1fggwtGyWhfODwZL2LEKBiHhsQ78szBwS',
    TRUE
)
ON CONFLICT (repository_key)
DO UPDATE SET
    display_name = EXCLUDED.display_name,
    root_folder_id = EXCLUDED.root_folder_id,
    enabled = EXCLUDED.enabled;


-- ============================================================
-- 16. DEFAULT KEYWORD RULE SET
-- ============================================================

INSERT INTO drive_keyword_rule_sets (
    name,
    description,
    enabled,
    match_mode
)
VALUES (
    'default',
    'Default Alcalay Google Drive relevance rules',
    TRUE,
    'ANY'
)
ON CONFLICT (name)
DO NOTHING;


COMMIT;
