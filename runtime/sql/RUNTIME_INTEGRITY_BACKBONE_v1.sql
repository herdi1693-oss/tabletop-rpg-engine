-- RUNTIME_INTEGRITY_BACKBONE_v1
-- MODE=SQL_FIRST_MIGRATION_CANDIDATE
-- PARENT_ENGINE_PHASE_B_QA_HEAD=f548facf24f9e107f31744fd18fa2dc2a9d6bdca
-- ACTIVE_RUNTIME_BASELINE=DND_ENGINE_RUNTIME_MF_v1.3.7_VISUAL_EXECUTION_HARDENING
-- ROUTING_STAGE=FILE_PRIMARY
-- SQL_PRIMARY_AUTHORIZATION=NO
-- RUNTIME_PROMOTION_AUTHORIZATION=NO
-- SHARED_NEON_MUTATION_AUTHORIZATION=NO
-- GOVERNING_DIRECTIVE=docs/SQL_FIRST_RUNTIME_MIGRATION_HANDOFF_2026-10-14.md
--
-- FIRST SLICE ONLY:
--   SESSION_AND_LOGICAL_REVISION
--   EVENT_ENVELOPE_AND_COMMIT_RECORD
--   APPLIED_EVENT_LEDGER
--   MULTI_OWNER_TRANSACTION_RECEIPT
--   CHECKPOINT_AND_OWNER_STATE_HASH_BINDINGS
--   RNG_STATE_AND_RNG_RECEIPT
--
-- Explicitly NOT materialized here:
-- actor/PC sheet, combat/encounter, inventory/resources, effect state,
-- timer state, NPC state, full spatial/topology state, knowledge/PKP,
-- source assets, visual state.
--
-- This initial migration intentionally FAILS if dnd_runtime already exists.
-- A fresh read-only Neon preflight must prove the schema absent before an
-- isolated migration branch may execute these bytes.

BEGIN;

CREATE SCHEMA dnd_runtime;

CREATE TABLE dnd_runtime.session_revision (
    session_id text PRIMARY KEY CHECK (btrim(session_id) <> ''),
    logical_revision bigint NOT NULL CHECK (logical_revision >= 0),
    last_committed_event_id text NULL,
    last_checkpoint_id text NULL,
    state_digest_sha256 text NOT NULL CHECK (state_digest_sha256 ~ '^[0-9a-f]{64}$'),
    source_revision text NOT NULL CHECK (btrim(source_revision) <> ''),
    cutover_authorized boolean NOT NULL DEFAULT false CHECK (cutover_authorized = false),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT session_revision_barrier_ck CHECK (
        (logical_revision = 0 AND last_committed_event_id IS NULL AND last_checkpoint_id IS NULL)
        OR
        (logical_revision > 0 AND last_committed_event_id IS NOT NULL AND last_checkpoint_id IS NOT NULL)
    )
);

CREATE TABLE dnd_runtime.event_commit (
    event_id text PRIMARY KEY CHECK (btrim(event_id) <> ''),
    session_id text NOT NULL,
    logical_revision bigint NOT NULL CHECK (logical_revision > 0),
    event_type text NOT NULL CHECK (btrim(event_type) <> ''),
    payload_sha256 text NOT NULL CHECK (payload_sha256 ~ '^[0-9a-f]{64}$'),
    owner_set_sha256 text NOT NULL CHECK (owner_set_sha256 ~ '^[0-9a-f]{64}$'),
    ael_owner_id text NOT NULL CHECK (btrim(ael_owner_id) <> ''),
    transaction_id text NOT NULL CHECK (btrim(transaction_id) <> ''),
    checkpoint_id text NOT NULL CHECK (btrim(checkpoint_id) <> ''),
    commit_status text NOT NULL DEFAULT 'COMMITTED' CHECK (commit_status = 'COMMITTED'),
    committed_at timestamptz NOT NULL DEFAULT now(),
    source_revision text NOT NULL CHECK (btrim(source_revision) <> ''),
    UNIQUE (session_id, logical_revision),
    UNIQUE (event_id, session_id, logical_revision),
    UNIQUE (event_id, session_id, logical_revision, ael_owner_id, payload_sha256),
    UNIQUE (transaction_id, event_id, session_id, logical_revision, owner_set_sha256),
    UNIQUE (checkpoint_id, event_id, session_id, logical_revision)
);

