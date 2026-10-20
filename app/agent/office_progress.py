"""Bounded Office recovery accounting from settled, host-validated receipts.

Renewal changes only repetition accounting. It never dispatches/replays a call,
validates a native snapshot, or replaces resource binding and approval checks.
"""
from dataclasses import dataclass, field
from hashlib import sha256
import os

from app.agent.feedback import call_fingerprint
from app.agent.office_receipts import OFFICE_MUTATIONS, office_receipt_event
from app.mcp.office_contracts import OFFICE_TOOLS


_CONTRACTS = {tool.name: tool for tool in OFFICE_TOOLS}


def _arguments(call):
    contract = _CONTRACTS.get(call.capability)
    if contract is None:
        return None
    try:
        return contract.arguments.model_validate(call.arguments).model_dump(mode='json')
    except ValueError:
        return None


@dataclass
class _Document:
    application: str | None = None
    revision: int = 0
    saved_revision: int | None = None
    receipt: str | None = None
    blocked: bool = False
    destinations: set[str] = field(default_factory=set)


class OfficeProgress:
    def __init__(self):
        self.epoch = None
        self.application = None
        self.bindings = {}
        self.documents = {}
        self.registered = {}
        self.seen = set()
        self.pages = {}
        self.complete = {}
        self.rejected = {}
        self.retried = set()

    def sync(self, connection):
        """Observe trusted host connection state; never obtain execution authority."""
        if connection is not None:
            self.epoch = (id(connection), connection.exposure.generation)
            self.application = connection.selected_application

    def _key(self, session):
        session = session if isinstance(session, str) else None
        return self.bindings.get(session, (self.epoch, 'session', session))

    def _state(self, session):
        return self.documents.setdefault(self._key(session), _Document(self.application))

    def fingerprint(self, call):
        args = _arguments(call)
        if args is None:
            return call_fingerprint(call)
        session = args.get('session')
        if session:
            args['session'] = repr(self._key(session))
        # A new snapshot token is a prerequisite, not a different write intent.
        # One rejected intent may earn a retry from a later complete read.
        if call.capability in OFFICE_MUTATIONS:
            args.pop('snapshot', None)
        args['_office_connection'] = repr(self.epoch)
        return call_fingerprint(call.model_copy(update={'arguments': args}))

    def scope(self, call):
        session = call.arguments.get('session')
        args = {'binding': repr(self._key(session))} if session else {'connection': repr(self.epoch)}
        return call.capability + ':' + call_fingerprint(call.model_copy(update={'arguments': args}))

    def renew(self, call, *, step):
        if call.capability not in OFFICE_MUTATIONS or _arguments(call) is None:
            return False
        session, snapshot = call.arguments.get('session'), call.arguments.get('snapshot')
        state = self._state(session)
        key = self.fingerprint(call)
        rejected = self.rejected.get(key)
        read = self.complete.get((session, snapshot))
        if (state.blocked or key in self.retried or rejected is None or read is None
                or rejected[1] != state.revision or read[2] != state.revision
                or not rejected[0] < read[0] <= read[1] < step):
            return False
        self.retried.add(key)
        return True

    def diagnostic(self, call):
        session = call.arguments.get('session')
        state = self.documents.get(self._key(session)) if session else None
        if state is None and call.capability == 'office.documents':
            application = call.arguments.get('application')
            state = next((value for key, value in reversed(tuple(self.documents.items()))
                if key[0] == self.epoch and (application is None or value.application == application)), None)
        if state is None:
            return {'office_progress_revision': 0, 'office_state_reason': 'no_progress_observed'}
        stale_connection = self._key(session)[0] != self.epoch
        reason = ('connection_changed' if stale_connection else
                  'session_blocked' if state.blocked else
                  'retry_allowance_exhausted' if self.fingerprint(call) in self.retried else
                  'snapshot_required' if self.fingerprint(call) in self.rejected else
                  'current_revision_already_saved' if call.capability == 'office.save'
                      and state.saved_revision == state.revision else 'no_progress_observed')
        return {'office_progress_revision': state.revision, 'office_state_reason': reason,
                'evidence_receipt': state.receipt}

    def _renew_observations(self, key, state, repeated, *, saved=False):
        for fingerprint, (kind, target) in self.registered.items():
            if kind == 'documents':
                relevant = target[0] == self.epoch and (target[1] is None or target[1] == state.application)
            else:
                relevant = target == key and not saved and kind in {'read', 'save'}
            if relevant:
                repeated.pop(fingerprint, None)

    def _read(self, call, event, state, *, step):
        session, snapshot = event['session'], event['snapshot']
        signature = (session, call.arguments.get('target', 'selection'),
                     call.arguments.get('max_items', 100), call.arguments.get('max_chars', 4096))
        cursor = call.arguments.get('cursor')
        prior = self.pages.get(signature)
        if cursor is None:
            self._invalidate_read(call)
            start = step
        elif prior is not None and prior[:3] == (cursor, snapshot, state.revision):
            start = prior[3]
        else:
            return
        if event['cursor'] is None:
            self.pages.pop(signature, None)
            self.complete[(session, snapshot)] = (start, step, state.revision, signature[1])
        else:
            self.pages[signature] = (event['cursor'], snapshot, state.revision, start)

    def _invalidate_read(self, call):
        session, target = call.arguments.get('session'), call.arguments.get('target', 'selection')
        self.complete = {key: value for key, value in self.complete.items()
                         if key[0] != session or value[3] != target}
        self.pages = {key: value for key, value in self.pages.items()
                      if key[0] != session or key[1] != target}

    def observe(self, call, result, repeated, *, step):
        event = office_receipt_event(call, result)
        if event is None or result.call_id in self.seen:
            return False
        self.seen.add(result.call_id)
        kind, session = event['kind'], event['session']
        if kind == 'attach':
            self.bindings[session] = (self.epoch, event['application'], event['document'])
        elif session:
            # Sessions attached before this turn still belong to their observed
            # connection epoch; a reconnect cannot silently rebind an old token.
            self.bindings.setdefault(session, (self.epoch, 'session', session))
        state = self._state(session) if session else None
        if state is not None and event.get('application'):
            state.application = event['application']
        args = _arguments(call)
        fingerprint = self.fingerprint(call)
        key = self._key(session) if session else None
        current = key is not None and key[0] == self.epoch
        if kind == 'documents' and args is not None and args['cursor'] is None:
            self.registered[fingerprint] = ('documents', (self.epoch, args['application']))
        if state is None or not current:
            return False
        if kind == 'failed':
            if call.capability == 'office.read':
                self._invalidate_read(call)
            if event['uncertain'] or event.get('error_code') == 'permission_denied':
                state.blocked = True
                self.complete = {k: v for k, v in self.complete.items() if self._key(k[0]) != key}
            elif (call.capability in OFFICE_MUTATIONS and args is not None
                    and event.get('error_code') == 'invalid_arguments'):
                self.rejected.setdefault(fingerprint, (step, state.revision))
            state.receipt = result.call_id
            return False
        if kind == 'unverified' and call.capability in OFFICE_MUTATIONS | {'office.save'}:
            state.blocked = True
        if args is None or state.blocked:
            return False
        if kind == 'read':
            if args['cursor'] is None:
                self.registered[fingerprint] = ('read', key)
            self._read(call, event, state, step=step)
            state.receipt = result.call_id
        elif kind == 'saved':
            self.registered[fingerprint] = ('save', key)
            destination = args.get('path')
            destination = (sha256(os.path.normcase(os.path.normpath(destination)).encode()).hexdigest()
                           if destination else None)
            new_destination = destination is not None and destination not in state.destinations
            if destination:
                state.destinations.add(destination)
            if state.saved_revision != state.revision or new_destination:
                state.saved_revision, state.receipt = state.revision, result.call_id
                self._renew_observations(key, state, repeated, saved=True)
                return True
        elif kind == 'applied':
            state.revision += 1
            state.receipt = result.call_id
            self.complete = {k: v for k, v in self.complete.items() if self._key(k[0]) != key}
            self._renew_observations(key, state, repeated)
            return True
        return False
