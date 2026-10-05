"""Native non-following filesystem adapter for the storage-independent reader."""
import os
from hashlib import sha256

from app.runtime.skills.contracts import SkillLoadError, SkillLoadErrorCode
from app.runtime.skills.loader import _validate_path, _inspect_chain
from app.runtime.skills.reference_reader import PackageSnapshot, ReferenceReadError, ReferenceErrorCode


class FilesystemReferenceStorage:
    def snapshot(self, skill, cancellation) -> PackageSnapshot:
        from app.runtime.skills.windows_reference_snapshot import package_snapshot

        cancellation.raise_if_cancelled()
        if os.name != "nt":
            raise ReferenceReadError(ReferenceErrorCode.INACCESSIBLE)
        try:
            root = skill.root_path
            _validate_path(root, None)
            if not root.is_absolute() or skill.source_path != root / "SKILL.md":
                raise ReferenceReadError(ReferenceErrorCode.UNSAFE)
            _inspect_chain(root / "SKILL.md", None)
            identity, main, references = package_snapshot(root, cancellation)
            opaque = sha256((str(root) + "\0" + identity).encode("utf-8")).hexdigest()
            return PackageSnapshot(opaque, main, references)
        except ReferenceReadError:
            raise
        except FileNotFoundError:
            raise ReferenceReadError(ReferenceErrorCode.STALE) from None
        except SkillLoadError as error:
            code = ReferenceErrorCode.UNSAFE if error.code == SkillLoadErrorCode.UNSAFE_PATH else ReferenceErrorCode.INACCESSIBLE
            raise ReferenceReadError(code) from None
        except (ValueError, UnicodeError):
            raise ReferenceReadError(ReferenceErrorCode.INVALID_PACKAGE) from None
        except OSError:
            raise ReferenceReadError(ReferenceErrorCode.INACCESSIBLE) from None
