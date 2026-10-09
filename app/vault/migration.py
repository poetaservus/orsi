"""Opt-in snapshots, atomic import, verification and separately authorized cleanup."""
import base64
from dataclasses import dataclass, field
from hashlib import sha256
import json
from pathlib import Path
import time
from uuid import uuid4

from app.vault import files
from app.vault.types import Domain, RecordWrite, VaultError, MigrationConflict, OriginalChanged, UnverifiedMigration


CATEGORIES = {
    "preferences": "Setup, personality greeting and model/image preferences",
    "history": "Conversations, generated images, attachments and extracted text",
    "recovery": "Task recovery journal",
    "skills": "Personal skills and their documentation",
    "personality": "Personal personality files",
    "templates": "Templates and personal instructions",
    "documents": "Personal documents",
    "memory": "Retained memory, summaries and indexes",
    "drafts": "Retained drafts and recovery material",
}
_PREFERENCES = ("ui_preferences_v1.json", "local_model_selection_v1.json", "cloud_model_selection_v1.json",
                "image_generation_v1.json", "cloud_rate_limits_v1.json")
_TREES = {"personality": ("personality",), "templates": ("templates", "instructions"),
          "documents": ("documents",), "memory": ("memory", "context", "indexes"), "drafts": ("drafts", "recovery")}
_LIMIT = 512 * 1024 * 1024


@dataclass(frozen=True)
class Original:
    path: Path = field(repr=False)
    digest: str
    target: str = field(repr=False)
    domain: Domain = Domain.PERSONAL
    # Credential cleanup removes only the chosen JSON field, preserving config.
    credential_field: str | None = None


@dataclass
class MigrationPlan:
    categories: tuple[str, ...]
    writes: list[RecordWrite] = field(default_factory=list, repr=False)
    originals: list[Original] = field(default_factory=list, repr=False)
    identity: str = field(default_factory=lambda: uuid4().hex)
    credential_writes: list[RecordWrite] = field(default_factory=list, repr=False)

    @property
    def size_bytes(self):
        return sum(len(w.source) for w in (*self.writes, *self.credential_writes))


def _bytes(path):
    path = Path(path).absolute()
    data = files.read_bytes(path, _LIMIT)
    if path.stat().st_nlink != 1:
        raise VaultError("Import sources cannot use hardlink aliases.")
    return data


def _add(plan, source, target, *, references=(), retained=True, expires_at=None, raw=None):
    source = Path(source).absolute()
    raw = _bytes(source) if raw is None else raw
    if sum(len(w.source) for w in plan.writes) + len(raw) > 1024**3:
        raise VaultError("Import exceeds the safe batch size. Select fewer categories.")
    plan.writes.append(RecordWrite(target, raw, references=references, retained=retained, expires_at=expires_at))
    plan.originals.append(Original(source, sha256(raw).hexdigest(), target))
    return raw


def prepare_migration(application_root, categories, *, skills_root=None):
    root = Path(application_root).absolute()
    categories = tuple(categories)
    if not categories or len(set(categories)) != len(categories) or set(categories) - CATEGORIES.keys():
        raise VaultError("Select the personal-data categories to import.")
    plan = MigrationPlan(categories)
    state = root / "state"
    if "preferences" in categories:
        for name in _PREFERENCES:
            if (state / name).exists():
                raw = _add(plan, state / name, "state/" + name)
                if not isinstance(json.loads(raw), dict):
                    raise VaultError("A selected preference file is invalid; originals were preserved.")
    if "recovery" in categories and (state / "capability_journal_v1.json").exists():
        raw = _add(plan, state / "capability_journal_v1.json", "state/capability_journal_v1.json")
        if not isinstance(json.loads(raw), dict):
            raise VaultError("The recovery journal is invalid; originals were preserved.")
    if "history" in categories:
        _history(plan, state / "conversation_v1")
    for category, trees in _TREES.items():
        if category not in categories:
            continue
        for tree in trees:
            folder = root / tree
            if folder.is_dir():
                for path, _ in files.iter_files(folder):
                    _add(plan, path, tree + "/" + path.relative_to(folder).as_posix(),
                         expires_at=int(time.time()) + 86400 if category == "drafts" else None)
    if "skills" in categories:
        folder = Path(skills_root) if skills_root is not None else Path.home() / ".orsi/skills"
        if folder.is_dir():
            from app.runtime.skills.registry import SkillRegistry
            from app.runtime.skills.installer import _inspect_package
            from app.vault.skills import VaultSkillRegistry
            packages = _inspect_package(folder, SkillRegistry(global_root=folder))
            for package in packages:
                target = VaultSkillRegistry._record(package.skill.name)
                encoded = json.dumps({"main": base64.b64encode(package.data).decode("ascii"),
                    "references": {r.path: base64.b64encode(r.data).decode("ascii") for r in package.references}}).encode()
                plan.writes.append(RecordWrite(target, encoded))
                # Package metadata is not deleted: only verified source bodies.
                for relative, raw in package.files:
                    source = package.skill.root_path / relative
                    actual = _bytes(source)
                    if actual != raw:
                        raise VaultError("A skill changed while preparing the import.")
                    plan.originals.append(Original(source, sha256(actual).hexdigest(), target))
    if len({w.path for w in plan.writes}) != len(plan.writes):
        raise VaultError("Selected categories contain conflicting destinations.")
    return plan


