"""Focused phase 3 synthetic integration; no live providers or host secrets."""
import base64
from dataclasses import replace
from io import BytesIO
import json
import logging
import os
from pathlib import Path
from threading import Event, Thread
from types import SimpleNamespace
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from app.conversation.attachment_processing import AttachmentProcessor
from app.conversation.orchestrator import ConversationService
from app.conversation.store import ConversationStore
from app.execution.audit import CapabilityCrashJournal
from app.inference.engine import InferenceEngine, InferenceUnavailable
from app.inference.hybrid import HybridInferenceEngine
from app.runtime.cancellation import CancellationToken
from app.runtime.skills.import_source import SkillImport, install_import
from app.runtime.skills.package_format import ReferenceFile
from app.runtime.skills.installer import _Package
from app.runtime.skills.parser import parse_skill
from app.runtime.skills.reference_reader import SkillReferenceReader, ReferenceReadError
from app.security.host_access import HostAccessPolicy
from app.state.storage import JsonStore
from app.vault.attachments import VaultAttachmentStore
from app.vault.credentials import CredentialPolicy, CredentialProvider, CredentialsRequired
from app.vault.engine import Vault
from app.vault.session import ProfileSelection, ProfileSession
from app.vault.skills import VaultSkillRegistry
from app.vault.types import Domain, QuotaExceeded, State, VaultLocked


MARKER = "PHASE3-PRIVATE-MARKER-52eab9"
SECRET = "synthetic-only-PHASE3-CREDENTIAL-a1e954"
PASSWORD = b"synthetic phase three password"


@pytest.fixture(params=["local", "portable"])
def profile(tmp_path, request):
    root = tmp_path / request.param / "vault"
    root.parent.mkdir()
    vault = Vault.create(root, PASSWORD)
    session = ProfileSession(vault)
    yield session, vault
    session.lock()


@pytest.fixture
def qt():
    application = QApplication.instance() or QApplication([])
    yield application
    application.processEvents()


def assert_ciphertext(root, *, allowed=()):
    for path in root.rglob("*"):
        if path.is_file() and path not in allowed:
            data = path.read_bytes()
            assert MARKER.encode() not in data, path
            assert SECRET.encode() not in data, path
            assert MARKER not in str(path.relative_to(root))


class Backend(InferenceEngine):
    context_length = 8192
    max_response_tokens = 256
    config = SimpleNamespace(provider_name="Synthetic")

    def __init__(self):
        self._api_key = ""
        self.closed = False
        self.cancelled = False

    @property
    def has_api_key(self):
        return bool(self._api_key)

    def set_api_key(self, value):
        self._api_key = value

    def respond(self, messages):
        return "synthetic reply"

    def cancel_current_request(self):
        self.cancelled = True

    def close(self):
        self.closed = True
        self._api_key = ""


def test_personal_records_history_goals_and_archives_are_profile_owned(profile, tmp_path):
    session, vault = profile
    # These namespaces cover existing preferences and reusable storage for
    # supported notes, templates, personality/configuration and derived caches.
    keys = ("state/ui_preferences_v1.json", "setup/onboarding.json",
            "personality/custom.txt", "templates/instructions.json", "documents/notes.txt",
            "context/summary.json", "drafts/composer.json", "indexes/history.json")
    for key in keys:
        JsonStore(session.path(key)).save({"private": MARKER})
    store = ConversationStore(session.path("state/conversation_v1/conversation.json"))
    turn = store.begin_turn(MARKER)
    store.start_goal(turn)
    store.new_session(preserve_history=True)
    assert store.messages() == []
    archived = [p for p in vault.list_paths() if "/archives/" in p]
    assert len(archived) == 1 and MARKER.encode() in vault.read(archived[0])
    session.lock()
    for key in keys:
        with pytest.raises(VaultLocked):
            JsonStore(session.path(key)).load(default={})
    with pytest.raises(VaultLocked):
        store.messages()
    assert_ciphertext(tmp_path)
    vault.unlock(PASSWORD)
    reopened = ProfileSession(vault)
    try:
        for key in keys:
            assert JsonStore(reopened.path(key)).load() == {"private": MARKER}
    finally:
        reopened.lock()


