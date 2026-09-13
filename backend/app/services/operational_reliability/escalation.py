from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import (
    OperationalAlertDelivery,
    OperationalAlertIncident,
    OperationalAlertIncidentAction,
)

from .paging import (
    _create_delivery,
)
from .utils import (
    _canonical_hash,
    _utc,
)


def _maybe_escalate_incident(
    db: Session,
    *,
    incident: OperationalAlertIncident,
    settings: Settings,
    observed_at: dt.datetime,
) -> OperationalAlertDelivery | None:
    if (
        incident.status != "open"
        or incident.severity != "critical"
        or incident.acknowledged_at is not None
    ):
        return None
    age_seconds = max(0, int((observed_at - _utc(incident.opened_at)).total_seconds()))
    target_level = min(
        3,
        age_seconds // settings.operational_incident_escalation_seconds,
    )
    if target_level <= incident.escalation_level:
        return None
    incident.escalation_level = target_level
    incident.transition_version += 1
    _append_incident_action(
        db,
        incident=incident,
        action_type="escalated",
        reason=(
            f"Automatically escalated to level {target_level} after "
            f"{age_seconds} seconds without acknowledgement."
        ),
        assignee=None,
        actor_identity={
            "subject_id": "model-atlas-operational-controller",
            "display_name": "Operational Reliability Controller",
            "role": "system",
            "identity_provider": "model-atlas",
            "auth_source": "scheduled-control-loop",
            "identity_verified": True,
            "ticket_reference": None,
        },
        identity_verified=True,
        observed_at=observed_at,
    )
    if not settings.operational_paging_enabled:
        return None
    return _create_delivery(
        db,
        incident=incident,
        transition_type="escalated",
        settings=settings,
        observed_at=observed_at,
    )


def _append_incident_action(
    db: Session,
    *,
    incident: OperationalAlertIncident,
    action_type: str,
    reason: str,
    assignee: str | None,
    actor_identity: dict[str, Any],
    identity_verified: bool,
    observed_at: dt.datetime,
) -> OperationalAlertIncidentAction:
    previous = db.scalar(
        select(OperationalAlertIncidentAction)
        .where(OperationalAlertIncidentAction.incident_id == incident.id)
        .order_by(
            OperationalAlertIncidentAction.occurred_at.desc(),
            OperationalAlertIncidentAction.created_at.desc(),
        )
        .limit(1)
    )
    previous_hash = previous.action_hash if previous is not None else None
    canonical = {
        "incident_id": str(incident.id),
        "action_type": action_type,
        "reason": reason,
        "assignee": assignee,
        "actor_identity": actor_identity,
        "identity_verified": identity_verified,
        "occurred_at": observed_at.isoformat(),
        "previous_action_hash": previous_hash,
    }
    action = OperationalAlertIncidentAction(
        incident_id=incident.id,
        action_type=action_type,
        reason=reason,
        assignee=assignee,
        actor_identity_json=actor_identity,
        identity_verified=identity_verified,
        occurred_at=observed_at,
        previous_action_hash=previous_hash,
        action_hash=_canonical_hash(canonical),
        created_at=observed_at,
    )
    db.add(action)
    db.flush()
    return action
