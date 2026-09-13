"""Local PostgreSQL workflow QA with synthetic proposals, never participant or model accuracy."""

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

from smoke_request_scenarios import call, official

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.services.request_workflow_catalog import cases, catalog  # noqa: E402
from app.services.structured_ticket_contract import digest  # noqa: E402


def run_case(case, *, wrong=False, abandon=False):
    row = call(
        "/request-workflows/attempts",
        "POST",
        {
            "task_id": case["id"],
            "source": "automated_qa",
        },
        expected=201,
    )
    path = f"/request-workflows/attempts/{row['id']}"
    key = case["expected"]
    if key["decision"] == "execute" and not abandon:
        draft = {
            "original_request": case["request"],
            "query": key["query"],
            "priority": {"mode": "set", "value": "high"} if wrong else key["priority"],
        }
        request = call(
            path + "/request",
            "POST",
            {
                "expected_revision": row["revision"],
                "draft": draft,
            },
            expected=201,
        )
        contract_path = f"/structured-requests/{request['id']}"
        binding = {
            "expected_revision": request["revision"],
            "expected_hash": request["contract_hash"],
        }
        call(contract_path + "/confirm", "POST", {**binding, "acknowledged": True})
        arguments = {"query": draft["query"]}
        if draft["priority"]["mode"] == "set":
            arguments["priority"] = draft["priority"]["value"]
        check = call(
            contract_path + "/checks",
            "POST",
            {
                **binding,
                "proposal": json.dumps(
                    {"tool_name": "create_ticket", "arguments": arguments}
                ),
            },
            expected=201,
        )
        assert check["verdict"]["allowed"]
        call(contract_path + f"/checks/{check['id']}/execute", "POST")
    row = call(path)
    payload = {
        "expected_revision": row["revision"],
        "request_state_hash": row["request_state_hash"],
        "disposition": "abandoned"
        if abandon
        else "clarification_requested"
        if key["decision"] == "clarify"
        else "finished",
        "assistance": "not_applicable",
        "acknowledged": True,
        "note": "Automated API QA. Synthetic proposals; no participant or model inference."
        + (" Deliberate misconfirmation." if wrong else "")
        + (" Deliberate abandonment." if abandon else ""),
    }
    result = call(path + "/finish", "POST", payload)
    assessment = (
        "abandoned" if abandon else "does_not_match_task" if wrong else "matches_task"
    )
    assert result["result"]["assessment"] == assessment
    assert result["result"]["metrics"]["model_proposal_count"] == 0
    assert not result["gate_evidence"] and not result["human_review_verified"]
    replay = call(path + "/finish", "POST", payload)
    assert replay["replayed"] and replay["result"] == result["result"]
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("refusing to overwrite previous QA evidence")
    assert call("/request-workflows/catalog")["hash"] == catalog()["hash"]
    before = official()
    studies = call("/request-scenarios/studies?limit=50")
    contracts = call("/structured-requests?limit=50")
    prior = {r["id"]: digest(r) for r in contracts}
    attempts = [run_case(case) for case in cases()]
    attempts.extend(
        [run_case(cases()[0], wrong=True), run_case(cases()[0], abandon=True)]
    )
    after = official()
    assert before == after
    assert studies == call("/request-scenarios/studies?limit=50")
    for request_id, before_hash in prior.items():
        assert digest(call(f"/structured-requests/{request_id}")) == before_hash
    report = {
        "created_at": dt.datetime.now(dt.UTC).isoformat(),
        "status": "passed",
        "scope": "automated_api_qa_real_contract_services_synthetic_proposals",
        "model_calls": 0,
        "human_review_verified": False,
        "gate_evidence": False,
        "attempts": attempts,
        "official_before": before,
        "official_after": after,
        "prior_studies_unchanged": len(studies),
        "prior_contracts_unchanged": len(prior),
        "expected_observation_counts": {
            "matches_task": 10,
            "does_not_match_task": 1,
            "abandoned": 1,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(
        json.dumps(
            {"status": "passed", "attempts": len(attempts), "official": after},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