def test_original_and_prepared_attachment_are_encrypted_and_explicit_export_survives_lock(profile, tmp_path):
    session, vault = profile
    original = tmp_path / "external-original.txt"
    original.write_text(MARKER)
    store = ConversationStore(session.path("state/conversation_v1/conversation.json"))
    ref = store.attachment_store.import_file(original, draft=True)
    processor = AttachmentProcessor(store.attachment_store)
    prepared = processor.prepare(ref)
    assert prepared.processed.text == MARKER
    assert processor.load(ref).text == MARKER
    store.begin_turn(MARKER, attachments=(ref,))
    assert not store.attachment_store.discard_draft(ref)
    export = tmp_path / "explicit-export.txt"
    with store.attachment_store.open(ref) as stream:
        export.write_bytes(stream.read())
    session.lock()
    assert original.read_text() == export.read_text() == MARKER
    with pytest.raises(VaultLocked):
        processor.load(ref)
    assert_ciphertext(tmp_path, allowed=(original, export))
    vault.unlock(PASSWORD)
    reopened = ProfileSession(vault)
    try:
        attachments = VaultAttachmentStore(reopened.path("state/conversation_v1/attachments"))
        assert AttachmentProcessor(attachments).load(ref).text == MARKER
    finally:
        reopened.lock()


@pytest.mark.parametrize("kind", ["docx", "pdf", "png"])
def test_real_memory_parsers_and_image_preview(profile, qt, kind):
    session, vault = profile
    from tests.test_attachment_processing import package, image_data, W
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, NameObject
    if kind == "docx":
        raw = package({"word/document.xml": f'<w:document xmlns:w="{W}"><w:body><w:p><w:r><w:t>{MARKER}</w:t></w:r></w:p></w:body></w:document>'})
    elif kind == "pdf":
        writer = PdfWriter()
        page = writer.add_blank_page(width=100, height=100)
        content = DecodedStreamObject()
        content.set_data(f"BT /F1 12 Tf 10 10 Td ({MARKER}) Tj ET".encode())
        page[NameObject("/Contents")] = writer._add_object(content)
        output = BytesIO(); writer.write(output); raw = output.getvalue()
    else:
        raw = image_data()
    attachments = VaultAttachmentStore(session.path("state/attachments"))
    ref = attachments.import_bytes(raw, name=MARKER + "." + kind)
    prepared = AttachmentProcessor(attachments).prepare(ref)
    assert prepared.processed.attachment_id == ref.id
    if kind == "docx":
        assert prepared.processed.text == MARKER
    if kind == "png":
        from app.ui.message_images import MessageImageLoader
        from tests.test_message_images import wait_for
        loader = MessageImageLoader(attachments)
        loader.image(ref)
        wait_for(lambda: ref.id in loader._images)
        assert not loader.image(ref).isNull()
        session.lock()
        assert not loader._images and not loader._jobs
        with pytest.raises(VaultLocked):
            loader.image(ref)


def test_draft_expiry_and_shared_archive_reachability(profile):
    session, vault = profile
    store = ConversationStore(session.path("state/conversation_v1/conversation.json"))
    attachments = store.attachment_store
    abandoned = attachments.import_bytes(MARKER.encode(), name="abandoned.txt", draft=True)
    AttachmentProcessor(attachments).prepare(abandoned)
    shared = attachments.import_bytes(MARKER.encode(), name="shared.txt", draft=True)
    AttachmentProcessor(attachments).prepare(shared)
    store.begin_turn("keep", attachments=(shared,))
    store.new_session(preserve_history=True)
    store.begin_turn("keep again", attachments=(shared,))
    vault.expire(now=int(time.time()) + 86401)
    assert not any(abandoned.id in p for p in vault.list_paths())
    attachments.verify(shared)
    store.new_session(preserve_history=False)
    attachments.verify(shared)  # Still owned by the archived first conversation.
    archive = next(p for p in vault.list_paths() if "/archives/" in p)
    vault.delete((archive,))
    assert not any(shared.id in p for p in vault.list_paths())