CREATE TABLE dnd_runtime.applied_event_ledger (
    event_id text PRIMARY KEY,
    session_id text NOT NULL,
    logical_revision bigint NOT NULL CHECK (logical_revision > 0),
    ael_owner_id text NOT NULL CHECK (btrim(ael_owner_id) <> ''),
    payload_sha256 text NOT NULL CHECK (payload_sha256 ~ '^[0-9a-f]{64}$'),
    applied_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (session_id, logical_revision),
    UNIQUE (event_id, session_id, logical_revision, ael_owner_id, payload_sha256)
);

CREATE TABLE dnd_runtime.transaction_receipt (
    transaction_id text PRIMARY KEY CHECK (btrim(transaction_id) <> ''),
    event_id text NOT NULL UNIQUE,
    session_id text NOT NULL,
    logical_revision bigint NOT NULL CHECK (logical_revision > 0),
    owner_ids text[] NOT NULL CHECK (cardinality(owner_ids) >= 1) CHECK (array_position(owner_ids, NULL) IS NULL),
    owner_set_sha256 text NOT NULL CHECK (owner_set_sha256 ~ '^[0-9a-f]{64}$'),
    transaction_status text NOT NULL DEFAULT 'COMMITTED' CHECK (transaction_status = 'COMMITTED'),
    committed_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (transaction_id, event_id, session_id, logical_revision, owner_set_sha256)
);

CREATE TABLE dnd_runtime.checkpoint_commit (
    checkpoint_id text PRIMARY KEY CHECK (btrim(checkpoint_id) <> ''),
    event_id text NOT NULL UNIQUE,
    session_id text NOT NULL,
    logical_revision bigint NOT NULL CHECK (logical_revision > 0),
    checkpoint_digest_sha256 text NOT NULL CHECK (checkpoint_digest_sha256 ~ '^[0-9a-f]{64}$'),
    owner_binding_count integer NOT NULL CHECK (owner_binding_count > 0),
    checkpoint_status text NOT NULL DEFAULT 'COMMITTED' CHECK (checkpoint_status = 'COMMITTED'),
    committed_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (checkpoint_id, event_id, session_id, logical_revision),
    UNIQUE (checkpoint_id, session_id, logical_revision)
);

CREATE TABLE dnd_runtime.checkpoint_owner_state (
    checkpoint_id text NOT NULL,
    session_id text NOT NULL,
    logical_revision bigint NOT NULL CHECK (logical_revision > 0),
    owner_id text NOT NULL CHECK (btrim(owner_id) <> ''),
    owner_state_sha256 text NOT NULL CHECK (owner_state_sha256 ~ '^[0-9a-f]{64}$'),
    binding_digest_sha256 text NOT NULL CHECK (binding_digest_sha256 ~ '^[0-9a-f]{64}$'),
    PRIMARY KEY (checkpoint_id, owner_id),
    UNIQUE (checkpoint_id, session_id, logical_revision, owner_id)
);

CREATE TABLE dnd_runtime.rng_state_receipt (
    rng_receipt_id text PRIMARY KEY CHECK (btrim(rng_receipt_id) <> ''),
    event_id text NOT NULL,
    session_id text NOT NULL,
    logical_revision bigint NOT NULL CHECK (logical_revision > 0),
    rng_stream_id text NOT NULL CHECK (btrim(rng_stream_id) <> ''),
    rng_cursor bigint NOT NULL CHECK (rng_cursor >= 0),
    rng_state_sha256 text NOT NULL CHECK (rng_state_sha256 ~ '^[0-9a-f]{64}$'),
    draw_receipt_sha256 text NOT NULL CHECK (draw_receipt_sha256 ~ '^[0-9a-f]{64}$'),
    committed_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (session_id, rng_stream_id, logical_revision),
    UNIQUE (event_id, session_id, logical_revision, rng_stream_id)
);

