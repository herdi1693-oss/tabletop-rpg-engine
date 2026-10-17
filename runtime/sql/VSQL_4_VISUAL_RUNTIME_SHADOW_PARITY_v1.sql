-- VSQL_4_VISUAL_RUNTIME_SHADOW_PARITY_v1
-- MODE=DUAL_WRITE_PARITY_CANDIDATE
-- TARGET_RELEASE=v1.3.8
-- ACTIVE_RUNTIME_BASELINE=DND_ENGINE_RUNTIME_MF_v1.3.7_VISUAL_EXECUTION_HARDENING
-- PROMOTION_AUTHORIZATION=NO
-- MERGE_AUTHORIZATION=NO_UNTIL_NEW_EXACT_HEAD_QA_PASS
-- GOVERNING_DIRECTIVE=docs/SQL_FIRST_RUNTIME_MIGRATION_HANDOFF_2026-10-14.md
-- LOCAL_CONTRACT=docs/visual/VISUAL_RUNTIME_SQL_MIGRATION_v1.md
--
-- VSQL-4 does NOT cut over presentation authority to PostgreSQL.
-- SQLite remains the current display/replay owner while SQL receives shadow
-- state and deterministic parity receipts. Any mismatch means NOT_READY.
-- No mismatch is allowed to mutate gameplay, Canon, RNG, checkpoint, AEL,
-- knowledge, Recovery, Gates, or active Runtime state.

BEGIN;

-- Exact parity requires retaining the canonical SQLite display receipt identity
-- and digest, not only selected columns.
ALTER TABLE dnd_visual.display_commit
    ADD COLUMN IF NOT EXISTS display_receipt_id text,
    ADD COLUMN IF NOT EXISTS display_record_digest_sha256 text
        CHECK (
            display_record_digest_sha256 IS NULL
            OR display_record_digest_sha256 ~ '^[0-9a-f]{64}$'
        );

CREATE UNIQUE INDEX IF NOT EXISTS display_commit_receipt_id_uq
    ON dnd_visual.display_commit (display_receipt_id)
    WHERE display_receipt_id IS NOT NULL;

-- SQLite supports zero-to-many tactical receipts per display commit. Keep the
-- SQL representation normalized so parity is exact and does not collapse a
-- list into one nullable field.
CREATE TABLE IF NOT EXISTS dnd_visual.display_commit_tactical_receipt (
    display_commit_id text NOT NULL
        REFERENCES dnd_visual.display_commit(display_commit_id) ON DELETE RESTRICT,
    receipt_id text NOT NULL,
    receipt_ordinal integer NOT NULL CHECK (receipt_ordinal >= 0),
    exposure_class text NOT NULL DEFAULT 'PLAYER_SAFE_DISPLAY_METADATA'
        CHECK (exposure_class = 'PLAYER_SAFE_DISPLAY_METADATA'),
    semantic_authority boolean NOT NULL DEFAULT false
        CHECK (semantic_authority = false),
    PRIMARY KEY (display_commit_id, receipt_id),
    UNIQUE (display_commit_id, receipt_ordinal)
);

COMMENT ON TABLE dnd_visual.display_commit_tactical_receipt IS
'Normalized shadow copy of tactical receipt ordering for SQLite/PostgreSQL display parity. Not semantic authority.';

-- One parity receipt is an immutable observation of one exact owner/store/
-- namespace/source-revision snapshot comparison. PASS is mechanically guarded.
CREATE TABLE IF NOT EXISTS dnd_visual.visual_state_parity_receipt (
    parity_receipt_id text PRIMARY KEY,
    session_id text NOT NULL,
    source_revision text NOT NULL,
    display_ledger_owner_id text NOT NULL,
    display_store_id text NOT NULL,
    display_namespace text NOT NULL,
    sqlite_snapshot_digest_sha256 text NOT NULL
        CHECK (sqlite_snapshot_digest_sha256 ~ '^[0-9a-f]{64}$'),
    sql_snapshot_digest_sha256 text NOT NULL
        CHECK (sql_snapshot_digest_sha256 ~ '^[0-9a-f]{64}$'),
    sqlite_logical_index bigint NOT NULL CHECK (sqlite_logical_index >= 0),
    sql_logical_index bigint NOT NULL CHECK (sql_logical_index >= 0),
    sqlite_record_count bigint NOT NULL CHECK (sqlite_record_count >= 0),
    sql_record_count bigint NOT NULL CHECK (sql_record_count >= 0),
    identity_parity_status text NOT NULL
        CHECK (identity_parity_status IN ('PASS','FAIL','UNKNOWN')),
    order_parity_status text NOT NULL
        CHECK (order_parity_status IN ('PASS','FAIL','UNKNOWN')),
    hash_parity_status text NOT NULL
        CHECK (hash_parity_status IN ('PASS','FAIL','UNKNOWN')),
    replay_semantics_status text NOT NULL
        CHECK (replay_semantics_status IN ('PASS','FAIL','UNKNOWN')),
    parity_status text NOT NULL
        CHECK (parity_status IN ('PASS','FAIL','NOT_READY')),
    findings_digest_sha256 text NOT NULL
        CHECK (findings_digest_sha256 ~ '^[0-9a-f]{64}$'),
    validator_version text NOT NULL,
    source_commit_sha text NOT NULL
        CHECK (source_commit_sha ~ '^[0-9a-f]{40}$'),
    exposure_class text NOT NULL DEFAULT 'MIGRATION_INTERNAL'
        CHECK (exposure_class = 'MIGRATION_INTERNAL'),
    semantic_authority boolean NOT NULL DEFAULT false
        CHECK (semantic_authority = false),
    checked_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT visual_state_parity_pass_guard_ck CHECK (
        parity_status <> 'PASS'
        OR (
            identity_parity_status = 'PASS'
            AND order_parity_status = 'PASS'
            AND hash_parity_status = 'PASS'
            AND replay_semantics_status = 'PASS'
            AND sqlite_logical_index = sql_logical_index
            AND sqlite_record_count = sql_record_count
            AND sqlite_snapshot_digest_sha256 = sql_snapshot_digest_sha256
        )
    )
);

