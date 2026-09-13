from __future__ import annotations

import argparse
import logging
import os
import platform
import socket
import threading
import time
import uuid
from uuid import UUID

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.services.agent_jobs import (
    claim_agent_job,
    enqueue_checkpoint_reconciliation_job,
    enqueue_oidc_session_cleanup_job,
    enqueue_operational_observability_cycle_job,
    heartbeat_agent_job,
    heartbeat_agent_worker,
    mark_agent_worker_stopped,
    process_claimed_agent_job,
    record_agent_worker_outcome,
    register_agent_worker,
    system_worker_identity,
)
from app.services.trust_source_scheduler import enqueue_due_trust_source_sync_jobs
from app.validators import DomainValidationError

logger = logging.getLogger(__name__)


class LeaseHeartbeat:
    def __init__(
        self,
        *,
        worker_id: str,
        job_id: UUID,
        lease_token: str,
        lease_seconds: int,
        heartbeat_seconds: float,
    ) -> None:
        self.worker_id = worker_id
        self.job_id = job_id
        self.lease_token = lease_token
        self.lease_seconds = lease_seconds
        self.heartbeat_seconds = heartbeat_seconds
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            name=f"agent-job-heartbeat-{str(job_id)[:8]}",
            daemon=True,
        )

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=max(2.0, self.heartbeat_seconds + 1.0))

    def _run(self) -> None:
        while not self._stop.wait(self.heartbeat_seconds):
            try:
                with SessionLocal() as db:
                    heartbeat_agent_job(
                        db,
                        job_id=self.job_id,
                        lease_token=self.lease_token,
                        lease_seconds=self.lease_seconds,
                    )
                with SessionLocal() as db:
                    heartbeat_agent_worker(
                        db,
                        worker_id=self.worker_id,
                        current_job_id=self.job_id,
                    )
            except DomainValidationError:
                return
            except Exception:
                logger.exception("Agent worker heartbeat failed")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Model Atlas Agent job worker.")
    parser.add_argument("--once", action="store_true", help="Process at most one job.")
    parser.add_argument("--worker-id", default=None)
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    settings = get_settings()
    worker_id = args.worker_id or (
        f"{socket.gethostname()}-{uuid.uuid4().hex[:8]}"
    )
    with SessionLocal() as db:
        register_agent_worker(
            db,
            worker_id=worker_id,
            metadata_json={
                "hostname": socket.gethostname(),
                "pid": os.getpid(),
                "platform": platform.platform(),
                "job_contract_version": "agent-durable-job-v1",
                "trust_source_scheduler_enabled": (
                    settings.trust_source_scheduler_enabled
                ),
                "oidc_session_cleanup_enabled": (
                    settings.oidc_session_cleanup_enabled
                ),
                "operational_snapshot_enabled": (
                    settings.operational_snapshot_enabled
                ),
                "operational_paging_enabled": (
                    settings.operational_paging_enabled
                ),
            },
        )
    logger.info("Agent worker %s started", worker_id)

    try:
        while True:
            with SessionLocal() as db:
                if settings.trust_source_scheduler_enabled:
                    enqueue_due_trust_source_sync_jobs(
                        db,
                        scheduler_id=worker_id,
                        signer_identity=system_worker_identity(worker_id),
                        lease_seconds=settings.trust_source_schedule_lease_seconds,
                        batch_size=settings.trust_source_scheduler_batch_size,
                    )
                now_bucket = (
                    int(time.time())
                    // settings.agent_reconciliation_interval_seconds
                )
                enqueue_checkpoint_reconciliation_job(
                    db,
                    schedule_key=f"interval-{now_bucket}",
                    signer_identity=system_worker_identity(worker_id),
                )
                if settings.oidc_session_cleanup_enabled:
                    cleanup_bucket = (
                        int(time.time())
                        // settings.oidc_session_cleanup_interval_seconds
                    )
                    enqueue_oidc_session_cleanup_job(
                        db,
                        schedule_key=f"interval-{cleanup_bucket}",
                        signer_identity=system_worker_identity(worker_id),
                        retention_days=settings.oidc_session_retention_days,
                        batch_size=settings.oidc_session_cleanup_batch_size,
                        reason="Scheduled browser session retention cleanup",
                    )
                if settings.operational_snapshot_enabled:
                    observability_bucket = (
                        int(time.time())
                        // settings.operational_snapshot_interval_seconds
                    )
                    enqueue_operational_observability_cycle_job(
                        db,
                        schedule_key=f"interval-{observability_bucket}",
                        signer_identity=system_worker_identity(worker_id),
                        reason="Scheduled operational metric and SLO capture",
                    )
                job = claim_agent_job(
                    db,
                    worker_id=worker_id,
                    lease_seconds=settings.agent_job_lease_seconds,
                )
            if job is None or job.lease_token is None:
                with SessionLocal() as db:
                    heartbeat_agent_worker(
                        db,
                        worker_id=worker_id,
                        current_job_id=None,
                    )
                if args.once:
                    return
                time.sleep(settings.agent_worker_poll_seconds)
                continue

            with SessionLocal() as db:
                heartbeat_agent_worker(
                    db,
                    worker_id=worker_id,
                    current_job_id=job.id,
                )
            heartbeat = LeaseHeartbeat(
                worker_id=worker_id,
                job_id=job.id,
                lease_token=job.lease_token,
                lease_seconds=settings.agent_job_lease_seconds,
                heartbeat_seconds=settings.agent_job_heartbeat_seconds,
            )
            heartbeat.start()
            try:
                with SessionLocal() as db:
                    processed = process_claimed_agent_job(
                        db,
                        job_id=job.id,
                        lease_token=job.lease_token,
                    )
            finally:
                heartbeat.stop()
            with SessionLocal() as db:
                record_agent_worker_outcome(
                    db,
                    worker_id=worker_id,
                    job_status=processed.status,
                )
            logger.info(
                "Agent worker %s processed %s as %s",
                worker_id,
                processed.id,
                processed.status,
            )
            if args.once:
                return
    except KeyboardInterrupt:
        logger.info("Agent worker %s received shutdown", worker_id)
    finally:
        with SessionLocal() as db:
            mark_agent_worker_stopped(db, worker_id=worker_id)
        logger.info("Agent worker %s stopped", worker_id)


if __name__ == "__main__":
    main()