ALTER TABLE dnd_runtime.event_commit
    ADD CONSTRAINT event_session_fk FOREIGN KEY (session_id)
    REFERENCES dnd_runtime.session_revision(session_id)
    ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE dnd_runtime.applied_event_ledger
    ADD CONSTRAINT ael_event_fk FOREIGN KEY (event_id, session_id, logical_revision, ael_owner_id, payload_sha256)
    REFERENCES dnd_runtime.event_commit (event_id, session_id, logical_revision, ael_owner_id, payload_sha256)
    ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE dnd_runtime.event_commit
    ADD CONSTRAINT event_ael_fk FOREIGN KEY (event_id, session_id, logical_revision, ael_owner_id, payload_sha256)
    REFERENCES dnd_runtime.applied_event_ledger (event_id, session_id, logical_revision, ael_owner_id, payload_sha256)
    ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE dnd_runtime.transaction_receipt
    ADD CONSTRAINT tx_event_fk FOREIGN KEY (transaction_id, event_id, session_id, logical_revision, owner_set_sha256)
    REFERENCES dnd_runtime.event_commit (transaction_id, event_id, session_id, logical_revision, owner_set_sha256)
    ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE dnd_runtime.event_commit
    ADD CONSTRAINT event_tx_fk FOREIGN KEY (transaction_id, event_id, session_id, logical_revision, owner_set_sha256)
    REFERENCES dnd_runtime.transaction_receipt (transaction_id, event_id, session_id, logical_revision, owner_set_sha256)
    ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE dnd_runtime.checkpoint_commit
    ADD CONSTRAINT checkpoint_event_fk FOREIGN KEY (checkpoint_id, event_id, session_id, logical_revision)
    REFERENCES dnd_runtime.event_commit (checkpoint_id, event_id, session_id, logical_revision)
    ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE dnd_runtime.event_commit
    ADD CONSTRAINT event_checkpoint_fk FOREIGN KEY (checkpoint_id, event_id, session_id, logical_revision)
    REFERENCES dnd_runtime.checkpoint_commit (checkpoint_id, event_id, session_id, logical_revision)
    ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE dnd_runtime.checkpoint_owner_state
    ADD CONSTRAINT checkpoint_owner_commit_fk FOREIGN KEY (checkpoint_id, session_id, logical_revision)
    REFERENCES dnd_runtime.checkpoint_commit (checkpoint_id, session_id, logical_revision)
    ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE dnd_runtime.session_revision
    ADD CONSTRAINT session_last_event_fk FOREIGN KEY (last_committed_event_id, session_id, logical_revision)
    REFERENCES dnd_runtime.event_commit (event_id, session_id, logical_revision)
    ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE dnd_runtime.session_revision
    ADD CONSTRAINT session_last_checkpoint_fk FOREIGN KEY (last_checkpoint_id, session_id, logical_revision)
    REFERENCES dnd_runtime.checkpoint_commit (checkpoint_id, session_id, logical_revision)
    ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE dnd_runtime.rng_state_receipt
    ADD CONSTRAINT rng_event_fk FOREIGN KEY (event_id, session_id, logical_revision)
    REFERENCES dnd_runtime.event_commit (event_id, session_id, logical_revision)
    ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED;

