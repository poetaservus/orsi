"""Recorded profile locations and recoverable, explicitly confirmed deletion."""
from contextlib import ExitStack
import json
from pathlib import Path
from uuid import UUID, uuid4

from app.state.storage import JsonStore
from app.vault import files
from app.vault.types import VaultError


class ProfileDeletionError(VaultError):
    pass


def identity(root, encrypted):
    name = "header.json" if encrypted else "profile.json"
    value = json.loads(files.read_bytes(Path(root) / name, 16 * 1024))
    return str(UUID(value["profile_id"]))


class ProfileCopies:
    """Public locators only: never keys, passwords or personal record contents."""
    def __init__(self, application_root):
        self.root = Path(application_root).absolute()
        self.store = JsonStore(self.root / "state/profile_registry_v1.json")
        self.pending = JsonStore(self.root / "state/profile_deletion_v1.json")

    def entries(self):
        value = self.store.load({"version": 1, "copies": []})
        if not isinstance(value, dict) or set(value) != {"version", "copies"} or value["version"] != 1:
            raise ProfileDeletionError("Invalid profile copy registry.")
        if not isinstance(value["copies"], list) or len(value["copies"]) > 10_000:
            raise ProfileDeletionError("Invalid profile copy inventory.")
        for item in value["copies"]:
            if (not isinstance(item, dict) or set(item) != {"location", "relative", "profile_id", "encrypted"}
                    or type(item["relative"]) is not bool or type(item["encrypted"]) is not bool):
                raise ProfileDeletionError("Invalid profile copy locator.")
            UUID(item["profile_id"])
            self.path(item)
        return value["copies"]

    def path(self, entry):
        location = entry["location"]
        if not isinstance(location, str) or not location:
            raise ProfileDeletionError("Invalid profile location.")
        path = Path(location)
        if entry["relative"]:
            if path.is_absolute() or ".." in path.parts:
                raise ProfileDeletionError("Invalid relative profile location.")
            path = self.root / path
        elif not path.is_absolute():
            raise ProfileDeletionError("Profile location must be absolute.")
        return path.absolute()

    def remember(self, root, profile_id, encrypted, *, portable=False):
        root = Path(root).absolute()
        relative = portable and root.is_relative_to(self.root)
        entry = {"location": str(root.relative_to(self.root) if relative else root), "relative": relative,
                 "profile_id": str(UUID(profile_id)), "encrypted": encrypted}
        entries = [item for item in self.entries() if self.path(item) != root]
        self.store.save({"version": 1, "copies": [*entries, entry]})

    def forget(self, profile_id):
        entries = [item for item in self.entries() if item["profile_id"] != profile_id]
        if entries:
            self.store.save({"version": 1, "copies": entries})
        else:
            self.store.path.unlink(missing_ok=True)

    def safe_root(self, root):
        root = Path(root).absolute()
        files.ordinary(root)
        if (root.resolve() != root or root == Path(root.anchor)
                or self.root.is_relative_to(root) or Path.home().is_relative_to(root)
                or self.store.path.is_relative_to(root) or self.pending.path.is_relative_to(root)):
            raise ProfileDeletionError("Profile deletion escaped its own location.")
        return root

    def targets(self, locator, known_roots):
        entries = self.entries()
        roots = {locator.root}
        roots.update(self.path(item) for item in entries if item["profile_id"] == locator.profile_id)
        # Include older copies encountered before registry support was installed.
        for root in known_roots:
            try:
                if root.is_dir() and identity(root, locator.encrypted) == locator.profile_id:
                    roots.add(root)
            except (OSError, ValueError, KeyError):
                continue
        other_roots = [self.path(item) for item in entries if item["profile_id"] != locator.profile_id]
        for root in roots:
            self.safe_root(root)
            if any(other.is_relative_to(root) for other in other_roots):
                raise ProfileDeletionError("Another profile is inside a selected location.")
            if not root.exists():
                # A disconnected location cannot be reported as successfully deleted.
                if not root.parent.is_dir():
                    raise ProfileDeletionError("A recorded copy is unavailable.")
                continue
            if identity(root, locator.encrypted) != locator.profile_id:
                raise ProfileDeletionError("A recorded location contains a different profile.")
            list(files.iter_files(root))
        return tuple(sorted((root for root in roots if not any(root != parent and root.is_relative_to(parent)
                            for parent in roots)), key=str))

    def job(self):
        value = self.pending.load()
        if (not isinstance(value, dict) or set(value) != {"version", "operation", "profile_id", "encrypted", "locations"}
                or value["version"] != 1 or type(value["encrypted"]) is not bool):
            raise ProfileDeletionError("Invalid pending profile deletion.")
        UUID(value["operation"])
        UUID(value["profile_id"])
        locations = value["locations"]
        if not isinstance(locations, list) or not locations or len(locations) > 10_000:
            raise ProfileDeletionError("Invalid pending deletion locations.")
        for index, entry in enumerate(locations):
            if (not isinstance(entry, dict) or set(entry) != {"location", "relative"}
                    or type(entry["relative"]) is not bool):
                raise ProfileDeletionError("Invalid pending deletion locator.")
            self.safe_root(self.path(entry))
        return value

    def begin(self, locator, roots):
        locations = []
        for root in roots:
            relative = locator.mode == "portable" and root.is_relative_to(self.root)
            locations.append({"location": str(root.relative_to(self.root) if relative else root), "relative": relative})
        self.pending.save({"version": 1, "operation": str(uuid4()), "profile_id": locator.profile_id,
                           "encrypted": locator.encrypted, "locations": locations})

    def staged(self, job, index, source):
        target = source.with_name(".orsi-delete-" + job["operation"] + "-" + str(index))
        self.safe_root(target)
        if target.parent != source.parent:
            raise ProfileDeletionError("Deletion staging escaped the selected folder.")
        return target

    def _marker(self, target, job):
        marker = target / ".orsi-deletion.json"
        expected = {"profile_id": job["profile_id"], "operation": job["operation"]}
        if marker.exists():
            if json.loads(files.read_bytes(marker, 4096)) != expected:
                raise ProfileDeletionError("Deletion staging identity changed.")
        else:
            # After a crash at the final rmdir, only a newly acquired lease may remain.
            if any(child.name != ".lease" for child in target.iterdir()) and identity(target, job["encrypted"]) != job["profile_id"]:
                raise ProfileDeletionError("Deletion copy identity changed.")
            files.atomic_write(marker, json.dumps(expected).encode())
        return marker

    def remove(self):
        job = self.job()
        sources = [self.path(entry) for entry in job["locations"]]
        targets = [self.staged(job, index, source) for index, source in enumerate(sources)]
        # Acquire every copy before moving or deleting any of them.
        with ExitStack() as stack:
            leases, target_leases = {}, {}
            for source, target in zip(sources, targets):
                if target.exists():
                    list(files.iter_files(target))
                    target_leases[target] = stack.enter_context(_CopyLease(target))
                    self._marker(target, job)
                elif source.exists():
                    if identity(source, job["encrypted"]) != job["profile_id"]:
                        raise ProfileDeletionError("A profile copy was replaced before deletion.")
                    list(files.iter_files(source))
                    leases[source] = stack.enter_context(_CopyLease(source))
                elif not source.parent.is_dir():
                    raise ProfileDeletionError("A recorded copy is unavailable.")
            for source, target in zip(sources, targets):
                if source in leases:
                    leases[source].close()
                    # On Windows an instance holding the source open prevents this move.
                    source.rename(target)
                    target_leases[target] = stack.enter_context(_CopyLease(target))
                    self._marker(target, job)
            for target in targets:
                if not target.exists():
                    continue
                self.safe_root(target)
                marker = self._marker(target, job)
                list(files.iter_files(target))
                lease_file = target / ".lease"
                self._remove_contents(target, marker, lease_file)
                target_leases[target].close()
                lease_file.unlink(missing_ok=True)
                marker.unlink(missing_ok=True)
                target.rmdir()
        self.forget(job["profile_id"])
        return tuple(sources)

    def _remove_contents(self, directory, marker, lease_file):
        # Only resolved, explicitly staged profile directories reach this walker.
        files.ordinary(directory)
        for child in directory.iterdir():
            if child in (marker, lease_file):
                continue
            files.ordinary(child)
            if child.is_dir():
                self._remove_contents(child, marker, lease_file)
                child.rmdir()
            else:
                child.unlink()


class _CopyLease:
    def __init__(self, root):
        self.root = root

    def __enter__(self):
        self.lease = files.Lease(self.root, child_directories=())
        return self.lease

    def __exit__(self, *args):
        self.lease.close()
