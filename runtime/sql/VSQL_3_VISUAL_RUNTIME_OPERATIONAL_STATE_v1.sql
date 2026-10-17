-- VSQL_3_VISUAL_RUNTIME_OPERATIONAL_STATE_v1
-- MODE=SQL_FIRST_MIGRATION_CANDIDATE
-- TARGET_RELEASE=v1.3.8
-- ACTIVE_RUNTIME_BASELINE=DND_ENGINE_RUNTIME_MF_v1.3.7_VISUAL_EXECUTION_HARDENING
-- PROMOTION_AUTHORIZATION=NO
-- MERGE_AUTHORIZATION=NO_UNTIL_NEW_EXACT_HEAD_QA_PASS
-- GOVERNING_DIRECTIVE=docs/SQL_FIRST_RUNTIME_MIGRATION_HANDOFF_2026-10-14.md
-- LOCAL_CONTRACT=docs/visual/VISUAL_RUNTIME_SQL_MIGRATION_v1.md
--
-- SECURITY / AUTHORITY RULES:
-- * PostgreSQL stores structured operational state/evidence for this subsystem.
-- * PostgreSQL MUST NOT select or replace the Runtime Host verification root.
-- * No private signing key or PEM/keyring material is stored here.
-- * These rows do not become Campaign Canon, Geometry Master, checkpoint/AEL,
--   knowledge/PKP, or topology semantic authority merely by existing.
-- * Current visual_state routing remains FILE_PRIMARY until explicit parity/cutover.
-- * SQLite display ledger remains the active presentation replay owner during VSQL-3.
-- * No silent fallback between file/SQLite and SQL state is permitted.
--
-- This migration intentionally creates only the PR #15-owned visual/control tables.
-- It MUST NOT create duplicate checkpoint, Applied Event Ledger, PKP/knowledge,
-- topology, or source-asset tables.

BEGIN;

CREATE SCHEMA IF NOT EXISTS dnd_control;
CREATE SCHEMA IF NOT EXISTS dnd_visual;