-- Deferred relational enforcement for the multi-owner save barrier. The
-- transaction owner set, checkpoint owner-state membership and declared
-- owner_binding_count must all describe the same committed owner set.
CREATE FUNCTION dnd_runtime.assert_save_barrier_owner_membership()
RETURNS trigger
LANGUAGE plpgsql
AS E'DECLARE\n    v_session_id text := NEW.session_id\073\n    v_logical_revision bigint := NEW.logical_revision\073\n    v_tx_owner_ids text[]\073\n    v_tx_owner_ids_canonical text[]\073\n    v_checkpoint_owner_ids text[]\073\n    v_owner_binding_count integer\073\n    v_checkpoint_owner_count integer\073\nBEGIN\n    SELECT tr.owner_ids,\n           ARRAY(SELECT DISTINCT x.owner_id FROM unnest(tr.owner_ids) AS x(owner_id) ORDER BY x.owner_id)\n      INTO v_tx_owner_ids, v_tx_owner_ids_canonical\n      FROM dnd_runtime.transaction_receipt AS tr\n     WHERE tr.session_id = v_session_id\n       AND tr.logical_revision = v_logical_revision\073\n    IF v_tx_owner_ids IS NULL THEN\n        RAISE EXCEPTION ''DND_RUNTIME_SAVE_BARRIER_MISSING_TRANSACTION:%:%'', v_session_id, v_logical_revision\n            USING ERRCODE = ''23514''\073\n    END IF\073\n    IF EXISTS (\n        SELECT 1 FROM unnest(v_tx_owner_ids) AS x(owner_id)\n         WHERE btrim(x.owner_id) = ''''\n    ) THEN\n        RAISE EXCEPTION ''DND_RUNTIME_TRANSACTION_OWNER_EMPTY:%:%'', v_session_id, v_logical_revision\n            USING ERRCODE = ''23514''\073\n    END IF\073\n    IF cardinality(v_tx_owner_ids) <> cardinality(v_tx_owner_ids_canonical) THEN\n        RAISE EXCEPTION ''DND_RUNTIME_TRANSACTION_OWNER_DUPLICATE:%:%'', v_session_id, v_logical_revision\n            USING ERRCODE = ''23514''\073\n    END IF\073\n    SELECT cc.owner_binding_count,\n           COALESCE(\n               array_agg(cos.owner_id ORDER BY cos.owner_id) FILTER (WHERE cos.owner_id IS NOT NULL),\n               ARRAY[]::text[]\n           ),\n           count(cos.owner_id)::integer\n      INTO v_owner_binding_count, v_checkpoint_owner_ids, v_checkpoint_owner_count\n      FROM dnd_runtime.checkpoint_commit AS cc\n      LEFT JOIN dnd_runtime.checkpoint_owner_state AS cos\n        ON cos.checkpoint_id = cc.checkpoint_id\n       AND cos.session_id = cc.session_id\n       AND cos.logical_revision = cc.logical_revision\n     WHERE cc.session_id = v_session_id\n       AND cc.logical_revision = v_logical_revision\n     GROUP BY cc.owner_binding_count\073\n    IF v_owner_binding_count IS NULL THEN\n        RAISE EXCEPTION ''DND_RUNTIME_SAVE_BARRIER_MISSING_CHECKPOINT:%:%'', v_session_id, v_logical_revision\n            USING ERRCODE = ''23514''\073\n    END IF\073\n    IF v_owner_binding_count <> v_checkpoint_owner_count THEN\n        RAISE EXCEPTION ''DND_RUNTIME_CHECKPOINT_OWNER_COUNT_MISMATCH:%:%'', v_session_id, v_logical_revision\n            USING ERRCODE = ''23514''\073\n    END IF\073\n    IF v_owner_binding_count <> cardinality(v_tx_owner_ids_canonical) THEN\n        RAISE EXCEPTION ''DND_RUNTIME_TRANSACTION_CHECKPOINT_OWNER_COUNT_MISMATCH:%:%'', v_session_id, v_logical_revision\n            USING ERRCODE = ''23514''\073\n    END IF\073\n    IF v_tx_owner_ids_canonical <> v_checkpoint_owner_ids THEN\n        RAISE EXCEPTION ''DND_RUNTIME_TRANSACTION_CHECKPOINT_OWNER_SET_MISMATCH:%:%'', v_session_id, v_logical_revision\n            USING ERRCODE = ''23514''\073\n    END IF\073\n    RETURN NULL\073\nEND\073';

CREATE CONSTRAINT TRIGGER transaction_receipt_save_barrier_owner_ck
AFTER INSERT ON dnd_runtime.transaction_receipt
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION dnd_runtime.assert_save_barrier_owner_membership();

CREATE CONSTRAINT TRIGGER checkpoint_commit_save_barrier_owner_ck
AFTER INSERT ON dnd_runtime.checkpoint_commit
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION dnd_runtime.assert_save_barrier_owner_membership();

CREATE CONSTRAINT TRIGGER checkpoint_owner_state_save_barrier_owner_ck
AFTER INSERT ON dnd_runtime.checkpoint_owner_state
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION dnd_runtime.assert_save_barrier_owner_membership();

-- Append-only tables: 'event_commit', 'applied_event_ledger', 'transaction_receipt',
-- 'checkpoint_commit', 'checkpoint_owner_state', 'rng_state_receipt'.
CREATE FUNCTION dnd_runtime.reject_committed_row_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS E'BEGIN\n    RAISE EXCEPTION ''DND_RUNTIME_APPEND_ONLY:%'', TG_TABLE_NAME\n        USING ERRCODE = ''55000''\073\nEND\073';

CREATE TRIGGER event_commit_append_only BEFORE UPDATE OR DELETE ON dnd_runtime.event_commit FOR EACH ROW EXECUTE FUNCTION dnd_runtime.reject_committed_row_mutation();
CREATE TRIGGER applied_event_ledger_append_only BEFORE UPDATE OR DELETE ON dnd_runtime.applied_event_ledger FOR EACH ROW EXECUTE FUNCTION dnd_runtime.reject_committed_row_mutation();
CREATE TRIGGER transaction_receipt_append_only BEFORE UPDATE OR DELETE ON dnd_runtime.transaction_receipt FOR EACH ROW EXECUTE FUNCTION dnd_runtime.reject_committed_row_mutation();
CREATE TRIGGER checkpoint_commit_append_only BEFORE UPDATE OR DELETE ON dnd_runtime.checkpoint_commit FOR EACH ROW EXECUTE FUNCTION dnd_runtime.reject_committed_row_mutation();
CREATE TRIGGER checkpoint_owner_state_append_only BEFORE UPDATE OR DELETE ON dnd_runtime.checkpoint_owner_state FOR EACH ROW EXECUTE FUNCTION dnd_runtime.reject_committed_row_mutation();
CREATE TRIGGER rng_state_receipt_append_only BEFORE UPDATE OR DELETE ON dnd_runtime.rng_state_receipt FOR EACH ROW EXECUTE FUNCTION dnd_runtime.reject_committed_row_mutation();

COMMENT ON SCHEMA dnd_runtime IS 'Runtime-state migration candidate. FILE_PRIMARY remains authoritative until separate parity/cutover approval.';
COMMENT ON TABLE dnd_runtime.session_revision IS 'Current structured runtime revision pointer. Existence does not authorize SQL_PRIMARY or semantic-authority reassignment.';
COMMENT ON TABLE dnd_runtime.event_commit IS 'Immutable committed EVENT_ID envelope paired transactionally with AEL, transaction receipt, and checkpoint.';
COMMENT ON TABLE dnd_runtime.applied_event_ledger IS 'Exactly-one Applied Event Ledger row per committed event/logical revision.';
COMMENT ON TABLE dnd_runtime.transaction_receipt IS 'Atomic owner-set receipt for a committed event, owner membership is deferred-bound to checkpoint owner-state membership and parity digest semantics.';
COMMENT ON TABLE dnd_runtime.checkpoint_commit IS 'Save-barrier checkpoint bound to the same committed EVENT_ID/logical revision, owner_binding_count is deferred-bound to actual checkpoint owner-state cardinality.';
COMMENT ON TABLE dnd_runtime.checkpoint_owner_state IS 'Owner-state hash bindings for a committed checkpoint, membership is deferred-bound to the transaction owner set, no topology or knowledge semantics are stored here.';
COMMENT ON TABLE dnd_runtime.rng_state_receipt IS 'Committed RNG cursor/state receipt, append-only uniqueness prevents a second receipt for the same stream/revision.';

COMMIT;
