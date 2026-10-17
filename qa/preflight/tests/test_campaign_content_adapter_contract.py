import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CONTRACT_PATH = ROOT / "docs" / "architecture" / "CAMPAIGN_CONTENT_ADAPTER_CONTRACT_v1.md"

REQUIRED_MARKERS = {
    "STATUS: CANDIDATE_CONTRACT_ONLY",
    "PUBLIC_PROVIDER_IDENTITY: OPAQUE_ONLY",
    "PRIVATE_TO_PUBLIC_REPOSITORY_FLOW: FORBIDDEN",
    "PUBLIC_RESOLVED_CONTENT_PERSISTENCE: FORBIDDEN",
    "PLAYER_FACING_UNPROJECTED_PRIVATE_PAYLOAD: FORBIDDEN",
    "ORIGINAL_PRIVATE_DISPLAY_CONTENT_ALLOWED_AT_RUNTIME: TRUE",
    "PUBLIC_GENERIC_REQUEST -> PRIVATE_PROVIDER -> AUTHORIZED_PRIVATE_RUNTIME_PAYLOAD",
    "RESOLVED_PRIVATE_PAYLOAD -> PUBLIC_REPOSITORY_OR_PUBLIC_BUILD_ARTIFACT",
    "BINDING_NOT_FOUND",
    "BINDING_AMBIGUOUS",
    "BINDING_REVISION_MISMATCH",
    "CONTENT_KIND_MISMATCH",
    "SCOPE_DENIED",
    "PROVIDER_UNAVAILABLE",
    "PRIVATE_PAYLOAD_VALIDATION_FAILED",
}

EXPECTED_ID_REGEX = (
    r"^[a-z][a-z0-9_]{1,31}:[a-z0-9][a-z0-9._-]{0,63}:"
    r"[a-z0-9][a-z0-9._-]{0,127}$"
)

FORBIDDEN_IDENTITY_PATTERNS = {
    "url": re.compile(r"https?://", re.IGNORECASE),
    "email": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    "uuid": re.compile(
        r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
        r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
    ),
    "sha1_like": re.compile(r"\b[0-9a-f]{40}\b", re.IGNORECASE),
    "sha256_like": re.compile(r"\b[0-9a-f]{64}\b", re.IGNORECASE),
}

GENERIC_EXAMPLE_IDS = [
    "campaign:pkg01:campaign_001",
    "location:pkg01:loc_0042",
    "entity:pkg01:entity_0017",
]


class CampaignContentAdapterContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = CONTRACT_PATH.read_text(encoding="utf-8")

    def test_required_public_private_boundary_markers_present(self):
        for marker in REQUIRED_MARKERS:
            self.assertIn(marker, self.contract)

    def test_contract_contains_exact_generic_id_grammar(self):
        self.assertIn(f"ID_REGEX: {EXPECTED_ID_REGEX}", self.contract)
        pattern = re.compile(EXPECTED_ID_REGEX)
        for value in GENERIC_EXAMPLE_IDS:
            self.assertRegex(value, pattern)
            self.assertIn(value, self.contract)

    def test_public_contract_contains_no_concrete_provider_identity_material(self):
        for label, pattern in FORBIDDEN_IDENTITY_PATTERNS.items():
            self.assertIsNone(
                pattern.search(self.contract),
                msg=f"public adapter contract contains forbidden {label} material",
            )

    def test_contract_keeps_display_content_private_but_runtime_usable(self):
        self.assertIn("resolved private names or narrative MAY be used in the authorized game runtime", self.contract)
        self.assertIn("resolved private content MUST NOT be committed back into the public engine repository", self.contract)
        self.assertIn("public code MUST NOT embed a private binding table", self.contract)

    def test_contract_preserves_player_knowledge_boundary(self):
        self.assertIn("player-knowledge projection and leak-preoutput gate", self.contract)
        self.assertIn("The adapter MUST NOT create a bypass", self.contract)
        self.assertIn("unprojected private payload is not directly rendered to a player", self.contract)

    def test_contract_is_not_new_authority_or_mutation_owner(self):
        self.assertIn("This contract is a data-boundary contract, not a new authority owner.", self.contract)
        self.assertIn("gameplay-state mutation by the content provider", self.contract)
        self.assertIn("topology mutation by display content", self.contract)
        self.assertIn("player-knowledge expansion", self.contract)
        self.assertIn("source-of-truth replacement", self.contract)

    def test_binding_identity_and_revision_are_explicit(self):
        self.assertIn("(campaign_id, content_id, binding_revision)", self.contract)
        self.assertIn("`binding_revision` is explicit and immutable", self.contract)
        self.assertIn("Unknown versions fail closed.", self.contract)


if __name__ == "__main__":
    unittest.main()
