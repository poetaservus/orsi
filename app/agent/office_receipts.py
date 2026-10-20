"""Shared narrow classification of host-validated settled Office receipts.

Native adapters own resource identity, snapshot validation and write authority.
These extra checks only prevent recovery/evidence accounting from mistaking a
mismatched, malformed or uncertain receipt for confirmed document progress.
"""
from app.capabilities.contracts import CapabilityErrorCode


OFFICE_MUTATIONS = frozenset({'office.excel_edit', 'office.word_edit', 'office.word_compose',
                             'office.powerpoint_edit', 'office.revert'})
UNCERTAIN = frozenset({CapabilityErrorCode.OUTCOME_UNKNOWN, CapabilityErrorCode.CANCELLED,
    CapabilityErrorCode.TIMED_OUT, CapabilityErrorCode.INTERNAL_ERROR, CapabilityErrorCode.INVALID_OUTPUT})
APPLICATIONS = frozenset({'excel', 'word', 'powerpoint'})


def _identifier(value):
    return isinstance(value, str) and 0 < len(value) <= 256


def office_receipt_event(call, result):
    if not call.capability.startswith('office.'):
        return None
    name = call.capability
    output = result.output if isinstance(result.output, dict) else {}
    session = call.arguments.get('session')
    session = session if _identifier(session) else None
    # A purported successful write without its exact receipt cannot prove that
    # nothing changed. Conservatively stale prior observations without earning
    # any progress/renewal; validated successful outcomes clear this below.
    event = {'kind': 'unverified', 'session': session,
             'uncertain': name in OFFICE_MUTATIONS | {'office.save'}}
    if result.capability != name:
        return event
    application = call.arguments.get('application') if name in {'office.documents', 'office.attach'} else None
    if application in APPLICATIONS:
        event['application'] = application
    if not result.success:
        code = result.error.code if result.error is not None else None
        return {**event, 'kind': 'failed', 'error_code': str(code) if code is not None else None,
                'uncertain': name in OFFICE_MUTATIONS | {'office.save'} and code in UNCERTAIN}
    if name == 'office.documents':
        if isinstance(output.get('documents'), list):
            event['kind'] = 'documents'
        return event
    if name == 'office.attach':
        document = output.get('document')
        if (isinstance(document, dict) and _identifier(output.get('session'))
                and _identifier(document.get('document')) and document.get('application') in APPLICATIONS
                and document.get('document') == call.arguments.get('document')
                and document.get('application') == call.arguments.get('application')):
            return {**event, 'kind': 'attach', 'session': output['session'],
                    'document': document['document'], 'application': document['application']}
        return event
    if session is None or output.get('session') != session:
        return event
    if name == 'office.read':
        if (_identifier(output.get('snapshot')) and output.get('application') in APPLICATIONS
                and (output.get('cursor') is None or _identifier(output.get('cursor')))):
            return {**event, 'kind': 'read', 'application': output['application'],
                    'snapshot': output['snapshot'], 'cursor': output.get('cursor')}
        return event
    if output.get('operation') != result.call_id:
        return event
    event['operation'] = result.call_id
    if name in OFFICE_MUTATIONS:
        affected = output.get('affected_items')
        if type(affected) is int:
            if output.get('outcome') == 'applied' and affected > 0:
                event['kind'] = 'applied'
            elif output.get('outcome') == 'unchanged' and affected == 0:
                event['kind'] = 'unchanged'
    elif name == 'office.save' and output.get('saved') is True:
        event['kind'] = 'saved'
    if event['kind'] in {'applied', 'unchanged', 'saved'}:
        event['uncertain'] = False
    return event