@pytest.mark.parametrize("policy", [CredentialPolicy.ASK, CredentialPolicy.SAVED])
def test_credential_modes_cloud_round_trip_replace_delete_and_no_personal_visibility(profile, policy):
    session, vault = profile
    provider = CredentialProvider(session)
    provider.configure("chat", policy)
    local, cloud = Backend(), Backend()
    inference = HybridInferenceEngine(local=local, cloud=cloud, credential_provider=provider, connection_id="chat")
    with pytest.raises(ValueError, match="consent"):
        provider.save("chat", SECRET)
    if policy == CredentialPolicy.SAVED:
        provider.save("chat", SECRET, consent=True)
        provider.save("other-connection", "unused synthetic credential", consent=True)
    inference.set_mode("cloud")
    if policy == CredentialPolicy.ASK:
        assert not inference.cloud_has_api_key
        inference.set_cloud_api_key(SECRET)
    assert cloud._api_key == SECRET
    assert inference.respond([{"role": "user", "content": "hello"}]) == "synthetic reply"
    inference.set_mode("local")
    assert not cloud.has_api_key and cloud.cancelled
    inference.set_mode("cloud")
    assert inference.cloud_has_api_key is (policy == CredentialPolicy.SAVED)
    assert all(SECRET.encode() not in vault.read(p) for p in vault.list_paths())
    if policy == CredentialPolicy.ASK:
        assert vault.list_paths(domain=Domain.CREDENTIAL) == ()
    else:
        provider.save("chat", "replacement synthetic key", consent=True)
        inference.set_mode("local"); inference.set_mode("cloud")
        assert cloud._api_key == "replacement synthetic key"
        provider.delete_saved("chat")
        assert not cloud.has_api_key and "chat/api_key" not in vault.list_paths(domain=Domain.CREDENTIAL)
    inference.close()
    assert not cloud.has_api_key


def test_failed_cloud_transition_and_unavailable_profile_release_session(profile):
    session, vault = profile
    provider = CredentialProvider(session)
    local, cloud = Backend(), Backend()
    def fail_unload():
        raise InferenceUnavailable("synthetic unload failure")
    local.unload = fail_unload
    inference = HybridInferenceEngine(local=local, cloud=cloud, credential_provider=provider, connection_id="chat")
    inference.set_cloud_api_key(SECRET)
    with pytest.raises(InferenceUnavailable):
        inference.set_mode("cloud")
    assert inference.mode == "local" and not cloud.has_api_key
    del local.unload
    inference.set_cloud_api_key(SECRET); inference.set_mode("cloud")
    vault.lock()  # Simulate the engine revoking access after a storage failure.
    with pytest.raises(VaultLocked):
        inference.respond([{"role": "user", "content": "hello"}])
    session.lock()
    assert not cloud.has_api_key
    inference.close()


def test_independent_service_tokens_consent_and_session_boundaries(profile):
    session, vault = profile
    provider = CredentialProvider(session)
    provider.configure("independent-image", CredentialPolicy.SAVED)
    receiver = Backend(); provider.bind("independent-image", receiver)
    for kind in ("login_token", "access_token", "refresh_token"):
        with pytest.raises(ValueError):
            provider.save("independent-image", SECRET, kind=kind)
        provider.save("independent-image", SECRET, consent=True, kind=kind)
    provider.begin("independent-image")
    assert provider.saved_token("independent-image", kind="refresh_token") == SECRET
    provider.supply("independent-image", SECRET)
    provider.end("independent-image")
    assert not receiver.has_api_key
    with pytest.raises(CredentialsRequired):
        provider.saved_token("independent-image", kind="refresh_token")
    provider.begin("independent-image"); provider.supply("independent-image", SECRET)
    session.lock()
    assert not receiver.has_api_key
    with pytest.raises(VaultLocked):
        provider.begin("independent-image")


