-- VSQL_4_VISUAL_DUAL_WRITE_PARITY_v1
-- Durable migration-readiness evidence for visual SQLite -> PostgreSQL transition.
-- SQLite remains the active presentation replay owner at this stage.
-- PostgreSQL shadow failures MUST NOT mutate gameplay, Canon, RNG, checkpoint,
-- AEL, PKP, Recovery, Gates, or the already committed SQLite display record.

BEGIN;

CREATE TABLE IF NOT EXISTS dnd_visual.visual_sql_parity_run (
    parity_run_id text PRIMARY KEY,
    session_id text NOT NULL,
    source_revision text NOT NULL,
    display_ledger_owner_id text NOT NULL,
    display_store_id text NOT NULL,
    display_namespace text NOT NULL,
    sqlite_snapshot_digest_sha256 text NOT NULL
        CHECK (sqlite_snapshot_digest_sha256 ~ '^[0-9a-f]{64}$'),
    sql_projection_digest_sha256 text NOT NULL
        CHECK (sql_projection_digest_sha256 ~ '^[0-9a-f]{64}$'),
    sqlite_display_count integer NOT NULL CHECK (sqlite_display_count >= 0),
    sql_display_count integer NOT NULL CHECK (sql_display_count >= 0),
    parity_status text NOT NULL
        CHECK (parity_status IN ('PASS','NOT_READY','FAIL')),
    findings_count integer NOT NULL DEFAULT 0 CHECK (findings_count >= 0),
    findings_digest_sha256 text NOT NULL
        CHECK (findings_digest_sha256 ~ '^[0-9a-f]{64}$'),
    source_commit_sha text NOT NULL
        CHECK (source_commit_sha ~ '^[0-9a-f]{40}$'),
    validator_version text NOT NULL,
    exposure_class text NOT NULL DEFAULT 'SECURITY_INTERNAL'
        CHECK (exposure_class = 'SECURITY_INTERNAL'),
    semantic_authority boolean NOT NULL DEFAULT false
        CHECK (semantic_authority = false),
    checked_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (
        session_id,
        source_revision,
        display_ledger_owner_id,
        display_store_id,
        display_namespace,
        sqlite_snapshot_digest_sha256,
        sql_projection_digest_sha256
    )
);

CREATE INDEX IF NOT EXISTS visual_sql_parity_status_idx
    ON dnd_visual.visual_sql_parity_run (parity_status, checked_at DESC);
CREATE INDEX IF NOT EXISTS visual_sql_parity_lineage_idx
    ON dnd_visual.visual_sql_parity_run (
        display_ledger_owner_id,
        display_store_id,
        display_namespace,
        source_revision,
        checked_at DESC
    );

COMMENT ON TABLE dnd_visual.visual_sql_parity_run IS
'Migration-readiness evidence only. PASS here does not promote Runtime, make PostgreSQL Canon, or transfer verification-root authority.';

COMMIT;
