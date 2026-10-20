"""Reconstruct complete source evidence from original contiguous read receipts."""
import codecs
from dataclasses import dataclass
import hashlib
import os


def path_key(value):
    return os.path.normcase(os.path.normpath(value)) if isinstance(value, str) else None


def shell_may_mutate(call):
    return call.capability == 'shell.run' and call.arguments.get('action', 'run') not in {'status', 'list'}


def invalidate_read_cache(reads, call, result):
    """Invalidate turn-local eligibility after a possibly mutating dispatch.

    A runtime preflight rejection never reached the file. Its observed source
    stays usable; an unknown/failed dispatched operation is conservative.
    """
    if call.capability == 'filesystem.read_text':
        # A failed or partial new observation cannot keep an older complete
        # read eligible. The caller restores eligibility only on a full proof.
        reads.pop(path_key(call.arguments.get('path')), None)
        reads.pop(path_key((result.output or {}).get('path')), None)
        return
    if result.metadata.get('edit_recovery'):
        return
    if shell_may_mutate(call):
        reads.clear()
    elif call.capability in {'filesystem.edit_text', 'filesystem.write_text',
            'filesystem.copy', 'filesystem.move', 'filesystem.trash'}:
        for key in ('path', 'source_path', 'destination_path'):
            reads.pop(path_key(call.arguments.get(key)), None)
        reads.pop(path_key((result.output or {}).get('path')), None)


@dataclass(frozen=True)
class SourceProof:
    sha256: str
    call_ids: tuple[str, ...]


def source_read_proof(settled, prior_calls=()):
    """Hash observed bytes, including an initial BOM, never a metadata revision.

    No source body is added to goals or diagnostics. Replaying original receipts
    produces the same proof at runtime, history validation and archive restore.
    """
    if settled.call.capability != 'filesystem.read_text' or not settled.result.success:
        return None
    target = path_key((settled.result.output or {}).get('path'))
    if target is None:
        return None
    digest, revision, end, total, ids = None, None, 0, None, []
    for item in (*prior_calls, settled):
        call, result = item.call, item.result
        output = result.output or {}
        if shell_may_mutate(call) or call.capability in {
                'filesystem.edit_text', 'filesystem.write_text', 'filesystem.copy', 'filesystem.move', 'filesystem.trash'} and any(
                    path_key(call.arguments.get(key)) == target for key in ('path', 'source_path', 'destination_path')):
            digest, ids = None, []
        if call.capability != 'filesystem.read_text' or path_key(output.get('path') or call.arguments.get('path')) != target:
            continue
        if not result.success or result.metadata.get('context_projection'):
            digest, ids = None, []
            continue
        start, stop, size = (output.get(key) for key in ('offset', 'end_offset', 'total_size_bytes'))
        text, codec, rev = output.get('text'), output.get('page_encoding'), output.get('revision')
        if (any(type(n) is not int for n in (start, stop, size)) or not 0 <= start <= stop <= size
                or not isinstance(text, str) or codec not in {'utf-8', 'utf-16-le', 'utf-16-be'}
                or not isinstance(rev, str) or len(rev) != 64):
            digest, ids = None, []
            continue
        if start == 0:
            digest, revision, end, total, ids = hashlib.sha256(), rev, 0, size, []
        if digest is None or start != end or rev != revision or size != total:
            digest, ids = None, []
            continue
        text_offset = output.get('text_offset', start)
        if type(text_offset) is not int:
            digest, ids = None, []
            continue
        prefix = text_offset - start
        bom = {('utf-8', 3): codecs.BOM_UTF8, ('utf-16-le', 2): codecs.BOM_UTF16_LE,
               ('utf-16-be', 2): codecs.BOM_UTF16_BE}.get((codec, prefix), b'')
        try:
            raw = bom + text.encode(codec)
        except UnicodeError:
            digest, ids = None, []
            continue
        if (prefix and (start != 0 or not bom)) or len(raw) != stop - start:
            digest, ids = None, []
            continue
        digest.update(raw)
        end = stop
        ids.append(result.call_id)
    if digest is not None and ids and ids[-1] == settled.result.call_id and end == total and output.get('has_more') is False:
        return SourceProof(digest.hexdigest(), tuple(ids))
    return None
