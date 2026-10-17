import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.audit_personal_assistant_completeness import verify_transport_failure  # noqa: E402


class TransportAuditTests(unittest.TestCase):
    def row(self):
        return {
            "runtime_error": "TimeoutError: timed out",
            "generated": {},
            "raw_output": "",
            "before": {"tasks": []},
            "after": {"tasks": []},
            "passed": False,
            "unchanged_before_approval": True,
            "sentinel_unchanged": True,
        }

    def test_recorded_timeout_is_not_a_successful_replay(self):
        verify_transport_failure(self.row(), {"error": "TimeoutError: timed out"})

    def test_response_or_fabricated_output_cannot_be_hidden_as_timeout(self):
        with self.assertRaises(AssertionError):
            verify_transport_failure(
                self.row(), {"error": "TimeoutError: timed out", "response": {}}
            )
        row = self.row()
        row["raw_output"] = "fabricated"
        with self.assertRaises(AssertionError):
            verify_transport_failure(row, {"error": "TimeoutError: timed out"})

    def test_mutation_or_success_claim_cannot_be_hidden_as_timeout(self):
        for key, value in (
            ("after", {"tasks": ["unexpected"]}),
            ("passed", True),
            ("sentinel_unchanged", False),
        ):
            row = self.row()
            row[key] = value
            with self.assertRaises(AssertionError):
                verify_transport_failure(row, {"error": "TimeoutError: timed out"})
