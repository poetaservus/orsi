"""Public engine types; importing these does not load cryptography or personal data."""
from dataclasses import dataclass, field
from enum import StrEnum
from typing import BinaryIO


class VaultError(Exception):
    """Engine errors use fixed messages without paths, content or secret values."""


class InvalidCredentials(VaultError):
    pass


class RecoveryRequired(VaultError):
    pass


class StorageUnavailable(VaultError):
    pass


class VaultBusy(VaultError):
    pass


class VaultLocked(VaultError):
    pass


class QuotaExceeded(VaultError):
    pass


class State(StrEnum):
    LOCKED = "locked"
    UNLOCKED = "unlocked"
    LOCKING = "locking"
    UNAVAILABLE = "unavailable"
    RECOVERY_REQUIRED = "recovery_required"


class Domain(StrEnum):
    PERSONAL = "personal"
    CREDENTIAL = "credential"


@dataclass(frozen=True)
class KdfCost:
    operations: int = 2
    memory_bytes: int = 64 * 1024 * 1024

    def __post_init__(self):
        if (type(self.operations) is not int or not 2 <= self.operations <= 6
                or type(self.memory_bytes) is not int
                or not 64 * 1024 * 1024 <= self.memory_bytes <= 256 * 1024 * 1024):
            raise VaultError("Unsupported password derivation parameters.")


@dataclass(frozen=True)
class RecordWrite:
    """References point to same-domain records; unretained assets require an owner.

    A batch can commit a record, original, preview, extraction and index together.
    Only retained roots and their reachable dependencies survive deletion/expiry.
    """
    path: str = field(repr=False)
    source: bytes | BinaryIO = field(repr=False)
    references: tuple[str, ...] = field(default=(), repr=False)
    retained: bool = True
    expires_at: int | None = None


@dataclass(frozen=True)
class BackupPolicy:
    max_count: int = 3
    max_age_seconds: int = 30 * 24 * 60 * 60

    def __post_init__(self):
        if (type(self.max_count) is not int or not 0 <= self.max_count <= 100
                or type(self.max_age_seconds) is not int or not 0 <= self.max_age_seconds <= 3650 * 86400):
            raise VaultError("Invalid managed backup retention policy.")