CREATE TABLE IF NOT EXISTS dnd_control.authority_grant_record (
    grant_id text PRIMARY KEY,
    schema_version integer NOT NULL CHECK (schema_version > 0),
    request_id text NOT NULL,
    key_id text NOT NULL,
    verification_root_id text NOT NULL,
    verification_root_fingerprint_sha256 text NOT NULL
        CHECK (verification_root_fingerprint_sha256 ~ '^[0-9a-f]{64}$'),
    session_id text NOT NULL,
    activation_id text NOT NULL,
    source_revision text NOT NULL,
    checkpoint_receipt_id text NOT NULL,
    checkpoint_digest_sha256 text NOT NULL
        CHECK (checkpoint_digest_sha256 ~ '^[0-9a-f]{64}$'),
    event_id text NOT NULL,
    ael_owner_id text NOT NULL,
    ael_snapshot_digest_sha256 text NOT NULL
        CHECK (ael_snapshot_digest_sha256 ~ '^[0-9a-f]{64}$'),
    pkp_id text NOT NULL,
    observer_branch_id text NOT NULL,
    pkp_revision text NOT NULL,
    pkp_digest_sha256 text NOT NULL
        CHECK (pkp_digest_sha256 ~ '^[0-9a-f]{64}$'),
    leak_gate_receipt_id text NOT NULL,
    leak_gate_receipt_digest_sha256 text NOT NULL
        CHECK (leak_gate_receipt_digest_sha256 ~ '^[0-9a-f]{64}$'),
    player_safe_bundle_digest_sha256 text NOT NULL
        CHECK (player_safe_bundle_digest_sha256 ~ '^[0-9a-f]{64}$'),
    display_ledger_owner_id text NOT NULL,
    display_store_id text NOT NULL,
    display_namespace text NOT NULL,
    grant_payload_sha256 text NOT NULL
        CHECK (grant_payload_sha256 ~ '^[0-9a-f]{64}$'),
    signature_sha256 text NOT NULL
        CHECK (signature_sha256 ~ '^[0-9a-f]{64}$'),
    nonce text NOT NULL UNIQUE,
    issued_at timestamptz NOT NULL,
    expires_at timestamptz NOT NULL,
    verified_at timestamptz NULL,
    used_at timestamptz NULL,
    revoked_at timestamptz NULL,
    rejected_at timestamptz NULL,
    grant_status text NOT NULL DEFAULT 'ISSUED'
        CHECK (grant_status IN ('ISSUED','VERIFIED','USED','REVOKED','EXPIRED','REJECTED')),
    source_commit_sha text NOT NULL
        CHECK (source_commit_sha ~ '^[0-9a-f]{40}$'),
    broker_version text NOT NULL,
    validator_version text NOT NULL,
    exposure_class text NOT NULL DEFAULT 'SECURITY_INTERNAL'
        CHECK (exposure_class = 'SECURITY_INTERNAL'),
    semantic_authority boolean NOT NULL DEFAULT false
        CHECK (semantic_authority = false),
    trust_root_authority boolean NOT NULL DEFAULT false
        CHECK (trust_root_authority = false),
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT authority_grant_record_expiry_ck CHECK (expires_at > issued_at),
    CONSTRAINT authority_grant_record_terminal_time_ck CHECK (
        (grant_status <> 'USED' OR used_at IS NOT NULL) AND
        (grant_status <> 'REVOKED' OR revoked_at IS NOT NULL) AND
        (grant_status <> 'REJECTED' OR rejected_at IS NOT NULL)
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS authority_grant_session_activation_revision_uq
    ON dnd_control.authority_grant_record (session_id, activation_id, source_revision, grant_id);
CREATE INDEX IF NOT EXISTS authority_grant_status_idx
    ON dnd_control.authority_grant_record (grant_status, expires_at);
CREATE INDEX IF NOT EXISTS authority_grant_revision_idx
    ON dnd_control.authority_grant_record (source_revision, source_commit_sha);

COMMENT ON TABLE dnd_control.authority_grant_record IS
'Operational security evidence for broker-issued grants. Rows do not select the Runtime Host verification root and are not semantic authority.';
COMMENT ON COLUMN dnd_control.authority_grant_record.verification_root_id IS
'Audit identity only. The trusted Runtime Host root is selected by bootstrap/OS before request handling; this column cannot select trust.';
COMMENT ON COLUMN dnd_control.authority_grant_record.verification_root_fingerprint_sha256 IS
'Audit fingerprint only; never a caller- or database-selected verification root.';

CREATE TABLE IF NOT EXISTS dnd_visual.visual_activation_run (
    activation_run_id text PRIMARY KEY,
    activation_id text NOT NULL,
    attempt_no integer NOT NULL CHECK (attempt_no > 0),
    session_id text NOT NULL,
    source_revision text NOT NULL,
    grant_id text NOT NULL REFERENCES dnd_control.authority_grant_record(grant_id),
    generation_packet_id text NOT NULL,
    generation_packet_sha256 text NOT NULL
        CHECK (generation_packet_sha256 ~ '^[0-9a-f]{64}$'),
    player_safe_bundle_digest_sha256 text NOT NULL
        CHECK (player_safe_bundle_digest_sha256 ~ '^[0-9a-f]{64}$'),
    visual_profile_id text NOT NULL,
    visual_pipeline_status text NOT NULL
        CHECK (visual_pipeline_status IN ('PENDING','GENERATION_READY','RENDERED','DISPLAYED','BLOCKED','FAILED')),
    structural_gate_status text NOT NULL DEFAULT 'NOT_APPLICABLE'
        CHECK (structural_gate_status IN ('NOT_APPLICABLE','PASS','FAIL','UNKNOWN')),
    presentation_gate_status text NOT NULL DEFAULT 'UNKNOWN'
        CHECK (presentation_gate_status IN ('PASS','FAIL','UNKNOWN')),
    render_status text NOT NULL DEFAULT 'PENDING'
        CHECK (render_status IN ('PENDING','SUCCESS','FAILED','BLOCKED')),
    renderer_version text NULL,
    render_artifact_id text NULL,
    render_artifact_sha256 text NULL
        CHECK (render_artifact_sha256 IS NULL OR render_artifact_sha256 ~ '^[0-9a-f]{64}$'),
    source_commit_sha text NOT NULL
        CHECK (source_commit_sha ~ '^[0-9a-f]{40}$'),
    exposure_class text NOT NULL DEFAULT 'PLAYER_SAFE_VISUAL_METADATA'
        CHECK (exposure_class = 'PLAYER_SAFE_VISUAL_METADATA'),
    semantic_authority boolean NOT NULL DEFAULT false
        CHECK (semantic_authority = false),
    created_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz NULL,
    CONSTRAINT visual_activation_run_completion_ck CHECK (
        (visual_pipeline_status IN ('DISPLAYED','BLOCKED','FAILED') AND completed_at IS NOT NULL)
        OR visual_pipeline_status NOT IN ('DISPLAYED','BLOCKED','FAILED')
    ),
    CONSTRAINT visual_activation_run_render_binding_ck CHECK (
        (render_artifact_id IS NULL AND render_artifact_sha256 IS NULL)
        OR (render_artifact_id IS NOT NULL AND render_artifact_sha256 IS NOT NULL)
    ),
    UNIQUE (session_id, activation_id, source_revision, attempt_no)
);

CREATE INDEX IF NOT EXISTS visual_activation_status_idx
    ON dnd_visual.visual_activation_run (visual_pipeline_status, source_revision);
CREATE INDEX IF NOT EXISTS visual_activation_grant_idx
    ON dnd_visual.visual_activation_run (grant_id, session_id, activation_id);

COMMENT ON TABLE dnd_visual.visual_activation_run IS
'Versioned visual attempt lineage. This table never owns topology, Canon, checkpoint/AEL semantics, PKP semantics, or hidden DM truth.';

CREATE TABLE IF NOT EXISTS dnd_visual.display_commit (
    display_commit_id text PRIMARY KEY,
    activation_run_id text NOT NULL UNIQUE
        REFERENCES dnd_visual.visual_activation_run(activation_run_id),
    activation_id text NOT NULL,
    session_id text NOT NULL,
    source_revision text NOT NULL,
    grant_id text NOT NULL REFERENCES dnd_control.authority_grant_record(grant_id),
    generation_packet_id text NOT NULL,
    generation_packet_sha256 text NOT NULL
        CHECK (generation_packet_sha256 ~ '^[0-9a-f]{64}$'),
    render_artifact_id text NOT NULL,
    render_artifact_sha256 text NOT NULL
        CHECK (render_artifact_sha256 ~ '^[0-9a-f]{64}$'),
    identity_comparator_receipt_id text NOT NULL,
    player_safe_receipt_id text NOT NULL,
    tactical_receipt_id text NULL,
    display_ledger_owner_id text NOT NULL,
    display_store_id text NOT NULL,
    display_namespace text NOT NULL,
    logical_display_index bigint NOT NULL CHECK (logical_display_index > 0),
    display_status text NOT NULL DEFAULT 'COMMITTED'
        CHECK (display_status = 'COMMITTED'),
    source_commit_sha text NOT NULL
        CHECK (source_commit_sha ~ '^[0-9a-f]{40}$'),
    exposure_class text NOT NULL DEFAULT 'PLAYER_SAFE_DISPLAY_METADATA'
        CHECK (exposure_class = 'PLAYER_SAFE_DISPLAY_METADATA'),
    semantic_authority boolean NOT NULL DEFAULT false
        CHECK (semantic_authority = false),
    committed_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (
        display_ledger_owner_id,
        display_store_id,
        display_namespace,
        logical_display_index
    ),
    UNIQUE (
        display_ledger_owner_id,
        display_store_id,
        display_namespace,
        source_revision,
        generation_packet_sha256
    ),
    UNIQUE (grant_id, generation_packet_sha256)
);

CREATE INDEX IF NOT EXISTS display_commit_lineage_idx
    ON dnd_visual.display_commit (
        session_id,
        source_revision,
        display_ledger_owner_id,
        display_namespace,
        logical_display_index
    );
CREATE INDEX IF NOT EXISTS display_commit_render_idx
    ON dnd_visual.display_commit (render_artifact_id, render_artifact_sha256);

COMMENT ON TABLE dnd_visual.display_commit IS
'Presentation-only display commit candidate. VSQL-3 does not cut over from SQLite; SQL becomes operational owner only after VSQL-4 parity and explicit cutover.';

-- Defensive catalog guard: this migration must not introduce key material columns.
DO $$
DECLARE
    forbidden_count integer;
BEGIN
    SELECT count(*)
      INTO forbidden_count
      FROM information_schema.columns
     WHERE table_schema IN ('dnd_control','dnd_visual')
       AND table_name IN ('authority_grant_record','visual_activation_run','display_commit')
       AND lower(column_name) ~ '(private.*key|private.*pem|signing.*key|keyring.*pem|verification.*pem)';

    IF forbidden_count <> 0 THEN
        RAISE EXCEPTION 'VSQL3_FORBIDDEN_KEY_MATERIAL_COLUMN';
    END IF;
END $$;

COMMIT;

-- Rollback policy for this candidate migration:
-- No automatic DROP is executed. Before SQL_PRIMARY cutover these tables are
-- migration-candidate state only. Any rollback must be an explicit reviewed
-- migration preserving exported evidence/history; never silently destroy rows.
