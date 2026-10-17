import copy
import dataclasses
import inspect
import tempfile
import unittest
from pathlib import Path

from qa.preflight.tests.test_live_visual_activation_contract import request
from qa.preflight.tests.test_visual_runtime_promotion_candidate import (
    SESSION_ID,
    _test_signer_and_verifier,
    runtime_fixture,
)
from runtime.runtime_host_request_context import (
    RuntimeHostRequestContext,
    cancel_runtime_host_request_context,
    issue_runtime_host_request_context,
    runtime_host_request_context_authority_id,
)
from runtime.visual_runtime_bridge import (
    RuntimeVisualBridge,
    materialize_runtime_authority_bindings,
)


class AuthorityGrantRequestBindingRegressionTests(unittest.TestCase):
    def _materialization_args(self, fixture, req):
        (
            _,
            _,
            _,
            record,
            checkpoint,
            ael,
            player,
            ledger,
            grant,
            _,
        ) = fixture
        return (
            grant,
            SESSION_ID,
            record["RECEIPT_ID"],
            checkpoint,
            ael,
            player,
            ledger,
            req["SOURCE_STATE_EPOCH"],
            req,
        )

    def test_production_materialization_requires_host_context_not_request_id_string(self):
        params = list(inspect.signature(materialize_runtime_authority_bindings).parameters)
        self.assertEqual(params[0], "grant_envelope")
        self.assertEqual(params[1], "host_request_context")

        req = request(False)
        with tempfile.TemporaryDirectory() as tmp:
            fixture = runtime_fixture(req, Path(tmp) / "ledger.sqlite")
            args = self._materialization_args(fixture, req)
            grant = args[0]
            with self.assertRaises(TypeError) as error:
                materialize_runtime_authority_bindings(
                    grant,
                    "REQ-CALLER-SELECTED",
                    *args[1:],
                )
            self.assertIn("RUNTIME_HOST_REQUEST_CONTEXT_REQUIRED", str(error.exception))

    def test_forged_context_object_without_host_mac_is_rejected(self):
        req = request(False)
        with tempfile.TemporaryDirectory() as tmp:
            fixture = runtime_fixture(req, Path(tmp) / "ledger.sqlite")
            args = self._materialization_args(fixture, req)
            grant = args[0]
            forged = RuntimeHostRequestContext(
                request_id=grant.claims.request_id,
                session_id=SESSION_ID,
                activation_id=req["ACTIVATION_ID"],
                source_revision=req["SOURCE_STATE_EPOCH"],
                issued_at_unix=1,
                nonce="FORGED-NONCE",
                authority_id=runtime_host_request_context_authority_id(),
                mac_hex="00" * 32,
            )
            with self.assertRaises(PermissionError) as error:
                materialize_runtime_authority_bindings(
                    grant,
                    forged,
                    *args[1:],
                )
            self.assertIn("RUNTIME_HOST_REQUEST_CONTEXT_MAC_INVALID", str(error.exception))

    def test_valid_grant_a_cannot_cross_into_actual_host_transaction_b(self):
        req = request(False)
        with tempfile.TemporaryDirectory() as tmp:
            fixture = runtime_fixture(req, Path(tmp) / "ledger.sqlite")
            args = self._materialization_args(fixture, req)
            grant_a = args[0]
            context_b = issue_runtime_host_request_context(
                SESSION_ID,
                req["ACTIVATION_ID"],
                req["SOURCE_STATE_EPOCH"],
            )
            try:
                self.assertNotEqual(context_b.request_id, grant_a.claims.request_id)
                with self.assertRaises(PermissionError) as error:
                    materialize_runtime_authority_bindings(
                        grant_a,
                        context_b,
                        *args[1:],
                    )
                self.assertIn("AUTHORITY_GRANT_REQUEST_ID_MISMATCH", str(error.exception))
            finally:
                cancel_runtime_host_request_context(context_b)

    def test_cancelled_host_transaction_rejects_matching_old_signed_grant(self):
        req = request(False)
        with tempfile.TemporaryDirectory() as tmp:
            fixture = runtime_fixture(req, Path(tmp) / "ledger.sqlite")
            args = self._materialization_args(fixture, req)
            context = issue_runtime_host_request_context(
                SESSION_ID,
                req["ACTIVATION_ID"],
                req["SOURCE_STATE_EPOCH"],
            )
            signer, _ = _test_signer_and_verifier()
            matching_claims = dataclasses.replace(
                args[0].claims,
                request_id=context.request_id,
            )
            matching_grant = signer.sign(matching_claims)
            cancel_runtime_host_request_context(context)

            with self.assertRaises(PermissionError) as error:
                materialize_runtime_authority_bindings(
                    matching_grant,
                    context,
                    *args[1:],
                )
            self.assertIn("RUNTIME_HOST_REQUEST_CONTEXT_NOT_ACTIVE", str(error.exception))

    def test_consumed_host_transaction_context_cannot_materialize_twice(self):
        req = request(False)
        with tempfile.TemporaryDirectory() as tmp:
            fixture = runtime_fixture(req, Path(tmp) / "ledger.sqlite")
            _, bindings, _, record, checkpoint, ael, player, ledger, grant, _ = fixture
            with self.assertRaises(PermissionError) as error:
                materialize_runtime_authority_bindings(
                    grant,
                    bindings.host_request_context,
                    SESSION_ID,
                    record["RECEIPT_ID"],
                    checkpoint,
                    ael,
                    player,
                    ledger,
                    req["SOURCE_STATE_EPOCH"],
                    req,
                )
            self.assertIn("RUNTIME_HOST_REQUEST_CONTEXT_NOT_ACTIVE", str(error.exception))
            self.assertEqual(ledger.snapshot().logical_index, 0)

    def test_binding_rejects_host_context_proof_tamper_after_materialization(self):
        req = request(False)
        with tempfile.TemporaryDirectory() as tmp:
            _, bindings, *_ = runtime_fixture(req, Path(tmp) / "ledger.sqlite")
            forged_context = dataclasses.replace(
                bindings.host_request_context,
                nonce="RHNONCE-TAMPERED",
            )
            forged = copy.copy(bindings)
            object.__setattr__(forged, "host_request_context", forged_context)
            with self.assertRaises(PermissionError) as error:
                RuntimeVisualBridge(forged)
            self.assertIn("RUNTIME_HOST_REQUEST_CONTEXT_MAC_INVALID", str(error.exception))


if __name__ == "__main__":
    unittest.main()
