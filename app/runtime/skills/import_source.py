"""Review immutable single-file or complete Markdown packages before publication."""
from dataclasses import dataclass
from pathlib import Path
from time import monotonic
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from app.runtime.skills.contracts import SkillDefinition
from app.runtime.skills.installer import SkillInstaller, _Package, _snapshot, _inspect_package, _validate_packages
from app.runtime.skills.registry import SkillRegistry
from app.runtime.skills.loader import MAX_SKILL_SIZE, _validate_path
from app.runtime.skills.parser import parse_skill


class SkillImportError(ValueError):
    """A safe, user-facing import failure without downloaded content."""


@dataclass(frozen=True, slots=True)
class SkillImport:
    definition: SkillDefinition
    data: bytes
    source: str
    packages: tuple[_Package, ...] = ()
    revision: str = ""
    kind: str = "single-file"

    @property
    def reference_count(self):
        return sum(len(package.references) for package in self.packages)

    @property
    def total_bytes(self):
        return sum(package.total_bytes for package in self.packages) if self.packages else len(self.data)

    @property
    def skill_count(self):
        return len(self.packages) if self.packages else 1


def _github_repository_url(source):
    """Only a public GitHub repository root selects package mode in Settings."""
    parts = urlsplit(source)
    segments = parts.path.strip("/").split("/")
    if parts.netloc != "github.com" or len(segments) != 2:
        return None
    from app.runtime.skills.git_installer import _validate_url
    _validate_url(source)
    if any(not segment or segment in (".", "..") or "%" in segment for segment in segments):
        raise SkillImportError("Use a public GitHub repository link.")
    return source


def github_skill_url(source: str) -> str:
    """Accept GitHub file/raw links only; never treat a repository as one skill."""
    try:
        if (not isinstance(source, str) or not 1 <= len(source) <= 2048
                or any(ord(char) < 33 or ord(char) > 126 for char in source)):
            raise ValueError
        parts = urlsplit(source)
        if (parts.scheme != "https" or parts.username is not None or parts.password is not None
                or parts.port is not None or parts.query not in ("", "plain=1", "raw=1")):
            raise ValueError
        segments = parts.path.split("/")[1:]
        if (any(not part or part in (".", "..") for part in segments)
                or any(char in parts.path for char in "%\\") or segments[-1] != "SKILL.md"):
            raise ValueError
        if parts.netloc == "github.com" and len(segments) >= 5 and segments[2] == "blob":
            segments.pop(2)
        elif parts.netloc != "raw.githubusercontent.com" or len(segments) < 4:
            raise ValueError
        return "https://raw.githubusercontent.com/" + "/".join(segments)
    except (ValueError, IndexError):
        raise SkillImportError("Paste a GitHub link to SKILL.md or its Raw link. Repository and marketplace links are not supported here.") from None


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def _download(url: str, max_bytes: int) -> bytes:
    deadline = monotonic() + 30
    opener = build_opener(ProxyHandler({}), _NoRedirect())
    request = Request(url, headers={"User-Agent": "ORSI-Skill-Import/1", "Accept": "text/plain"})
    try:
        with opener.open(request, timeout=10) as response:
            if response.headers.get_content_type() == "text/html":
                raise SkillImportError("The link returned a webpage. Choose the skill's SKILL.md file.")
            length = response.headers.get("Content-Length")
            if length is not None and (len(length) > 20 or not length.isdecimal() or int(length) > max_bytes):
                raise SkillImportError("The skill exceeds the download size limit.")
            chunks, total = [], 0
            while True:
                if monotonic() >= deadline:
                    raise SkillImportError("The download took too long. Try again.")
                chunk = response.read1(min(65536, max_bytes - total + 1))
                if not chunk:
                    return b"".join(chunks)
                total += len(chunk)
                if total > max_bytes:
                    raise SkillImportError("The skill exceeds the download size limit.")
                chunks.append(chunk)
    except HTTPError as error:
        error.close()
        if error.code == 404:
            message = "The skill file was not found. Check the link and branch name."
        elif 300 <= error.code < 400:
            message = "The link redirects elsewhere. Use the skill's direct Raw link."
        else:
            message = "GitHub could not provide the file. Try again later."
        raise SkillImportError(message) from None
    except (URLError, OSError, TimeoutError):
        raise SkillImportError("Could not download the skill. Check your connection and try again.") from None


def prepare_import(source: str, *, max_bytes: int = MAX_SKILL_SIZE) -> SkillImport:
    if type(max_bytes) is not int or not 0 < max_bytes <= MAX_SKILL_SIZE:
        raise SkillImportError("The skill size limit is invalid.")
    if not isinstance(source, str) or not source.strip():
        raise SkillImportError("Paste a GitHub repository/file link or choose a skill folder or Markdown file.")
    source = source.strip()
    if "://" in source:
        repository = _github_repository_url(source)
        if repository is not None:
            from app.runtime.skills.git_installer import GitSkillInstaller
            snapshot = GitSkillInstaller(SkillInstaller(SkillRegistry(max_bytes=max_bytes))).prepare(repository)
            first = snapshot.packages[0]
            return SkillImport(first.skill, first.data, source, snapshot.packages, snapshot.revision, "repository")
        url = github_skill_url(source)
        data = _download(url, max_bytes)
        root, path = Path("."), Path("SKILL.md")
    else:
        path = Path(source)
        _validate_path(path, path)
        path = path.absolute()
        if path.is_dir():
            packages = _inspect_package(path, SkillRegistry(max_bytes=max_bytes))
            first = packages[0]
            return SkillImport(first.skill, first.data, source, packages, kind="folder")
        if path.suffix.casefold() != ".md":
            raise SkillImportError("Choose a Markdown (.md) skill file.")
        data = _snapshot(path, max_bytes)
        root = path.parent
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        raise SkillImportError("The skill file must use UTF-8 text.") from None
    definition = parse_skill(text, root_path=root, source_path=path)
    return SkillImport(definition, data, source)


def install_import(installer: SkillInstaller, imported: SkillImport):
    """Install the reviewed bytes, even if the original file/link later changes."""
    if not isinstance(installer, SkillInstaller) or not isinstance(imported, SkillImport):
        raise SkillImportError("Preview the skill before installing it.")
    if not isinstance(imported.data, bytes) or len(imported.data) > installer.registry.max_bytes:
        raise SkillImportError("The skill exceeds the installation size limit.")
    definition = parse_skill(imported.data.decode("utf-8", errors="strict"),
                             root_path=imported.definition.root_path,
                             source_path=imported.definition.source_path)
    if definition != imported.definition:
        raise SkillImportError("The preview changed. Preview the skill again.")
    if imported.packages:
        _validate_packages(imported.packages, installer.registry)
        if imported.packages[0].skill != definition or imported.packages[0].data != imported.data:
            raise SkillImportError("The preview changed. Preview the skill again.")
        return installer._install_packages(imported.packages)
    # The same immutable package transaction is used by HTTPS Git installation.
    return installer._install_packages((_Package(definition, imported.data),))
