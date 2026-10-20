"""Scoped recovery accounting; settled progress never grants execution authority."""
from dataclasses import dataclass, field
import os

from app.agent.feedback import call_fingerprint


def recovery_scope(call):
    args = call.arguments
    target = next((args.get(key) for key in ('path', 'project_path', 'session_id')
                   if isinstance(args.get(key), str)), '')
    return call.capability + ':' + os.path.normcase(os.path.normpath(target))


@dataclass
class RecoveryProgress:
    failures: dict[str, int] = field(default_factory=dict)
    review_failures: int = 0
    revisions: dict[str, str] = field(default_factory=dict)
    observations: set[tuple] = field(default_factory=set)

    def correct(self, scope):
        self.failures[scope] = self.failures.get(scope, 0) + 1

    def exhausted(self, limit):
        return self.review_failures >= limit or any(n >= limit for n in self.failures.values())

    def observe(self, call, result, repeated, *, scope=None, office_changed=False):
        if not result.success:
            return
        output = result.output or {}
        scope = scope or recovery_scope(call)
        changed = False
        if call.capability.startswith('office.'):
            # Office uses trusted document aliases, not one shared empty target.
            # Successful operations resolve only their own argument failure;
            # bounded review renewal requires confirmed new document progress.
            self.failures.pop(scope, None)
            changed = office_changed
        elif call.capability == 'filesystem.read_text':
            # A corrected read resolves only its own argument recovery.
            self.failures.pop(scope, None)
            if isinstance(output.get('path'), str) and isinstance(output.get('sha256'), str):
                self.revisions[os.path.normcase(os.path.normpath(output['path']))] = output['sha256']
        elif call.capability in {'filesystem.edit_text', 'filesystem.write_text'}:
            path, digest = output.get('path'), output.get('sha256')
            if isinstance(path, str) and isinstance(digest, str):
                path = os.path.normcase(os.path.normpath(path))
                previous = self.revisions.get(path)
                changed = previous != digest and (call.capability == 'filesystem.edit_text'
                    or previous is not None or output.get('operation') == 'created')
                self.revisions[path] = digest
                if changed:
                    self.failures.pop(scope, None)
        elif call.capability in {'project.verify', 'project.inspect'}:
            # A normalized tool result resolves argument recovery even when the
            # inspected project still fails. Only a novel pass renews review.
            self.failures.pop(scope, None)
            if output.get('passed') is True:
                key = (call_fingerprint(call), tuple(sorted(self.revisions.items())))
                changed = key not in self.observations
                self.observations.add(key)
        elif call.capability == 'shell.run':
            session = output.get('session_id')
            if call.arguments.get('action') == 'status' and session == call.arguments.get('session_id'):
                if output.get('running') is True:
                    # Only an observed owned live session earns another poll.
                    repeated.pop(call_fingerprint(call), None)
                elif output.get('command_completed') is True:
                    key = ('shell', session, output.get('exit_code'), output.get('stop_reason'))
                    changed = key not in self.observations
                    self.observations.add(key)
                    self.failures.pop(scope, None)
        else:
            self.failures.pop(scope, None)
        self.failures.pop('catalog', None)
        if call.capability.startswith('filesystem.'):
            self.failures.pop('filename', None)
        if changed:
            self.review_failures = 0
