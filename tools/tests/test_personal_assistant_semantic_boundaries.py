import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.audit_personal_assistant_semantic_boundaries import (  # noqa: E402
    CHALLENGES,
    assess,
    audit,
)


class SemanticBoundaryTests(unittest.TestCase):
    def test_original_counterexamples_and_scope_negatives_are_checked(self):
        result = audit()
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["model_calls"], 0)
        self.assertEqual(len(result["observations"]), 12)

    def test_action_role_alone_cannot_certify_content(self):
        row = audit()["observations"][1]
        proof = copy.deepcopy(row["semantic_evidence"])
        proof["content_evidence"]["claims"]["polarity"] = "requested"
        self.assertFalse(assess(proof, row["request"], CHALLENGES[1][1], CHALLENGES[1][2]))

    def test_unverified_content_cannot_be_claimed_as_verified(self):
        row = audit()["observations"][6]
        proof = copy.deepcopy(row["semantic_evidence"])
        proof["content_evidence"]["status"] = "verified"
        self.assertFalse(assess(proof, row["request"], CHALLENGES[6][1], None))
