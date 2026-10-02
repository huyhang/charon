import pytest

from charon.domain.api_keys import KEY_PREFIX, display_prefix, generate_key, hash_key
from charon.domain.models import Principal, Role
from charon.errors import ConflictError, ForbiddenError, NotFoundError, UnauthorizedError
from charon.services.api_key_service import ANONYMOUS, BOOTSTRAP_ADMIN, ApiKeyService
from tests.unit.fakes import FakeClock, InMemoryApiKeyStore, SequentialIds

ADMIN_KEY = "bootstrap-secret"


class Harness:
    def __init__(self, admin_key: str | None = ADMIN_KEY) -> None:
        self.store = InMemoryApiKeyStore()
        self.clock = FakeClock()
        self.service = ApiKeyService(
            self.store,
            admin_key,
            clock=self.clock,
            new_id=SequentialIds("key"),
            new_secret=SequentialIds("chk_longsecret"),
        )


def test_generate_key_is_prefixed_and_unique() -> None:
    first, second = generate_key(), generate_key()
    assert first.startswith(KEY_PREFIX)
    assert first != second
    assert len(first) > 40


def test_hash_and_prefix() -> None:
    assert hash_key("abc") == hash_key("abc") != hash_key("abd")
    assert display_prefix("chk_0123456789abcdef") == "chk_01234567"


def test_create_stores_only_hash() -> None:
    h = Harness()
    issued = h.service.create("phone", Role.CLIENT)
    stored = h.store.keys["key-1"]
    assert issued.secret == "chk_longsecret-1"
    assert stored.key_hash == hash_key("chk_longsecret-1")
    assert issued.secret not in stored.model_dump_json()
    assert (stored.name, stored.role, stored.prefix) == ("phone", Role.CLIENT, "chk_longsecr")


@pytest.mark.parametrize(
    ("presented", "expected"),
    [
        (ADMIN_KEY, BOOTSTRAP_ADMIN),
        ("chk_longsecret-1", Principal(name="phone", role=Role.CLIENT, key_id="key-1")),
        ("chk_longsecret-2", Principal(name="ops", role=Role.ADMIN, key_id="key-2")),
    ],
)
def test_authenticate_valid_keys(presented: str, expected: Principal) -> None:
    h = Harness()
    h.service.create("phone", Role.CLIENT)
    h.service.create("ops", Role.ADMIN)
    assert h.service.authenticate(presented) == expected


@pytest.mark.parametrize("presented", [None, "", "wrong", "chk_longsecret-1x", "bootstrap-secret "])
def test_authenticate_rejects_bad_keys(presented: str | None) -> None:
    h = Harness()
    h.service.create("phone", Role.CLIENT)
    with pytest.raises(UnauthorizedError):
        h.service.authenticate(presented)


def test_authenticate_handles_non_ascii_header() -> None:
    with pytest.raises(UnauthorizedError):
        Harness().service.authenticate("clé")


@pytest.mark.parametrize("presented", [None, "anything"])
def test_auth_disabled_without_admin_key(presented: str | None) -> None:
    h = Harness(admin_key=None)
    assert h.service.auth_enabled is False
    assert h.service.authenticate(presented) == ANONYMOUS


def test_revoked_key_is_rejected_immediately() -> None:
    h = Harness()
    issued = h.service.create("phone", Role.CLIENT)
    h.service.authenticate(issued.secret)
    h.clock.advance(5)
    revoked = h.service.revoke(issued.api_key.id)
    assert revoked.revoked_at == h.clock()
    with pytest.raises(UnauthorizedError):
        h.service.authenticate(issued.secret)


def test_revoke_is_idempotent() -> None:
    h = Harness()
    key_id = h.service.create("phone", Role.CLIENT).api_key.id
    first = h.service.revoke(key_id)
    h.clock.advance(5)
    assert h.service.revoke(key_id).revoked_at == first.revoked_at


@pytest.mark.parametrize("action", [lambda s: s.get("nope"), lambda s: s.revoke("nope")])
def test_unknown_key_raises_not_found(action) -> None:
    with pytest.raises(NotFoundError):
        action(Harness().service)


@pytest.mark.parametrize(
    ("admin_key", "role", "error"),
    [
        (ADMIN_KEY, Role.ADMIN, None),
        (ADMIN_KEY, Role.CLIENT, ForbiddenError),
        (None, Role.ADMIN, ConflictError),
    ],
)
def test_authorize_admin(admin_key: str | None, role: Role, error: type | None) -> None:
    service = Harness(admin_key).service
    principal = Principal(name="p", role=role)
    if error is None:
        service.authorize_admin(principal)
    else:
        with pytest.raises(error):
            service.authorize_admin(principal)
