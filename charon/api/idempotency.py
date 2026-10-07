"""Lets clients retry a create safely by sending an Idempotency-Key header."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated

from fastapi import Header
from pydantic import BaseModel

from charon.domain.models import Actor
from charon.services.idempotency_service import IdempotencyService

IdempotencyKey = Annotated[
    str | None,
    Header(
        alias="Idempotency-Key",
        max_length=255,
        description=(
            "Any unique string, e.g. a UUID. Repeating a request with the same key returns "
            "what the first one created (with status 200) instead of creating it again. "
            "Keys belong to the API key that sent them and are remembered for a day."
        ),
    ),
]


@dataclass(frozen=True)
class Outcome[T]:
    value: T
    # False when the request returned something that already existed.
    created: bool


def caller_scope(resource: str, actor: Actor) -> str:
    """Keys are per API key, so two clients that happen to pick the same key can't collide."""
    return f"{resource}:{actor.key_id or actor.name}"


def run_once[T](
    idempotency: IdempotencyService,
    scope: str,
    key: str | None,
    body: BaseModel,
    create: Callable[[], Outcome[T]],
    load: Callable[[str], T],
    id_of: Callable[[T], str],
) -> Outcome[T]:
    """Create something, or return what an earlier request with the same key created."""
    if key is None:
        return create()
    payload = body.model_dump_json()
    with idempotency.exclusive(scope, key):
        earlier = idempotency.recall(scope, key, payload)
        if earlier is not None:
            return Outcome(load(earlier), created=False)
        outcome = create()
        idempotency.remember(scope, key, payload, id_of(outcome.value))
    return outcome
