"""Turn-local completeness for explicitly requested full Office reads."""
from __future__ import annotations

import json


class OfficeReadProgress:
    def __init__(self):
        self.pending = {}
        self.failed = {}
        self.reminded = None
        self.applied = set()
        self.saved = set()

    def observe(self, call, result):
        session = call.arguments.get("session")
        if call.capability in {"office.excel_edit", "office.revert", "office.save"}:
            output = result.output or {}
            if result.success and isinstance(session, str) and session:
                if output.get("outcome") == "applied":
                    self.applied.add(session)
                    self.saved.discard(session)
                elif call.capability == "office.save" and output.get("saved") is True:
                    self.saved.add(session)
            return
        if call.capability != "office.read":
            return
        target = call.arguments.get("target", "selection")
        if not isinstance(target, str) or not (target == "workbook" or target.endswith("!used")):
            return
        session = call.arguments.get("session")
        if not isinstance(session, str) or not session:
            return
        key = (session, target)
        if result.success:
            if (result.output or {}).get("application", "excel") != "excel":
                return
            cursor = (result.output or {}).get("cursor")
            self.failed.pop(key, None)
            if cursor:
                self.pending[key] = cursor
            else:
                self.pending.pop(key, None)
        elif key in self.pending:
            self.pending.pop(key, None)
            self.failed[key] = result.error.message

    def before_final(self):
        if self.failed:
            return False, "The full workbook read remains unfinished: " + next(iter(self.failed.values()))
        if not self.pending:
            return None
        requests = [{"session": session, "target": target, "cursor": cursor}
                    for (session, target), cursor in self.pending.items()]
        identity = json.dumps(requests, ensure_ascii=False, sort_keys=True)
        message = ("The full workbook read is unfinished. Continue office.read with these exact "
                   "session/target/cursor arguments until each cursor is null before reporting complete "
                   "results or whole-sheet KPIs. Existing permissions and budgets still apply: " + identity)
        changed = identity != self.reminded
        self.reminded = identity
        return changed, message

    def unfinished_summary(self):
        message = ("Task unfinished. The complete workbook read did not finish. "
                   "Read the remaining worksheet pages before relying on whole-sheet calculations.")
        if self.failed:
            message += " " + next(iter(self.failed.values()))
        affected = {session for session, _ in (*self.pending, *self.failed)}
        if affected & self.applied:
            message += " Earlier Excel changes were confirmed applied; the later read failure does not undo them."
        if affected & self.saved:
            message += " An earlier save was confirmed; the later read failure does not invalidate that save receipt."
        return message
