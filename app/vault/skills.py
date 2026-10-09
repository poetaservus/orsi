"""Personal instruction packages and reference snapshots in the selected vault."""
import base64
from copy import deepcopy
from hashlib import sha256
import json
from threading import RLock

from app.runtime.skills.registry import SkillRegistry
from app.runtime.skills.contracts import SkillDiscoveryReport
from app.runtime.skills.parser import parse_skill
from app.runtime.skills.installer import (_Package, _validate_packages, SkillInstallResult,
                                         SkillInstallError, SkillInstallErrorCode, SkillInstaller)
from app.runtime.skills.package_format import ReferenceFile, validate_references
from app.runtime.skills.reference_reader import PackageSnapshot, ReferenceReadError, ReferenceErrorCode
from app.vault.types import RecordWrite, VaultError


class VaultSkillRegistry(SkillRegistry):
    def __init__(self, session):
        super().__init__(global_root=session.protected_roots[0] / "virtual-skills")
        self.session = session
        self._lock = RLock()
        self.reference_storage = self
        self.session.register(clear=self._forget)

    def _forget(self):
        with self._lock:
            self._report = SkillDiscoveryReport()

    @staticmethod
    def _record(name):
        return "skills/" + sha256(name.encode("utf-8")).hexdigest() + ".json"

    def _decode(self, key, raw):
        if len(raw) > 2 * 1024 * 1024:
            raise ValueError("Personal skill package exceeds the safe size limit.")
        data = json.loads(raw)
        if not isinstance(data, dict) or set(data) != {"main", "references"} or not isinstance(data["references"], dict):
            raise ValueError("Invalid personal skill package.")
        main = base64.b64decode(data["main"], validate=True)
        refs = tuple(ReferenceFile(p, base64.b64decode(v, validate=True)) for p, v in data["references"].items())
        validate_references(refs)
        if len(main) > self.max_bytes:
            raise ValueError("Personal skill exceeds the configured limit.")
        root = self.global_root / key.split("/")[-1].removesuffix(".json")
        skill = parse_skill(main.decode("utf-8"), root_path=root, source_path=root / "SKILL.md")
        if key != self._record(skill.name):
            raise ValueError("Invalid personal skill identity.")
        return skill, main, refs

    def discover(self):
        with self.session.operation() as vault, self._lock:
            self._report = SkillDiscoveryReport()
            paths = [p for p in vault.list_paths() if p.startswith("skills/")]
            if len(paths) > self.max_entries:
                raise ValueError("Personal skill catalog exceeds the configured limit.")
            skills = tuple(self._decode(p, self.session.path(p).read_bytes(limit=2 * 1024 * 1024))[0] for p in paths)
            self._report = SkillDiscoveryReport(skills=tuple(sorted(skills, key=lambda s: s.name)))
            return deepcopy(self._report)

    def get(self, name):
        with self.session.operation():
            return super().get(name)

    def list(self):
        with self.session.operation():
            return super().list()

    @property
    def report(self):
        with self.session.operation():
            return super().report

    def snapshot(self, skill, cancellation):
        cancellation.raise_if_cancelled()
        try:
            with self.session.operation() as vault:
                current, main, refs = self._decode(self._record(skill.name),
                    self.session.path(self._record(skill.name)).read_bytes(limit=2 * 1024 * 1024))
                if current != skill:
                    raise ReferenceReadError(ReferenceErrorCode.STALE)
                cancellation.raise_if_cancelled()
                return PackageSnapshot(self.session.identity + self._record(skill.name), main, refs)
        except (VaultError, KeyError, ValueError, TypeError, OSError):
            raise ReferenceReadError(ReferenceErrorCode.INACCESSIBLE) from None

    def _install_packages(self, packages, *, on_discovered=None):
        _validate_packages(packages, self)
        if on_discovered is not None:
            on_discovered(deepcopy(tuple(p.skill for p in packages)))
        with self.session.operation() as vault, self._lock:
            current = {s.name: s for s in self.discover().skills}
            writes, installed, same = [], [], []
            for package in packages:
                key = self._record(package.skill.name)
                if package.skill.name in current:
                    _, main, refs = self._decode(key, self.session.path(key).read_bytes(limit=2 * 1024 * 1024))
                    if dict(_Package(package.skill, main, refs).files) != dict(package.files):
                        raise SkillInstallError(SkillInstallErrorCode.CONFLICT,
                            "An installed name has different content; remove it before reinstalling.")
                    same.append(package.skill.name)
                    continue
                encoded = json.dumps({"main": base64.b64encode(package.data).decode("ascii"),
                    "references": {r.path: base64.b64encode(r.data).decode("ascii") for r in package.references}}).encode()
                writes.append(RecordWrite(key, encoded))
                installed.append(package.skill.name)
            if len(current) + len(installed) > self.max_entries:
                raise ValueError("Personal skill catalog exceeds the configured limit.")
            if writes:
                vault.write_batch(tuple(writes))
            self.discover()
            return SkillInstallResult(tuple(installed), tuple(same))

    def installer(self):
        return VaultSkillInstaller(self)

    def remove(self, name):
        with self.session.operation() as vault, self._lock:
            if self.get(name) is None:
                raise SkillInstallError(SkillInstallErrorCode.NOT_FOUND, "Skill is not available in the registry.")
            vault.delete((self._record(name),))
            self.discover()


class VaultSkillInstaller(SkillInstaller):
    def _install_packages(self, packages, *, on_discovered=None):
        return self.registry._install_packages(packages, on_discovered=on_discovered)

    def remove(self, name):
        return self.registry.remove(name)