def test_encrypted_skill_install_discover_reference_remove_and_no_host_fallback(profile, tmp_path):
    session, vault = profile
    registry = VaultSkillRegistry(session)
    data = (f"---\nname: private-skill\ndescription: {MARKER}\n---\nRead references/guide.md when selected.\n").encode()
    root = tmp_path / "source-only"
    definition = parse_skill(data.decode(), root_path=root, source_path=root / "SKILL.md")
    package = _Package(definition, data, (ReferenceFile("references/guide.md", MARKER.encode()),))
    imported = SkillImport(definition, data, "synthetic immutable reviewed source", (package,))
    assert install_import(registry.installer(), imported).installed == ("private-skill",)
    assert install_import(registry.installer(), imported).already_installed == ("private-skill",)
    selected = registry.get("private-skill")
    assert selected.description == MARKER and not selected.source_path.exists()
    reader = SkillReferenceReader(registry)
    binding = reader.activate(selected, CancellationToken())
    snapshot = registry.snapshot(selected, CancellationToken())
    assert snapshot.references[0].data == MARKER.encode()
    registry.reload()
    reader.validate(binding, CancellationToken())
    session.lock()
    with pytest.raises(VaultLocked):
        registry.list()
    with pytest.raises(ReferenceReadError):
        reader.validate(binding, CancellationToken())
    vault.unlock(PASSWORD)
    reopened = ProfileSession(vault)
    try:
        registry = VaultSkillRegistry(reopened); registry.discover()
        assert registry.get("private-skill").description == MARKER
        reader = SkillReferenceReader(registry)
        binding = reader.activate(registry.get("private-skill"), CancellationToken())
        registry.remove("private-skill")
        assert registry.list() == ()
        with pytest.raises(ReferenceReadError):
            reader.validate(binding, CancellationToken())
    finally:
        reopened.lock()


def test_switch_drains_old_jobs_revokes_old_paths_streams_and_credentials(profile, tmp_path):
    session, vault = profile
    selector = ProfileSelection(); selector.current = session
    path = session.path("state/private.json"); JsonStore(path).save({"marker": MARKER})
    provider = CredentialProvider(session); receiver = Backend(); provider.bind("chat", receiver)
    provider.begin("chat"); provider.supply("chat", SECRET)
    stream = session.open_bytes(MARKER.encode())
    started, cancelled, finished = Event(), Event(), Event()
    errors = []
    def work():
        started.set(); assert cancelled.wait(5)
        try:
            JsonStore(path).save({"late": MARKER})
        except VaultLocked:
            errors.append("revoked")
        finished.set()
    worker = Thread(target=work); worker.start(); assert started.wait(5)
    session.register(stop=cancelled.set, drain=lambda: worker.join(5))
    other_root = tmp_path / "second-profile"; other = Vault.create(other_root, PASSWORD)
    selected = selector.select(other)
    try:
        assert finished.is_set() and errors == ["revoked"] and not receiver.has_api_key
        assert stream.closed and vault.state == State.LOCKED
        assert JsonStore(selected.path("state/private.json")).load() is None
        with pytest.raises(VaultLocked):
            JsonStore(path).load()
        with pytest.raises(VaultLocked):
            stream.read()
        assert other_root in selected.protected_roots
    finally:
        selector.lock()


def test_failed_drain_blocks_switch_and_can_be_retried(profile, tmp_path):
    session, vault = profile
    selector = ProfileSelection(); selector.current = session
    released = [False]
    cleared = []
    def drain():
        if not released[0]:
            raise RuntimeError(MARKER)
    session.register(drain=drain, clear=lambda: cleared.append(True))
    other = Vault.create(tmp_path / "other", PASSWORD)
    try:
        with pytest.raises(RuntimeError, match="retry closing") as exc:
            selector.select(other)
        assert MARKER not in str(exc.value)
        assert selector.current is session and vault.state == State.LOCKED
        assert cleared == []
        released[0] = True
        selector.select(other)
        assert cleared == [True]
        selector.lock()
    finally:
        other.lock()