def _history(plan, root):
    from app.conversation.store import Conversation
    from app.inference.attachments import AttachmentReference
    if not root.is_dir():
        return
    entries = dict(files.iter_files(root))
    histories, owned = [], set()
    for source in entries:
        rel = source.relative_to(root)
        if rel.as_posix() == "conversation.json" or (len(rel.parts) == 2 and rel.parts[0] == "archives" and rel.suffix == ".json"):
            raw = _bytes(source)
            conversation = Conversation.model_validate_json(raw)
            refs = {r.id: r for m in conversation.messages for r in (*m.attachments, *m.generated_images)}
            # A source active conversation becomes a saved archive, never replaces live history.
            name = sha256((plan.identity + str(rel)).encode()).hexdigest()[:32] + ".json"
            target = "state/conversation_v1/archives/" + name
            _add(plan, source, target, references=tuple("state/conversation_v1/attachments/" + r + "/metadata.json" for r in refs), raw=raw)
            histories.append(refs)
            owned.update(refs)
    prefixes = {p.parent for p in entries if p.name == "metadata.json" and p.parent.parent == root / "attachments"}
    for folder in prefixes:
        raw = _bytes(folder / "metadata.json")
        reference = AttachmentReference.model_validate_json(raw)
        if reference.id != folder.name:
            raise VaultError("Attachment identity does not match its retained copy.")
        content = _bytes(folder / "content")
        if len(content) != reference.size_bytes or sha256(content).hexdigest() != reference.sha256:
            raise VaultError("Attachment verification failed; originals were preserved.")
        if any(reference.id in refs and refs[reference.id] != reference for refs in histories):
            raise VaultError("Conversation attachment metadata does not match its original.")
        prefix = "state/conversation_v1/attachments/" + folder.name
        _add(plan, folder / "content", prefix + "/content", retained=False, raw=content)
        links = [prefix + "/content"]
        if (folder / "prepared_v1.json") in entries:
            prepared = _add(plan, folder / "prepared_v1.json", prefix + "/prepared_v1.json", retained=False)
            json.loads(prepared)
            links.append(prefix + "/prepared_v1.json")
        _add(plan, folder / "metadata.json", prefix + "/metadata.json", references=tuple(links),
             retained=reference.id not in owned,
             expires_at=int(time.time()) + 86400 if reference.id not in owned else None, raw=raw)
    if owned - {p.name for p in prefixes}:
        raise VaultError("A retained conversation has a missing attachment; originals were preserved.")
    recognized = {o.path for o in plan.originals}
    # Preserve interrupted copies/cache files encrypted, with a disposable lifetime.
    for source in entries:
        if source not in recognized:
            _add(plan, source, "drafts/migrated/" + plan.identity + "/" + source.relative_to(root).as_posix(),
                 expires_at=int(time.time()) + 86400)


def prepare_credential_import(source, connection, kind, *, field_name=None, consent=False):
    from app.vault.credentials import CredentialProvider, _connection
    if consent is not True or kind not in {"api_key", "access_token", "refresh_token", "login_token"}:
        raise VaultError("Importing a credential requires explicit save consent.")
    source = Path(source).absolute()
    raw = _bytes(source)
    field_name = field_name or kind
    value = json.loads(raw)
    if not isinstance(value, dict) or field_name not in value:
        raise VaultError("Choose a JSON credential file containing the selected field.")
    secret = CredentialProvider._secret(value[field_name])
    key = _connection(connection) + "/" + kind
    plan = MigrationPlan(("credentials",))
    plan.credential_writes.append(RecordWrite(key, secret))
    plan.originals.append(Original(source, sha256(raw).hexdigest(), key, Domain.CREDENTIAL, field_name))
    return plan


