"""Issues, revokes and authenticates API keys."""

import secrets
from collections.abc import Callable
from dataclasses import dataclass

from charon.domain.api_keys import display_prefix, generate_key, hash_key
from charon.domain.models import ApiKey, Principal, Role
from charon.errors import ConflictError, ForbiddenError, NotFoundError, UnauthorizedError
from charon.ports.clock import Clock, IdFactory, new_uuid, utc_now
from charon.ports.stores import ApiKeyStore

KeyFactory = Callable[[], str]

ANONYMOUS = Principal(name="anonymous", role=Role.ADMIN)
BOOTSTRAP_ADMIN = Principal(name="bootstrap-admin", role=Role.ADMIN)


@dataclass(frozen=True)
class IssuedKey:
    api_key: ApiKey
    secret: str


class ApiKeyService:
    """Auth is enabled only when a bootstrap admin key is configured.

    The bootstrap key lives in the environment, not the store, so it cannot be
    revoked through the API; rotate it by changing the environment.
    """

    def __init__(
        self,
        keys: ApiKeyStore,
        admin_key: str | None,
        clock: Clock = utc_now,
        new_id: IdFactory = new_uuid,
        new_secret: KeyFactory = generate_key,
    ) -> None:
        self._keys = keys
        self._admin_key = admin_key
        self._clock = clock
        self._new_id = new_id
        self._new_secret = new_secret

    @property
    def auth_enabled(self) -> bool:
        return self._admin_key is not None

    def authenticate(self, presented: str | None) -> Principal:
        if self._admin_key is None:
            return ANONYMOUS
        if presented is None:
            raise UnauthorizedError("unauthorized", "missing API key")
        if secrets.compare_digest(presented.encode(), self._admin_key.encode()):
            return BOOTSTRAP_ADMIN
        key = self._keys.find_by_hash(hash_key(presented))
        if key is None or key.revoked:
            raise UnauthorizedError("unauthorized", "invalid or revoked API key")
        return Principal(name=key.name, role=key.role, key_id=key.id)

    def authorize_admin(self, principal: Principal) -> None:
        if not self.auth_enabled:
            raise ConflictError("auth_disabled", "set CHARON_ADMIN_API_KEY to manage API keys")
        if principal.role is not Role.ADMIN:
            raise ForbiddenError("forbidden", "this action requires an admin key")

    def create(self, name: str, role: Role) -> IssuedKey:
        secret = self._new_secret()
        key = ApiKey(
            id=self._new_id(),
            name=name,
            role=role,
            prefix=display_prefix(secret),
            key_hash=hash_key(secret),
            created_at=self._clock(),
        )
        self._keys.add(key)
        return IssuedKey(api_key=key, secret=secret)

    def list(self) -> list[ApiKey]:
        return self._keys.list()

    def get(self, key_id: str) -> ApiKey:
        key = self._keys.get(key_id)
        if key is None:
            raise NotFoundError("api_key_not_found", f"API key {key_id} does not exist")
        return key

    def revoke(self, key_id: str) -> ApiKey:
        """Revoke a key. Revoking an already-revoked key is a no-op."""
        key = self.get(key_id)
        if key.revoked:
            return key
        revoked = key.model_copy(update={"revoked_at": self._clock()})
        self._keys.update(revoked)
        return revoked
