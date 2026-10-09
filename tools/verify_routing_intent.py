"""Opt-in cloud routing gate; isolated synthetic files and content-free reports."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent.bootstrap import build_agent_runtime
from app.conversation.orchestrator import ConversationService
from app.conversation.store import ConversationStore
from app.inference.cloud_errors import CloudInferenceError
from app.inference.openai_backend import OpenAIResponsesInferenceEngine
from app.runtime.skills import SkillRegistry
from app.security.host_access import HostAccessPolicy
from app.security.permissions import PermissionDecision, PermissionGate, PermissionRule
from app.capabilities.contracts import PermissionClass
from app.settings.agent import load_agent_feature_config
from app.settings.cloud import load_cloud_config


def screenshot():
    from PySide6.QtCore import QBuffer, QIODevice
    from PySide6.QtGui import QColor, QImage, QPainter
    image = QImage(640, 160, QImage.Format.Format_RGB32)
    image.fill(QColor('#252525'))
    painter = QPainter(image)
    painter.setPen(QColor('white'))
    painter.drawText(20, 50, 'Synthetic Python overlay: values [2, 3]')
    painter.drawText(20, 90, 'Actual total: 4    Expected total: 5')
    painter.end()
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    assert image.save(buffer, 'PNG')
    return bytes(buffer.data())


def verify(output, key_file, skill_source=None):
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    with key_file.open(encoding='utf-8-sig') as stream:
        key = stream.readline().strip()
    if not key:
        return {'passed': False, 'error_category': 'credential_unavailable'}
    output.mkdir(parents=True, exist_ok=False)
    report = {'passed': False, 'cases': [], 'python_execution_by_agent': False, 'gui_execution': False}
    if skill_source is None:
        installed = SkillRegistry()
        installed.discover()
        definition = installed.get('python-coder')
        skill_source = definition.source_path.parent if definition else None
    installed_skill_digest = sha256((skill_source / 'SKILL.md').read_bytes()).hexdigest() if skill_source and skill_source.is_dir() else None
    report['skill_identity'] = installed_skill_digest
    source = b'def draw_overlay(values):\r\n    return sum(values) - 1\r\n'
    fixed = source.replace(b'sum(values) - 1', b'sum(values)')
    save = lambda: (output / 'summary.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    config = load_cloud_config()
    report.update(cloud_model=config.default_model)
    save()
    for skill in (False, True):
        for copy in (False, True):
            cell = {'workflow': 'requested_copy' if copy else 'existing_fix', 'skill': skill, 'status': 'failed'}
            report['cases'].append(cell)
            if skill and installed_skill_digest is None:
                cell.update(status='skipped', error_category='installed_skill_unavailable')
                save()
                continue
            folder = output / ('skill' if skill else 'plain') / cell['workflow']
            folder.mkdir(parents=True)
            portable = folder / 'portable'
            portable.mkdir()
            target = folder / 'main.py'
            destination = folder / 'main_v2.py' if copy else target
            target.write_bytes(source)
            registry = SkillRegistry(global_root=folder / 'skills')
            if skill:
                shutil.copytree(skill_source, registry.global_root / 'python-coder')
                registry.discover()
                assert registry.get('python-coder') is not None
            engine = OpenAIResponsesInferenceEngine(config, api_key=key, selection_path=folder / 'cloud-selection.json')
            policy = HostAccessPolicy.full_local(application_root=portable, user_home=folder, acknowledged=True)
            runtime = build_agent_runtime(engine, config=load_agent_feature_config(), portable_root=portable,
                state_directory=portable / 'state', host_access_policy=policy)
            # Restrict this qualification's authority to synthetic fixtures, while
            # retaining the production catalog, sampling, prompts and turn budgets.
            runtime.permission_gate = PermissionGate((*runtime.permission_gate.rules,
                PermissionRule('fixture-read-deny', PermissionDecision.DENY, permission=PermissionClass.READ),
                PermissionRule('fixture-read-allow', PermissionDecision.ALLOW, permission=PermissionClass.READ, resource_root=folder),
                PermissionRule('fixture-write-deny', PermissionDecision.DENY, permission=PermissionClass.WRITE),
                PermissionRule('fixture-write-ask', PermissionDecision.ASK, permission=PermissionClass.WRITE, resource_root=folder),
                PermissionRule('fixture-execute-deny', PermissionDecision.DENY, permission=PermissionClass.EXECUTE)))
            service = ConversationService(engine, ConversationStore(portable / 'chat.json'), agent_runtime=runtime,
                portable_root=portable, allowed_read_roots=(folder,), host_access_policy=policy, skill_registry=registry)
            approved = []
            def approve(record):
                allowed = record.capability in {'filesystem.edit_text', 'filesystem.write_text', 'filesystem.copy'} and (
                    record.resource is not None and Path(record.resource).resolve() == destination.resolve())
                approved.append(allowed)
                service.resolve_approval(record.approval_id, allowed)
            service.set_approval_requester(approve)
            runner = None
            try:
                if not skill and not copy:
                    # Establish a real historical visual task, then prove the file
                    # request cannot reuse it as an implicit image-edit source.
                    service.select_image_settings(engine.image_settings.current.model_copy(update={'quality': 'low'}))
                    originals = service.run('Generate one simple image of a blue circle on a charcoal background.').generated_images
                    assert originals
                    cell['historical_image_count'] = len(originals)
                reference = service.store.attachment_store.import_bytes(screenshot(), name='bug.png')
                prompt = (f'Create a new copy of "{target}" at "{destination}" and implement the fix there. '
                          'Preserve the original main.py. ' if copy else
                          f'Fix "{target}" in place. Do not create another version of the file. ')
                prompt += ('The attached screenshot shows draw_overlay([2, 3]) returning 4 instead of 5. '
                    'Make draw_overlay return the sum of its values, preserving unrelated source and line endings. '
                    'Read the current file before changing it. '
                    'Report which file you changed and which checks you could actually run.')
                kwargs = {'skill_name': 'python-coder'} if skill else {}
                decision = service.image_route_decision(prompt, attachments=(reference,), **kwargs)
                assert decision.route == 'agent' and decision.references == (reference,)
                assert not service.will_generate_images(prompt, attachments=(reference,), **kwargs)
                answer = service.run(prompt, attachments=(reference,), **kwargs)
                assert not answer.generated_images
                turn = service.store.turns()[-1]
                cell.update(route=decision.route, route_reason=decision.reason,
                    catalog_size=len(runtime.registry.model_definitions()), terminal_status=turn.outcome.status.value,
                    calls=len(turn.settled_calls), model_requests=turn.outcome.model_requests,
                    failed_calls=sum(not call.result.success for call in turn.settled_calls),
                    generated_images=len(answer.generated_images), approved=sum(approved), denied=len(approved) - sum(approved))
                assert turn.outcome.status.value == 'completed'
                assert destination.read_bytes() == fixed
                assert any(call.call.capability in {'filesystem.edit_text', 'filesystem.write_text'} and
                           call.result.success for call in turn.settled_calls)
                assert sorted(path.name for path in folder.glob('*.py')) == (['main.py', 'main_v2.py'] if copy else ['main.py'])
                if copy:
                    assert target.read_bytes() == source
                assert not service.image_route_decision('Make the background darker').references
                assert not service.image_route_decision('Change this file').references
                cell.update(status='passed', bytes_verified=True, source_preserved=not copy or target.read_bytes() == source)
            except CloudInferenceError as exc:
                cell['error_category'] = exc.code.value
            except Exception as exc:
                cell['error_category'] = type(exc).__name__
            finally:
                if service.store.turns():
                    turn = service.store.turns()[-1]
                    if turn.outcome is not None:
                        cell.setdefault('terminal_status', turn.outcome.status.value)
                        cell.setdefault('calls', len(turn.settled_calls))
                        cell['tool_errors'] = [call.result.error.code.value for call in turn.settled_calls if call.result.error]
                runner = engine._runner
                service.shutdown()
                cell['transport_released'] = runner is None or runner._thread is None or not runner._thread.is_alive()
                save()
    del key
    report['skill_source_preserved'] = installed_skill_digest is None or sha256((skill_source / 'SKILL.md').read_bytes()).hexdigest() == installed_skill_digest
    report['passed'] = all(cell['status'] == 'passed' and cell['transport_released'] for cell in report['cases']) and report['skill_source_preserved']
    save()
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--key-file', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--skill-source', type=Path)
    args = parser.parse_args()
    result = verify(args.output.resolve(), args.key_file, args.skill_source)
    print(json.dumps(result))
    raise SystemExit(0 if result['passed'] else 1)