def test_active_conversation_is_cancelled_and_drained_before_switch(profile, tmp_path):
    session, vault = profile
    started, release = Event(), Event()
    class BlockingBackend(Backend):
        def respond(self, messages):
            started.set()
            assert release.wait(5)
            return MARKER
        def cancel_current_request(self):
            release.set()
    backend = BlockingBackend()
    inference = HybridInferenceEngine(local=backend, cloud=None)
    service = ConversationService(inference, ConversationStore(session.path("state/conversation_v1/conversation.json")),
                                  skill_registry=VaultSkillRegistry(session))
    session.register(stop=service.stop_for_profile, drain=service.drain_for_profile, clear=service.clear_for_profile)
    settled = []
    def run():
        try:
            settled.append(service.run(MARKER))
        except (VaultLocked, RuntimeError):
            settled.append("stopped")
    worker = Thread(target=run); worker.start(); assert started.wait(5)
    other = Vault.create(tmp_path / "next-profile", PASSWORD)
    selector = ProfileSelection(); selector.current = session
    try:
        selected = selector.select(other)
        worker.join(5)
        assert not worker.is_alive() and settled in (["stopped"], ["The response was stopped."]) and backend.closed
        assert service._agent_history == []
        assert selected.path("state/conversation_v1/conversation.json").exists() is False
    finally:
        release.set(); worker.join(5); selector.lock(); other.lock()


def test_quota_failure_does_not_publish_history_or_create_plaintext(profile, tmp_path):
    session, vault = profile
    store = ConversationStore(session.path("state/conversation_v1/conversation.json"))
    bounded = session.path("state/bounded.txt"); bounded.write_bytes(MARKER.encode())
    assert bounded.stat().st_size == len(MARKER.encode())
    with pytest.raises(ValueError, match="consumer size limit"):
        bounded.read_bytes(limit=1)
    vault.set_quota(vault.usage_bytes() + 65536)
    with pytest.raises(QuotaExceeded):
        store.append("user", MARKER * 10000)
    assert store.messages() == []
    session.lock()
    assert_ciphertext(tmp_path)


@pytest.mark.parametrize("scope", ["portable", "full_local"])
def test_file_tools_exclude_vault_direct_parent_walk_traversal_and_hardlinks(profile, tmp_path, scope):
    from app.capabilities.filesystem_list import FilesystemListCapability
    from app.capabilities.filesystem_find import FilesystemFindCapability
    from app.capabilities.filesystem_search import FilesystemSearchCapability
    from app.capabilities.filesystem_read_text import FilesystemReadTextCapability
    from app.capabilities.contracts import CapabilityExecutionError
    from tests.test_filesystem_list import context
    session, vault = profile
    public = tmp_path / "ordinary.txt"; public.write_text("findme")
    policy = (HostAccessPolicy.portable_root(tmp_path) if scope == "portable" else
        HostAccessPolicy.full_local(application_root=tmp_path, user_home=tmp_path, acknowledged=True))
    policy = replace(policy, protected_roots=session.protected_roots)
    ctx = context(tmp_path, host_access_policy=policy)
    for target in (vault.root / "header.json", vault.root / "objects" / ".." / "header.json"):
        with pytest.raises(CapabilityExecutionError):
            policy.resolve_read(str(target))
        assert not FilesystemReadTextCapability().invoke({"path": str(target)}, ctx).success
    parent = vault.root.parent
    listed = FilesystemListCapability().invoke({"path": str(parent)}, ctx)
    assert listed.success and not listed.output["entries"]
    found = FilesystemFindCapability().invoke({"path": str(parent), "name": "vault"}, ctx)
    assert found.success and not found.output["matches"]
    result = FilesystemSearchCapability().invoke({"path": str(tmp_path), "query": "findme"}, ctx)
    assert result.success and [m["path"] for m in result.output["matches"]] == [str(public)]
    alias = tmp_path / "cipher-alias.txt"; os.link(vault.root / "header.json", alias)
    try:
        with pytest.raises(CapabilityExecutionError):
            policy.resolve_read(str(alias))
    finally:
        alias.unlink()