CREATE INDEX IF NOT EXISTS visual_state_parity_lineage_idx
    ON dnd_visual.visual_state_parity_receipt (
        session_id,
        source_revision,
        display_ledger_owner_id,
        display_namespace,
        checked_at DESC
    );
CREATE INDEX IF NOT EXISTS visual_state_parity_status_idx
    ON dnd_visual.visual_state_parity_receipt (parity_status, checked_at DESC);

COMMENT ON TABLE dnd_visual.visual_state_parity_receipt IS
'Migration-readiness evidence only. PASS requires exact identity/order/hash/replay parity and does not promote SQL to presentation authority.';

-- Derived readiness view. Missing evidence and stale/non-PASS evidence can
-- never be interpreted as cutover authorization.
CREATE OR REPLACE VIEW dnd_visual.visual_sql_parity_readiness AS
WITH latest AS (
    SELECT DISTINCT ON (
        session_id,
        source_revision,
        display_ledger_owner_id,
        display_store_id,
        display_namespace
    )
        parity_receipt_id,
        session_id,
        source_revision,
        display_ledger_owner_id,
        display_store_id,
        display_namespace,
        parity_status,
        identity_parity_status,
        order_parity_status,
        hash_parity_status,
        replay_semantics_status,
        sqlite_logical_index,
        sql_logical_index,
        sqlite_record_count,
        sql_record_count,
        sqlite_snapshot_digest_sha256,
        sql_snapshot_digest_sha256,
        source_commit_sha,
        checked_at
    FROM dnd_visual.visual_state_parity_receipt
    ORDER BY
        session_id,
        source_revision,
        display_ledger_owner_id,
        display_store_id,
        display_namespace,
        checked_at DESC
)
SELECT
    latest.*,
    CASE
        WHEN parity_status = 'PASS'
             AND identity_parity_status = 'PASS'
             AND order_parity_status = 'PASS'
             AND hash_parity_status = 'PASS'
             AND replay_semantics_status = 'PASS'
             AND sqlite_logical_index = sql_logical_index
             AND sqlite_record_count = sql_record_count
             AND sqlite_snapshot_digest_sha256 = sql_snapshot_digest_sha256
            THEN 'PARITY_PASS_NOT_CUTOVER_AUTHORIZATION'
        WHEN parity_status = 'FAIL'
            THEN 'PARITY_FAIL'
        ELSE 'NOT_READY'
    END AS derived_readiness
FROM latest;

-- Defensive catalog guards for this migration stage.
DO $$
DECLARE
    forbidden_key_columns integer;
    authority_true_defaults integer;
BEGIN
    SELECT count(*)
      INTO forbidden_key_columns
      FROM information_schema.columns
     WHERE table_schema IN ('dnd_control','dnd_visual')
       AND table_name IN (
           'authority_grant_record',
           'visual_activation_run',
           'display_commit',
           'display_commit_tactical_receipt',
           'visual_state_parity_receipt'
       )
       AND lower(column_name) ~ '(private.*key|private.*pem|signing.*key|keyring.*pem|verification.*pem)';

    IF forbidden_key_columns <> 0 THEN
        RAISE EXCEPTION 'VSQL4_FORBIDDEN_KEY_MATERIAL_COLUMN';
    END IF;

    SELECT count(*)
      INTO authority_true_defaults
      FROM information_schema.columns
     WHERE table_schema = 'dnd_visual'
       AND table_name IN (
           'visual_activation_run',
           'display_commit',
           'display_commit_tactical_receipt',
           'visual_state_parity_receipt'
       )
       AND column_name = 'semantic_authority'
       AND column_default IS DISTINCT FROM 'false';

    IF authority_true_defaults <> 0 THEN
        RAISE EXCEPTION 'VSQL4_SEMANTIC_AUTHORITY_DEFAULT_INVALID';
    END IF;
END $$;

COMMIT;

-- Rollback policy:
-- VSQL-4 is shadow/parity state only. No automatic DROP is permitted.
-- Before any SQL_PRIMARY cutover, rollback means stop shadow writes, preserve
-- evidence, keep SQLite as active presentation owner, and mark migration
-- readiness NOT_READY until a reviewed follow-up migration is applied.