def apply_migration(session, plan, *, replace=False):
    if not session.encrypted:
        raise VaultError("Protected migration requires an encrypted profile.")
    receipt_key = "migration/" + plan.identity + ".json"
    with session.operation() as vault:
        for domain, writes in ((Domain.PERSONAL, plan.writes), (Domain.CREDENTIAL, plan.credential_writes)):
            existing = set(vault.list_paths(domain=domain))
            if not replace and any(w.path in existing and vault.read(w.path, domain=domain) != w.source for w in writes):
                raise MigrationConflict("A destination already contains different data. Explicit replacement is required.")
        # Refuse a changed source before publication. No originals are removed here.
        for item in plan.originals:
            if sha256(_bytes(item.path)).hexdigest() != item.digest:
                raise OriginalChanged("An original changed before import. Prepare it again.")
        pending = {"version": 1, "verified": False, "categories": list(plan.categories), "originals": [], "records": []}
        vault.put(receipt_key, json.dumps(pending).encode(), expires_at=int(time.time()) + 86400)
        # Credentials are a separate domain and intentionally a separate explicit import.
        if plan.credential_writes and plan.writes:
            raise VaultError("Import personal data and credentials as separate choices.")
        domain = Domain.CREDENTIAL if plan.credential_writes else Domain.PERSONAL
        writes = plan.credential_writes or plan.writes
        if writes:
            vault.write_batch(tuple(writes), domain=domain)
        records = [{"target": w.path, "digest": sha256(w.source).hexdigest(), "domain": domain.value} for w in writes]
        for item in records:
            if sha256(vault.read(item["target"], domain=domain)).hexdigest() != item["digest"]:
                raise UnverifiedMigration("Import verification did not finish. Originals were preserved.")
        receipt = {**pending, "verified": True, "records": records, "originals": [
            {"path": str(o.path), "digest": o.digest, "target": o.target, "domain": o.domain.value,
             "field": o.credential_field} for o in plan.originals]}
        vault.put(receipt_key, json.dumps(receipt).encode())
    return receipt_key


def retained_originals(session, receipt_key):
    with session.operation() as vault:
        receipt = json.loads(vault.read(receipt_key))
        if not receipt.get("verified"):
            raise UnverifiedMigration("Import is not verified. Original cleanup is unavailable.")
        remaining = []
        for item in receipt["originals"]:
            source = Path(item["path"])
            if not source.is_file():
                continue
            if item["field"] is not None:
                try:
                    if item["field"] not in json.loads(_bytes(source)):
                        continue
                except (OSError, ValueError):
                    pass
            remaining.append(item["path"])
        return tuple(remaining)


def cleanup_originals(session, receipt_key, selected, *, consent=False):
    if consent is not True:
        raise VaultError("Original cleanup requires a separate explicit choice.")
    selected = set(selected)
    with session.operation() as vault:
        receipt = json.loads(vault.read(receipt_key))
        if not receipt.get("verified") or not selected or selected - {o["path"] for o in receipt["originals"]}:
            raise UnverifiedMigration("Choose originals from a verified migration.")
        # Verify all imported destinations and selected originals before any deletion.
        for record in receipt["records"]:
            if sha256(vault.read(record["target"], domain=Domain(record["domain"]))).hexdigest() != record["digest"]:
                raise OriginalChanged("An imported copy changed. Originals were preserved.")
        chosen = [o for o in receipt["originals"] if o["path"] in selected]
        for item in chosen:
            path = Path(item["path"])
            if path.is_relative_to(vault.root) or sha256(_bytes(path)).hexdigest() != item["digest"]:
                raise OriginalChanged("An original changed or is unsafe. It was preserved.")
        for item in chosen:
            path = Path(item["path"])
            files.ordinary(path)
            if item["field"] is not None:
                current = _bytes(path)
                if sha256(current).hexdigest() != item["digest"]:
                    raise OriginalChanged("Original credential configuration changed before cleanup.")
                value = json.loads(current)
                del value[item["field"]]
                files.atomic_write(path, (json.dumps(value, indent=2) + "\n").encode())
            else:
                files.remove_verified_original(path, item["digest"], _LIMIT)
        receipt["originals"] = [o for o in receipt["originals"] if o["path"] not in selected]
        vault.put(receipt_key, json.dumps(receipt).encode())
    return len(chosen)