def test_actual_startup_uses_profile_state_and_never_environment_or_legacy_preferences(profile, monkeypatch, tmp_path):
    import app.startup as startup
    from tests.test_openai_phase1 import config
    session, vault = profile
    host_state = tmp_path / "legacy-state"; host_state.mkdir()
    (host_state / "ui_preferences_v1.json").write_text(json.dumps({"legacy": MARKER}))
    app_root = tmp_path / "application"; app_root.mkdir()
    monkeypatch.setattr(startup, "PATHS", SimpleNamespace(root=app_root, state=host_state,
        models=app_root / "models", config=app_root / "config"))
    monkeypatch.setattr(startup, "load_model_config", lambda: (_ for _ in ()).throw(InferenceUnavailable("synthetic no local model")))
    monkeypatch.setattr(startup, "load_cloud_config", lambda: config(default_mode="cloud"))
    seen = []
    def backend(configuration, **kwargs):
        seen.append(kwargs)
        assert kwargs["api_key"] == ""
        JsonStore(kwargs["selection_path"]).save({"synthetic": MARKER})
        return Backend()
    monkeypatch.setattr(startup, "OpenAIResponsesInferenceEngine", backend)
    from app.vault.logging import configure_profile_logging
    previous_handlers = logging.getLogger().handlers[:]
    previous_level = logging.getLogger().level
    # Isolate the process-wide logging owner for this startup test.
    logging.getLogger().handlers = []
    try:
        service, _, error, inference = startup.build_application(
            profile_session=session, agent_config_override=startup.AgentFeatureConfig())
        assert error is None and service is not None and not inference.cloud_has_api_key
        assert isinstance(service.skill_registry, VaultSkillRegistry)
        assert isinstance(service.store.attachment_store, VaultAttachmentStore)
        assert JsonStore(session.path("state/ui_preferences_v1.json")).load() is None
        assert not (host_state / "conversation_v1").exists()
        assert not (host_state / "cloud_model_selection_v1.json").exists()
        service.run(MARKER)
        assert MARKER.encode() in vault.read("state/conversation_v1/conversation.json")
        logging.getLogger("app.synthetic").error("%s %s", MARKER, SECRET, exc_info=True)
        assert MARKER.encode() not in vault.read("diagnostics/events_v1.json")
        session.lock()
        assert inference.cloud.closed and service._agent_history == []
        with pytest.raises(VaultLocked):
            service.store.visible_messages()
        with pytest.raises(RuntimeError):
            service.run("late")
    finally:
        for handler in tuple(logging.getLogger().handlers):
            handler.close()
        logging.getLogger().handlers = previous_handlers
        logging.getLogger().setLevel(previous_level)


@pytest.mark.parametrize("policy", [CredentialPolicy.ASK, CredentialPolicy.SAVED])
def test_native_mock_image_generation_pipeline_uses_shared_credentials_and_encrypted_images(profile, monkeypatch, policy):
    from tests.test_image_generation import image_payload
    from tests.test_openai_phase1 import engine_with_transport, response
    session, vault = profile
    payload = image_payload()
    cloud, client, requests, factory = engine_with_transport(monkeypatch, payload)
    credentials = CredentialProvider(session); credentials.configure("chat-images", policy)
    inference = HybridInferenceEngine(local=Backend(), cloud=cloud, credential_provider=credentials, connection_id="chat-images")
    if policy == CredentialPolicy.SAVED:
        credentials.save("chat-images", SECRET, consent=True)
    inference.set_mode("cloud")
    if policy == CredentialPolicy.ASK:
        inference.set_cloud_api_key(SECRET)
    service = ConversationService(inference, ConversationStore(session.path("state/conversation_v1/conversation.json")),
                                  skill_registry=VaultSkillRegistry(session))
    session.register(stop=service.stop_for_profile, drain=service.drain_for_profile, clear=service.clear_for_profile)
    result = service.run("Generate an image of a blue circle")
    assert len(result.generated_images) == 1 and len(requests) == 1
    assert factory.call_args.kwargs["api_key"] == SECRET
    reference = result.generated_images[0]
    service.store.attachment_store.verify(reference)
    assert SECRET.encode() not in vault.read("state/conversation_v1/conversation.json")
    assert not service.store.attachment_store.discard_draft(reference)
    payload.clear(); payload.update(response(MARKER))
    assert service.run("Hello") == MARKER
    assert len(requests) == 2 and SECRET.encode() not in vault.read("state/conversation_v1/conversation.json")
    session.lock()
    assert client.is_closed() and not cloud.has_api_key
    vault.unlock(PASSWORD)
    reopened = ProfileSession(vault)
    try:
        store = ConversationStore(reopened.path("state/conversation_v1/conversation.json"))
        assert any(m.generated_images == (reference,) for m in store.visible_messages())
        store.attachment_store.verify(reference)
    finally:
        reopened.lock()


