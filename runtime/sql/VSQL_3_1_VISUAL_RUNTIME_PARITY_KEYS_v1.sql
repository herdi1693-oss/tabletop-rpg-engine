-- VSQL_3_1_VISUAL_RUNTIME_PARITY_KEYS_v1
-- Additive hardening for VSQL-4 dual-write/parity.
-- SQLite remains the presentation replay owner until explicit cutover.
-- PostgreSQL remains migration operational/evidence state, not Canon or trust root.

BEGIN;

ALTER TABLE dnd_visual.display_commit
    ADD COLUMN IF NOT EXISTS display_receipt_id text;
ALTER TABLE dnd_visual.display_commit
    ADD COLUMN IF NOT EXISTS canonical_display_record_sha256 text;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM dnd_visual.display_commit
        WHERE display_receipt_id IS NULL
           OR canonical_display_record_sha256 IS NULL
    ) THEN
        RAISE EXCEPTION 'VSQL31_DISPLAY_PARITY_BACKFILL_REQUIRED';
    END IF;
END $$;

ALTER TABLE dnd_visual.display_commit
    ALTER COLUMN display_receipt_id SET NOT NULL;
ALTER TABLE dnd_visual.display_commit
    ALTER COLUMN canonical_display_record_sha256 SET NOT NULL;

ALTER TABLE dnd_visual.display_commit
    DROP CONSTRAINT IF EXISTS display_commit_canonical_record_sha256_ck;
ALTER TABLE dnd_visual.display_commit
    ADD CONSTRAINT display_commit_canonical_record_sha256_ck
    CHECK (canonical_display_record_sha256 ~ '^[0-9a-f]{64}$');

-- Exact replay semantics must match the current SQLite owner inside one
-- display owner/store/namespace lineage.
CREATE UNIQUE INDEX IF NOT EXISTS display_commit_receipt_replay_uq
    ON dnd_visual.display_commit (
        display_ledger_owner_id, display_store_id, display_namespace, display_receipt_id
    );
CREATE UNIQUE INDEX IF NOT EXISTS display_commit_activation_replay_uq
    ON dnd_visual.display_commit (
        display_ledger_owner_id, display_store_id, display_namespace, activation_id
    );
CREATE UNIQUE INDEX IF NOT EXISTS display_commit_render_replay_uq
    ON dnd_visual.display_commit (
        display_ledger_owner_id, display_store_id, display_namespace, render_artifact_id
    );
CREATE UNIQUE INDEX IF NOT EXISTS display_commit_identity_receipt_replay_uq
    ON dnd_visual.display_commit (
        display_ledger_owner_id, display_store_id, display_namespace, identity_comparator_receipt_id
    );
CREATE UNIQUE INDEX IF NOT EXISTS display_commit_player_safe_receipt_replay_uq
    ON dnd_visual.display_commit (
        display_ledger_owner_id, display_store_id, display_namespace, player_safe_receipt_id
    );

-- SQLite stores a sequence of tactical receipt IDs, not one scalar receipt.
-- Keep the old scalar column for migration compatibility but do not use it as
-- parity authority. Normalize tactical receipt replay evidence here.
CREATE TABLE IF NOT EXISTS dnd_visual.display_tactical_receipt (
    display_commit_id text NOT NULL,
    display_ledger_owner_id text NOT NULL,
    display_store_id text NOT NULL,
    display_namespace text NOT NULL,
    receipt_id text NOT NULL,
    ordinal integer NOT NULL CHECK (ordinal >= 0),
    semantic_authority boolean NOT NULL DEFAULT false
        CHECK (semantic_authority = false),
    exposure_class text NOT NULL DEFAULT 'PLAYER_SAFE_DISPLAY_METADATA'
        CHECK (exposure_class = 'PLAYER_SAFE_DISPLAY_METADATA'),
    PRIMARY KEY (display_commit_id, receipt_id),
    UNIQUE (display_commit_id, ordinal),
    UNIQUE (
        display_ledger_owner_id, display_store_id, display_namespace, receipt_id
    ),
    FOREIGN KEY (display_commit_id)
        REFERENCES dnd_visual.display_commit(display_commit_id)
        ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS display_tactical_receipt_lineage_idx
    ON dnd_visual.display_tactical_receipt (
        display_ledger_owner_id, display_store_id, display_namespace, display_commit_id, ordinal
    );

COMMENT ON COLUMN dnd_visual.display_commit.display_receipt_id IS
'Exact canonical SQLite display receipt identity used for VSQL-4 parity.';
COMMENT ON COLUMN dnd_visual.display_commit.canonical_display_record_sha256 IS
'SHA-256 of the exact canonical SQLite display record projection used only for migration parity; not semantic authority.';
COMMENT ON TABLE dnd_visual.display_tactical_receipt IS
'Normalized tactical receipt replay/parity evidence for VSQL-4. SQLite remains operational replay owner until cutover.';

COMMIT;
