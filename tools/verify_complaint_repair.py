"""Opt-in unchanged three-prompt cloud replays with independent scroll acceptance.

The user must authorize the key file. All edits are confined to disposable
copies. Summaries contain no keys, source, prompts or response bodies.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import logging
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
from threading import Timer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def source_hashes(project):
    return {str(path.relative_to(project)):sha256(path.read_bytes()).hexdigest()
        for path in (project/'src').rglob('*') if path.is_file()}


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0))
        return sock.getsockname()[1]


def junction(path, target):
    quoted_path = str(path).replace("'", "''")
    quoted_target = str(target).replace("'", "''")
    subprocess.run(['powershell.exe','-NoProfile','-Command',
        f"New-Item -ItemType Junction -Path '{quoted_path}' -Target '{quoted_target}' | Out-Null"], check=True,
        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)


def prompts(website):
    # Exact preserved prompts; only the disposable path/preview port vary.
    return [f'can inspect and summarize this project please {website}',
        'can you start the npm server in the anim folder?',
        'great. currently the first section animation is disabled, can you re-enable it?\\']


def allowed_shell(arguments, project):
    if arguments.get('action') in {'list','status','stop'}:
        return True  # This runtime owns every session it can control.
    if Path(arguments.get('workdir','')).resolve() != project.resolve():
        return False
    command = arguments.get('command','').strip()
    return re.fullmatch(r'npm(?:\.cmd)? run (?:build|dev|preview)(?: -- --host 127\.0\.0\.1(?: --port [0-9]{1,5})?)?',command) is not None


def remaining_owned_processes(identities, process_lookup):
    """A reused PID is not an owned process left behind by this replay."""
    remaining = []
    for pid, created in identities:
        try:
            if process_lookup(pid).create_time() == created:
                remaining.append(pid)
        except OSError:
            pass
    return remaining


def replay(frozen, folder, dependencies, key_file):
    from app.agent.bootstrap import build_agent_runtime
    from app.capabilities.contracts import CapabilityExecutionError, CapabilityErrorCode
    from app.capabilities.project_verification import run_worker
    from app.conversation.orchestrator import ConversationService
    from app.conversation.store import ConversationStore
    from app.inference.openai_backend import OpenAIResponsesInferenceEngine
    from app.runtime.cancellation import CancellationToken
    from app.security.host_access import HostAccessPolicy
    from app.settings.agent import load_agent_feature_config
    from app.settings.cloud import load_cloud_config
    import psutil

    folder.mkdir(parents=True,exist_ok=False)
    website, project = folder/'website', folder/'website/anim'
    project.mkdir(parents=True)
    for name in ('src','public','.figma'):
        shutil.copytree(frozen/name,project/name)
    for name in ('package.json','index.html','tsconfig.json','vite.config.ts'):
        shutil.copy2(frozen/name,project/name)
    junction(project/'node_modules',dependencies)
    port = free_port()
    config = project/'vite.config.ts'
    config.write_text(config.read_text(encoding='utf-8').replace("'8443'",repr(str(port))),encoding='utf-8')
    portable = folder/'portable'; state = portable/'state';state.mkdir(parents=True)
    junction(state/'playwright',ROOT/'state/playwright')
    summary = dict(status='running',model=None,requests=0,image_inputs=0,turns=[],
        repairs=0,inspections=0,failed_inspections=0,denied_approvals=0,
        owned_resources_released=False,independent_acceptance=None,
        later_exact_prompt_gate='skipped_original_prompt_unavailable')
    def save():
        (folder/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')

    class FixturePolicy(HostAccessPolicy):
        def resolve_read(self, raw_path):
            result = super().resolve_read(raw_path)
            if not result.resolved.is_relative_to(website.resolve()):
                raise CapabilityExecutionError(CapabilityErrorCode.PERMISSION_DENIED,
                    'Live verification may read only its disposable website.')
            return result

    class ObservedCloud(OpenAIResponsesInferenceEngine):
        def _request(self, inputs, **kwargs):
            summary['requests'] += 1
            summary['image_inputs'] += sum(part.get('type') in {'input_image','image_url'}
                for item in inputs for part in item.get('content',[]) if isinstance(part,dict))
            save()
            return super()._request(inputs,**kwargs)

    with key_file.open(encoding='utf-8-sig') as stream:
        match = re.search(r'sk-[A-Za-z0-9_-]+',stream.read())
    if match is None:
        raise ValueError('credential_unavailable')
    engine = ObservedCloud(load_cloud_config(),api_key=match.group(),selection_path=folder/'selection.json')
    del match
    summary['model'] = engine.active_model
    policy = FixturePolicy.full_local(application_root=portable,user_home=website,acknowledged=True)
    runtime = build_agent_runtime(engine,config=load_agent_feature_config(),portable_root=portable,
        state_directory=state,host_access_policy=policy)
    service = ConversationService(engine,ConversationStore(state/'history.json',start_fresh=True),
        agent_runtime=runtime,portable_root=portable,host_access_policy=policy)

    def approve(record):
        allowed = False
        try:
            path = Path(record.resource).resolve()
            allowed = record.capability in {'filesystem.edit_text','filesystem.write_text','filesystem.mkdir'} and path.is_relative_to(project.resolve()) and 'node_modules' not in path.parts
            allowed |= record.capability in {'project.verify','project.inspect'} and path == project.resolve()
            if record.capability == 'shell.run':
                preview = record.approval_preview
                allowed = allowed_shell(json.loads(preview[preview.index('{'):]),project)
        except (ValueError,TypeError,OSError):
            allowed = False
        summary['denied_approvals'] += not allowed
        save()
        service.resolve_approval(record.approval_id,allowed)

    service.set_approval_requester(approve)
    owned_identities = set()
    try:
        for index,prompt in enumerate(prompts(website),1):
            timer = Timer(600,service.cancel_current_task);timer.daemon=True;timer.start()
            try:
                service.run(prompt)
            except Exception as error:
                summary['exception_type'] = type(error).__name__
            finally:
                timer.cancel()
            result = service._turn_result
            turn = dict(turn=index,status=result.status.value if result else 'unavailable')
            if result:
                turn['completion_status'] = result.completion_review.status if result.completion_review else None
                turn['calls'] = len(result.settled_calls)
                for settled in result.settled_calls:
                    output = settled.result.output or {}
                    if settled.call.capability in {'filesystem.edit_text','filesystem.write_text'} and settled.result.success:
                        summary['repairs'] += 1
                    if settled.call.capability == 'project.inspect':
                        summary['inspections'] += 1
                        summary['failed_inspections'] += output.get('passed') is not True
            summary['turns'].append(turn)
            save()
            print(json.dumps({'attempt':folder.name,**turn,'requests':summary['requests']}),flush=True)
            if not result or result.status.value != 'completed':
                break
        summary['status'] = summary['turns'][-1]['status']
    finally:
        sessions = runtime.registry.resolve('shell.run').sessions
        for session in sessions._sessions.values():
            try:
                if session._process.poll() is not None:
                    continue
                process = psutil.Process(session._process.pid)
                identity = (process.pid,process.create_time())
                if session._process.poll() is not None:
                    continue
                owned_identities.add(identity)
                owned_identities.update((p.pid,p.create_time()) for p in process.children(recursive=True))
            except psutil.Error:
                pass
        service.shutdown();engine.close()
        def process_lookup(pid):
            try:
                return psutil.Process(pid)
            except psutil.Error as error:
                raise OSError from error
        remaining = remaining_owned_processes(owned_identities,process_lookup)
        summary['remaining_owned_process_count'] = len(remaining)
        summary['owned_resources_released'] = engine._runner is None and not remaining and all(
            s['owned_processes_released'] for s in sessions.list()['sessions'])
        save()
    # A fresh independent worker assesses the result even when the agent stops.
    acceptance = folder/'acceptance.json'
    result = run_worker([sys.executable,str(ROOT/'tools/scroll_acceptance.py'),'--url',f'http://127.0.0.1:{free_port()}/',
        '--project',str(project),'--output',str(acceptance)],cwd=ROOT,timeout=60,
        cancellation=CancellationToken(),job_memory_bytes=4*1024**3)
    summary['acceptance_worker_released'] = result['owned_processes_released']
    summary['independent_acceptance'] = json.loads(acceptance.read_text())['passed'] if acceptance.is_file() else False
    summary['acceptance_available'] = acceptance.is_file()
    save()
    print(json.dumps({'attempt':folder.name,'status':summary['status'],
        'independent_acceptance':summary['independent_acceptance'],'owned_resources_released':summary['owned_resources_released']}),flush=True)
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--frozen',type=Path,required=True)
    parser.add_argument('--dependencies',type=Path,required=True)
    parser.add_argument('--key-file',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--attempts',type=int,default=3,choices=range(1,6))
    args = parser.parse_args()
    for name in ('frozen','dependencies','key_file','output'):
        setattr(args,name,getattr(args,name).resolve())
    if not args.output.resolve().is_relative_to((ROOT/'state').resolve()):
        parser.error('Live output must stay under repository state.')
    logging.disable(logging.CRITICAL)
    before = source_hashes(args.frozen)
    expected = json.loads((args.frozen.parent/'hashes.json').read_text(encoding='utf-8'))[args.frozen.name]
    if before != expected:
        parser.error('Frozen source differs from its preserved manifest.')
    settings = {str(p):sha256(p.read_bytes()).hexdigest() for p in (ROOT/'config').glob('*.json')}
    results = [replay(args.frozen,args.output/f'attempt-{index}',args.dependencies,args.key_file)
        for index in range(1,args.attempts+1)]
    summary = dict(attempts=results,frozen_source_unchanged=source_hashes(args.frozen)==before,
        settings_unchanged=all(sha256(Path(p).read_bytes()).hexdigest()==digest for p,digest in settings.items()),
        passed=all(r['status']=='completed' and r['independent_acceptance'] and r['owned_resources_released'] for r in results))
    (args.output/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps({'attempts':len(results),'passed':summary['passed']}),flush=True)


if __name__ == '__main__':
    main()