def test_cached_preferences_documents_and_crash_recovery_are_revoked(profile):
    from app.settings.images import ImageSettingsStore, ImageGenerationSettings
    from app.settings.openai_cloud import OpenAIModelCatalog
    from app.conversation.local_documents import LocalDocuments
    from tests.test_openai_phase1 import config
    session, vault = profile
    images = ImageSettingsStore(ImageGenerationSettings(), session.path("state/image_generation_v1.json"))
    images.select(ImageGenerationSettings(quality="low"))
    catalog = OpenAIModelCatalog(config(), session.path("state/cloud_model_selection_v1.json"))
    catalog.select("gpt-6.1-sol")
    journal = CapabilityCrashJournal(session.path("state/capability_journal_v1.json"))
    assert journal.records == ()
    attachments = VaultAttachmentStore(session.path("state/attachments"))
    ref = attachments.import_bytes(MARKER.encode(), name="private.txt")
    docs = LocalDocuments(attachments)
    assert docs.load(ref).text == MARKER
    assert images.current.quality == "low" and catalog.current_id == "gpt-6.1-sol"
    session.lock()
    for read in (lambda: images.current, lambda: catalog.current_id,
                 lambda: journal.records, lambda: docs.load(ref)):
        with pytest.raises(VaultLocked):
            read()
    assert docs._cache == {}


def test_window_and_viewer_drop_private_content_and_late_callbacks(profile, qt):
    from app.ui.main_window import MainWindow
    from app.ui.image_viewer import ImageViewer
    from tests.test_attachment_processing import image_data
    from tests.test_message_images import wait_for
    session, vault = profile
    local = Backend()
    inference = HybridInferenceEngine(local=local, cloud=Backend())
    service = ConversationService(inference, ConversationStore(session.path("state/conversation_v1/conversation.json")),
                                  skill_registry=VaultSkillRegistry(session))
    session.register(stop=service.stop_for_profile, drain=service.drain_for_profile, clear=service.clear_for_profile)
    prefs = JsonStore(session.path("state/ui_preferences_v1.json")); prefs.save({"greeting_message": MARKER})
    window = MainWindow(service, "synthetic host", None, inference, prefs)
    window.bind_profile(session); window.show()
    window.input.setPlainText(MARKER)
    window.chat.add_message("User", MARKER)
    ref = service.store.attachment_store.import_bytes(image_data(), name=MARKER + ".png")
    viewer = ImageViewer(service.store.attachment_store, (ref,), parent=window)
    # Keep the instance for assertions after it is hidden/revoked.
    from PySide6.QtCore import Qt
    viewer.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
    viewer.show(); wait_for(lambda: ref.id in viewer.loader._images)
    try:
        session.lock()
        assert not window.isVisible() and not viewer.isVisible()
        assert window.input.toPlainText() == window.greeting_input.text() == ""
        assert not window.chat._messages and window._preferences_store is None
        assert viewer._backdrop.isNull() and not viewer.loader._images
        window._done(MARKER, False)
        assert not window.chat._messages
        window.skill_settings_page._succeeded(SimpleNamespace(definition=MARKER))
        assert window.skill_settings_page.prepared is None
    finally:
        viewer.close(); window.close()
