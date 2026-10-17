"""Local Word outcome reporting; receipts survive a failed closing response."""
from app.agent.contracts import AgentRunStatus


def word_stop_report(result):
    if result.status == AgentRunStatus.COMPLETED:
        return None
    evidence = {}
    for settled in result.settled_calls:
        output = settled.result.output or {}
        session = settled.call.arguments.get("session")
        if settled.result.success and isinstance(output.get("word_workflow"), dict):
            evidence[session] = output["word_workflow"]
        elif session in evidence and not settled.result.success and settled.call.capability in {
                "office.word_compose", "office.word_edit", "office.revert"}:
            evidence[session] = {**evidence[session], "review": None, "current_save": None,
                                 "verified_saved": False}
    if not evidence:
        return None
    lines = ["Word work is retained; the overall task did not complete."]
    for item in evidence.values():
        saved = item.get("current_save")
        receipts = item.get("save_receipts", [])
        review = item.get("review")
        if item.get("blocker"):
            lines.append(item["blocker"])
        lines.append("Current revision: " + str(item.get("revision")) + ".")
        if saved:
            lines.append("Successful save receipt for this revision: " + saved["operation"] + ".")
        elif receipts:
            lines.append("Earlier successful saves are retained; they do not confirm saving the current revision.")
        else:
            lines.append("No successful save receipt for this revision was recorded.")
        if review is None:
            lines.append("Current page inspection and user requirements remain unverified.")
        elif review.get("requirements_met") and not review.get("findings"):
            lines.append("A clean page/requirements review was recorded for this revision; it does not prove the closing response succeeded.")
        else:
            lines.append("Recorded requirements remain unmet.")
            for finding in review.get("findings", []):
                lines.append(f"- {finding['location']}: {finding['defect']} Requirement: {finding['requirement']}")
    return "\n".join(lines)


class WordTurnProgress:
    """Word-only continuation gates; shared recovery budgets stay authoritative."""
    def __init__(self):
        self.evidence = {}
        self.images = {}
        self.reminded = None
        self.writing_sessions = set()

    def observe(self, call, result):
        if not call.capability.startswith("office."):
            return None
        session = call.arguments.get("session")
        if (call.capability in {"office.word_edit", "office.word_compose"} and
                (not result.success or session in self.evidence or
                 isinstance((result.output or {}).get("word_workflow"), dict))):
            self.writing_sessions.add(session)
            self.evidence.setdefault(session, {"edited": False, "verified_saved": False, "revision": None})
        if not result.success:
            if session in self.evidence and call.capability in {
                    "office.word_edit", "office.word_compose", "office.revert", "office.save"}:
                prior = self.evidence[session]
                self.evidence[session] = {**prior, "verified_saved": False,
                    "blocker": result.error.code.value if result.error else "failed",
                    **({"review": None, "current_save": None} if call.capability != "office.save" else {})}
            return None
        evidence = (result.output or {}).get("word_workflow")
        if not isinstance(evidence, dict):
            return None
        previous = self.evidence.get(session, {})
        if previous.get("revision") != evidence.get("revision") or (result.output or {}).get("outcome") == "applied":
            self.images = {key: value for key, value in self.images.items() if key[0] != session}
        self.evidence[session] = evidence
        if evidence.get("verified_saved"):
            return ("The current Word revision has a clean requirements review and a save receipt. Finish now; "
                "further editing requires a concrete observed unmet requirement, not cosmetic improvement.")
        if call.capability in {"office.word_compose", "office.word_edit"}:
            return ("Word edit settled. Inspect ALL current pages through render:first:last, collect defects and "
                "checked user requirements using office.word_review. Do not rewrite without concrete findings; "
                "layout/render snapshots do not authorize compose.")
        return None

    def before(self, call):
        if call.capability != "office.word_review":
            return None
        from app.agent.edit_progress import EditRejection
        session, revision = call.arguments.get("session"), call.arguments.get("revision")
        current = self.evidence.get(session, {})
        count = current.get("page_count")
        pages = self.images.get((session, revision), set())
        if (revision != current.get("revision") or type(count) is not int
                or pages != set(range(1, count + 1))):
            return EditRejection("word_inspection",
                "Word review requires every current page image delivered to this model. Render all current pages "
                "with a vision-capable model; layout metadata, stale pages or failed image delivery cannot establish visual correctness.")
        return None

    def images_delivered(self, call, result, message):
        import json
        content = message.get("content")
        if isinstance(content, list) and any(part.get("type") == "image_url" for part in content):
            revision = (result.output.get("word_workflow") or {}).get("revision")
            pages = {json.loads(item["text"])["page"] for item in result.output["items"]}
            self.images.setdefault((call.arguments.get("session"), revision), set()).update(pages)

    def before_final(self):
        from app.mcp.office_contracts import canonical_json
        unfinished = {key: value for key, value in self.evidence.items()
                      if (value.get("edited") or key in self.writing_sessions) and not value.get("verified_saved")}
        if not unfinished:
            return None
        identity = canonical_json(unfinished)
        message = ("Word work is preserved but verification/finalization is unfinished. Inspect every current rendered "
            "page, record concrete findings and checked user requirements with office.word_review. Correct only observed "
            "defects, reread authoring completely for justified compose; never replay edits. After clean review save current "
            "revision and finish. If blocked, report the precise remaining verification and retained save receipts. Evidence: " + identity)
        retry = identity != self.reminded
        self.reminded = identity
        return retry, message
