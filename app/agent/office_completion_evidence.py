"""Receipt-scoped Office observations, without inferring document correctness.

This projection is versioned by CompletionReview, independently of project goal
history. It retains failed attempts and historical writes, while later writes
invalidate an earlier read or save as evidence of the *current* document.
"""
from app.agent.source_evidence import shell_may_mutate
from app.agent.office_receipts import UNCERTAIN, office_receipt_event


OFFICE_CLAIMS = frozenset({'observed', 'applied', 'saved', 'unchanged'})


def office_evidence(calls):
    """Compile bounded evidence from settled receipts, never from model claims.

    Live session identifiers are opaque host bindings. Successful attach receipts
    identify aliases of an exact document; absent one, keep sessions separate.
    No document path, cell contents, formulas or screenshot pixels are copied.
    """
    records, bindings, applications, revisions = {}, {}, {}, {}
    for item in calls:
        call, result = item.call, item.result
        if shell_may_mutate(call) and (result.success or result.error and result.error.code in UNCERTAIN):
            for record in records.values():
                if record['observed'] in {'observed', 'saved'} and record['scope'] in {'read_page', 'document_save'}:
                    record.update(observed='unverified', stale=True)
            continue
        event = office_receipt_event(call, result)
        if event is None:
            continue
        session, kind = event['session'], event['kind']
        if kind == 'attach':
            bindings[session] = (event['application'], event['document'])
            applications[session] = event['application']
        key = bindings.get(session, ('session', session)) if session else None
        claim, scope = {
            'documents': ('observed', 'document_metadata'), 'attach': ('observed', 'document_binding'),
            'read': ('observed', 'read_page'), 'applied': ('applied', 'document_edit'),
            'unchanged': ('unchanged', 'document_edit'), 'saved': ('saved', 'document_save'),
            'failed': ('failed', 'office_operation'),
        }.get(kind, ('unverified', 'office_operation'))
        uncertain = event['uncertain']
        if key and (claim == 'applied' or uncertain):
            revisions[key] = revisions.get(key, 0) + 1
            for record in records.values():
                if record['_binding'] == key and record['scope'] in {'read_page', 'document_save'}:
                    record.update(observed='unverified', stale=True)
        record = {'observed': claim, 'scope': scope, 'stale': False, '_binding': key,
                  'mutation_generation': revisions.get(key, 0) if key else None}
        application = applications.get(session) or event.get('application')
        if application in {'excel', 'word', 'powerpoint'}:
            record['application'] = application
        if scope == 'read_page':
            record['more_pages'] = event.get('cursor') is not None
            # A read is evidence only of its bounded target/page, not all sheets.
            target = call.arguments.get('target', 'selection')
            if isinstance(target, str):
                record['target'] = target[:256]
        if uncertain:
            record['outcome_uncertain'] = True
        records[result.call_id] = record
    return {identity: {key: value for key, value in record.items() if not key.startswith('_')}
            for identity, record in records.items()}
