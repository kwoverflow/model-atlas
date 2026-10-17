import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools import audit_personal_assistant_decision_semantics as audit_tool  # noqa: E402


class ExplanationAuditTests(unittest.TestCase):
    def test_safe_abstention_does_not_claim_false_sufficiency(self):
        with patch.object(
            audit_tool,
            "decision_evidence",
            return_value={
                "status": "insufficient",
                "reason": None,
            },
        ):
            result = audit_tool.audit()
        self.assertEqual(result["status"], "passed")
        self.assertFalse(any(row["false_sufficiency"] for row in result["observations"]))

    def test_consistent_but_factually_unrelated_explanation_is_rejected(self):
        with patch.object(
            audit_tool,
            "decision_evidence",
            return_value={
                "status": "grounded",
                "reason": "일정이 완료됐습니다.",
            },
        ):
            result = audit_tool.audit()
        self.assertEqual(result["status"], "counterexamples_found")
        self.assertTrue(all(row["false_sufficiency"] for row in result["observations"]))

    def test_matching_summary_facts_are_checked_separately_from_sufficiency_flag(self):
        proofs = [
            {"status": "grounded", "reason": facts[0]} for _, _, facts in audit_tool.CHALLENGES
        ]
        with patch.object(audit_tool, "decision_evidence", side_effect=proofs):
            result = audit_tool.audit()
        self.assertEqual(result["status"], "passed")
        self.assertTrue(all(row["facts_present"] for row in result["observations"]))
