from charon.domain.events import EventType
from charon.domain.models import Actor, Job
from charon.ports.events import EventLog


def record_status_change(events: EventLog, before: Job, after: Job, actor: Actor) -> None:
    """Record a job's move to a new status; nothing if the status stayed the same."""
    if before.status is after.status:
        return
    data: dict[str, object] = {"status": after.status, "previous": before.status}
    if after.name:
        data["name"] = after.name
    if after.error is not None:
        data["error_code"] = after.error.code
    events.record(EventType.JOB_STATUS_CHANGED, after.id, actor, **data)
