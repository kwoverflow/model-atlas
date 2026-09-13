from __future__ import annotations

import datetime as dt
import uuid
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import (
    OperationalAlertDelivery,
    OperationalAlertIncident,
)
from app.schemas import (
    OperationalAlertIncidentActionRead,
)
from app.services.operator_identity import SignerIdentity
from app.validators import DomainValidationError

from .escalation import (
    _append_incident_action,
)
from .paging import (
    _create_delivery,
)
from .permissions import (
    _assert_can_administer,
)
from .read_models import (
    _incident_action_read,
)
from .utils import (
    _utc,
)


def create_operational_test_delivery(
    db: Session,
    *,
    settings: Settings,
    signer_identity: SignerIdentity,
    severity: str,
    reason: str,
    now: dt.datetime | None = None,
) -> OperationalAlertDelivery:
    _assert_can_administer(signer_identity)
    if not settings.operational_paging_enabled:
        raise DomainValidationError("operational paging delivery is disabled")
    observed_at = _utc(now or dt.datetime.now(dt.UTC)).replace(microsecond=0)
    incident = OperationalAlertIncident(
        active_key=None,
        alert_key=f"paging_delivery_test:{uuid.uuid4().hex}",
        source_type="test",
        severity=severity,
        route=("model-atlas-critical" if severity == "critical" else "model-atlas-warning"),
        summary=reason,
        status="resolved",
        opened_at=observed_at,
        last_seen_at=observed_at,
        resolved_at=observed_at,
        occurrence_count=1,
        transition_version=1,
        latest_context_json={
            "test": True,
            "requested_by": signer_identity.to_json(),
        },
    )
    db.add(incident)
    db.flush()
    delivery = _create_delivery(
        db,
        incident=incident,
        transition_type="test",
        settings=settings,
        observed_at=observed_at,
    )
    db.commit()
    db.refresh(delivery)
    return delivery


def record_operational_incident_action(
    db: Session,
    *,
    incident_id: UUID,
    signer_identity: SignerIdentity,
    action_type: str,
    reason: str,
    assignee: str | None = None,
    now: dt.datetime | None = None,
) -> OperationalAlertIncidentActionRead:
    _assert_can_administer(signer_identity)
    observed_at = _utc(now or dt.datetime.now(dt.UTC)).replace(microsecond=0)
    incident = db.scalar(
        select(OperationalAlertIncident)
        .where(OperationalAlertIncident.id == incident_id)
        .with_for_update()
    )
    if incident is None:
        raise DomainValidationError("operational incident was not found")
    if action_type not in {"acknowledged", "assigned", "note"}:
        raise DomainValidationError("operational incident action type is invalid")
    if action_type != "assigned" and assignee is not None:
        raise DomainValidationError("assignee is only valid for assigned actions")
    if incident.status != "open" and action_type != "note":
        raise DomainValidationError("only open incidents can be acknowledged or assigned")
    if action_type == "acknowledged":
        if incident.acknowledged_at is not None:
            raise DomainValidationError("operational incident is already acknowledged")
        incident.acknowledged_at = observed_at
        incident.acknowledged_by_identity_json = signer_identity.to_json()
    elif action_type == "assigned":
        if not assignee:
            raise DomainValidationError("assignee is required for assigned actions")
        incident.assigned_to = assignee

    action = _append_incident_action(
        db,
        incident=incident,
        action_type=action_type,
        reason=reason,
        assignee=assignee,
        actor_identity=signer_identity.to_json(),
        identity_verified=signer_identity.identity_verified,
        observed_at=observed_at,
    )
    db.commit()
    db.refresh(action)
    return _incident_action_read(action)
