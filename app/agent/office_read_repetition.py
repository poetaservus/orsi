"""Renew initial Office reads only after a settled change in that session."""
from app.agent.feedback import call_fingerprint


class OfficeReadRepetition:
    def __init__(self):
        self._reads = {}

    def observe(self, call, result, repeated):
        output = result.output
        if not result.success or not isinstance(output, dict):
            return
        session = call.arguments.get("session")
        if not isinstance(session, str) or not session or output.get("session") != session:
            return
        if call.capability == "office.read":
            # A changed document needs a fresh read, never a replay of an old
            # cursor. Failed/unsupported targets do not earn new attempts.
            if call.arguments.get("cursor") is None:
                self._reads[call_fingerprint(call)] = session
            return
        if (call.capability not in {"office.word_edit", "office.word_compose", "office.excel_edit", "office.revert"}
                or output.get("operation") != result.call_id or output.get("outcome") != "applied"
                or type(output.get("affected_items")) is not int or output["affected_items"] <= 0):
            return
        for fingerprint, read_session in self._reads.items():
            if read_session == session:
                repeated.pop(fingerprint, None)
