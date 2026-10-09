"""One explicit-consent credential provider for chat and independent services."""
from enum import StrEnum
from contextlib import contextmanager
import re
from threading import RLock

from app.vault.types import Domain


class CredentialPolicy(StrEnum):
    ASK = "ask_each_session"
    SAVED = "save_encrypted"


class CredentialsRequired(RuntimeError):
    def __init__(self):
        super().__init__("Enter credentials for this connection session.")


def _connection(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", value):
        raise ValueError("Invalid provider connection identifier.")
    return value


class CredentialProvider:
    def __init__(self, session):
        self.session = session
        self._lock = RLock()
        self._policies = {}
        self._active = {}
        self._bindings = {}
        from app.state.storage import JsonStore
        self._policy_store = JsonStore(session.path("setup/credential_policies_v1.json"))
        stored = self._policy_store.load(default={})
        if not isinstance(stored, dict):
            raise ValueError("Invalid protected credential policies.")
        self._policies = {_connection(c): CredentialPolicy(p) for c, p in stored.items()}
        session.register(stop=self.end_all, clear=self._clear)

    def configure(self, connection, policy=CredentialPolicy.ASK):
        connection = _connection(connection)
        policy = CredentialPolicy(policy)
        with self.session.operation(), self._lock:
            proposed = {**self._policies, connection: policy}
            self._policy_store.save(proposed)
            if self._policies.get(connection) != policy:
                self.end(connection)
            self._policies = proposed

    def policy(self, connection):
        with self.session.operation(), self._lock:
            return self._policies.get(_connection(connection), CredentialPolicy.ASK)

    def bind(self, connection, consumer):
        """Consumer supplies cancel_current_request and set_api_key (which drains)."""
        connection = _connection(connection)
        with self.session.operation(), self._lock:
            if connection in self._bindings:
                raise ValueError("The provider connection already has a consumer.")
            self._bindings[connection] = consumer
            consumer.set_api_key("")

    def begin(self, connection):
        connection = _connection(connection)
        with self.session.operation() as vault, self._lock:
            if connection not in self._active:
                value = None
                if self._policies.get(connection, CredentialPolicy.ASK) == CredentialPolicy.SAVED:
                    key = connection + "/api_key"
                    if key in vault.list_paths(domain=Domain.CREDENTIAL):
                        value = bytearray(vault.read(key, domain=Domain.CREDENTIAL))
                self._active[connection] = value
                self._publish(connection)
            return self._active[connection] is not None

    def supply(self, connection, secret):
        connection = _connection(connection)
        raw = self._secret(secret)
        with self.session.operation(), self._lock:
            if connection not in self._active:
                raise CredentialsRequired()
            self._erase(connection)
            self._active[connection] = bytearray(raw)
            self._publish(connection)

    @staticmethod
    def _secret(secret):
        if not isinstance(secret, str) or not secret.strip() or len(secret.encode("utf-8")) > 16384:
            raise ValueError("Enter valid connection credentials.")
        return secret.strip().encode("utf-8")

    def save(self, connection, secret, *, consent=False, kind="api_key"):
        connection = _connection(connection)
        if consent is not True or kind not in {"api_key", "access_token", "refresh_token", "login_token"}:
            raise ValueError("Saving connection credentials requires explicit consent.")
        raw = self._secret(secret)
        with self.session.operation() as vault, self._lock:
            vault.put(connection + "/" + kind, raw, domain=Domain.CREDENTIAL)

    def saved_token(self, connection, *, kind):
        connection = _connection(connection)
        if kind not in {"access_token", "refresh_token", "login_token"}:
            raise ValueError("Invalid connection token kind.")
        with self.session.operation() as vault, self._lock:
            if self._policies.get(connection) != CredentialPolicy.SAVED or connection not in self._active:
                raise CredentialsRequired()
            return vault.read(connection + "/" + kind, domain=Domain.CREDENTIAL).decode("utf-8")

    def delete_saved(self, connection, *, kind="api_key"):
        connection = _connection(connection)
        if kind not in {"api_key", "access_token", "refresh_token", "login_token"}:
            raise ValueError("Invalid connection token kind.")
        with self.session.operation() as vault, self._lock:
            self.end(connection)
            key = connection + "/" + kind
            if key in vault.list_paths(domain=Domain.CREDENTIAL):
                vault.delete((key,), domain=Domain.CREDENTIAL)

    def _publish(self, connection):
        consumer = self._bindings.get(connection)
        if consumer is not None:
            value = self._active.get(connection)
            consumer.set_api_key(value.decode("utf-8") if value else "")

    def _erase(self, connection):
        old = self._active.get(connection)
        if old is not None:
            old[:] = b"\0" * len(old)

    def end(self, connection):
        connection = _connection(connection)
        with self._lock:
            consumer = self._bindings.get(connection)
            try:
                if consumer is not None and consumer.has_api_key:
                    cancel = getattr(consumer, "cancel_current_request", None)
                    if callable(cancel):
                        cancel()
                    consumer.set_api_key("")
            finally:
                self._erase(connection)
                self._active.pop(connection, None)

    def end_all(self):
        # Lifecycle release intentionally works after the storage gate is revoked.
        with self._lock:
            failed = False
            for connection in tuple(self._bindings.keys() | self._active.keys()):
                try:
                    self.end(connection)
                except Exception:
                    failed = True
            if failed:
                raise RuntimeError("Connection credentials could not be fully released.") from None

    def _clear(self):
        self.end_all()
        self._bindings.clear()
        self._policies.clear()


class _EphemeralSession:
    ephemeral = True

    def __init__(self):
        self._active, self._resources = True, []

    def require_active(self):
        if not self._active:
            from app.vault.types import VaultLocked
            raise VaultLocked("The connection session is closed.")

    @contextmanager
    def operation(self):
        self.require_active()
        yield None

    def register(self, *, stop=lambda: None, clear=lambda: None):
        self._resources.append((stop, clear))

    def lock(self):
        self._active = False
        for stop, clear in self._resources:
            stop()
            clear()
        self._resources.clear()


class SessionCredentialProvider(CredentialProvider):
    """Explicit unencrypted profiles never read or persist connection secrets."""
    def __init__(self, session=None):
        self.session, self._lock = session or _EphemeralSession(), RLock()
        self._policies, self._active, self._bindings = {}, {}, {}
        self.session.register(stop=self.end_all, clear=self._clear)

    def configure(self, connection, policy=CredentialPolicy.ASK):
        if CredentialPolicy(policy) != CredentialPolicy.ASK:
            raise ValueError("Saved credentials require an encrypted profile.")
        self.end(_connection(connection))

    def begin(self, connection):
        connection = _connection(connection)
        with self.session.operation(), self._lock:
            if connection not in self._active:
                self._active[connection] = None
                self._publish(connection)
            return self._active[connection] is not None

    def save(self, *args, **kwargs):
        raise ValueError("Saved credentials require an encrypted profile.")

    def saved_token(self, *args, **kwargs):
        raise CredentialsRequired()

    def delete_saved(self, connection, **kwargs):
        self.end(_connection(connection))
