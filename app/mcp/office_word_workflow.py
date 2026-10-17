"""Revision-bound Word evidence. No complete document bodies are retained here."""
from hashlib import sha256

from app.mcp.office_contracts import canonical_json
from app.mcp.office_excel import OfficeConflict


def digest(value):
    return sha256(canonical_json(value).encode()).hexdigest()


class WordWorkflow:
    def __init__(self):
        self.revision = None
        self.rendered = set()
        self.delivered = set()
        self.page_count = None
        self.authoring = None
        self.review = None
        self.saved = None
        self.saves = []
        self.edited = False
        self.composed = False
        self.saved_after_review = False
        self.visits = {}
        self.cycle = False
        self.pass_authorized = False
        self.corrections = set()
        self.correction_key = None
        self.blocker = None

    def sync(self, revision):
        if revision != self.revision:
            self.revision = revision
            self.blocker = None
            self.rendered.clear()
            self.delivered.clear()
            self.page_count = None
            self.authoring = self.review = self.saved = None
            self.pass_authorized = False
            self.saved_after_review = False
            self.visits[revision] = self.visits.get(revision, 0) + 1
            self.cycle = self.visits[revision] > 1

    def inspect(self, arguments):
        if len(canonical_json(arguments.model_dump()).encode()) > 4_000:
            raise OfficeConflict("Word findings exceed the bounded review size. Consolidate concrete defects.")
        if arguments.revision != self.revision:
            raise OfficeConflict("Inspection findings refer to an old Word revision. Inspect current pages.")
        if self.page_count is None or self.delivered != set(range(1, self.page_count + 1)):
            raise OfficeConflict("Inspect every current Word page image before recording findings; layout alone is insufficient.")
        if any(not value.strip() for f in arguments.findings for value in (f.location, f.defect, f.requirement)):
            raise OfficeConflict("Each correction needs an observed defect, location and unmet user requirement.")
        if not all(value.strip() for value in arguments.requirements_checked):
            raise OfficeConflict("Identify the user requirements checked against this revision.")
        if arguments.requirements_met and arguments.findings:
            raise OfficeConflict("Resolve the recorded defects before reporting requirements met.")
        findings = [f.model_dump() for f in arguments.findings]
        # Repeated content with the same unresolved findings is a cycle, regardless
        # of transport snapshot IDs. Novel observed defects can justify more work.
        key = digest([self.revision, sorted({" ".join(f["requirement"].casefold().split()) for f in findings})])
        if findings and key in self.corrections:
            self.cycle = True
            raise OfficeConflict("Word revision cycle: this revision and the same unmet requirements already received a correction pass. Work is preserved; stop and report the unresolved defects.")
        self.saved_after_review = False
        self.review = {"revision": self.revision, "findings": findings,
                       "requirements_met": arguments.requirements_met,
                       "requirements_checked": list(arguments.requirements_checked)}
        self.pass_authorized = bool(findings)
        self.correction_key = key

    def before_edit(self):
        if (self.edited or self.composed) and not self.pass_authorized:
            raise OfficeConflict("A further Word edit requires current page inspection and concrete defect/location/unmet requirement findings via word_review. Do not replay settled edits or rewrite for vague cosmetic improvement.")

    def applied(self, revision):
        if self.pass_authorized:
            self.corrections.add(self.correction_key)
        self.edited = True
        self.sync(revision)
        # Even an equivalent revision cannot inherit inspection/save evidence.
        self.rendered.clear()
        self.delivered.clear()
        self.page_count = None
        self.authoring = self.review = self.saved = None
        self.pass_authorized = False
        self.saved_after_review = False

    def invalidate(self):
        self.revision = None
        self.authoring = self.review = self.saved = None
        self.rendered.clear()
        self.delivered.clear()
        self.page_count = None
        self.pass_authorized = self.saved_after_review = False
        self.blocker = "The Word action settled, but its current revision evidence could not be captured. Inspect the current document; completion remains unverified."

    def save(self, operation):
        self.saved = {"revision": self.revision, "operation": operation}
        self.saves.append(self.saved.copy())
        self.saved_after_review = bool(self.review and self.review["requirements_met"] and not self.review["findings"])

    def evidence(self):
        clean = self.review is not None and self.review["requirements_met"] and not self.review["findings"]
        return {"revision": self.revision, "edited": self.edited,
                "authoring_snapshot": self.authoring, "rendered_pages": sorted(self.rendered), "image_pages": sorted(self.delivered),
                "page_count": self.page_count, "review": self.review,
                "current_save": self.saved, "save_receipts": self.saves[-8:], "save_receipt_count": len(self.saves),
                "revision_repeated": self.cycle, "blocker": self.blocker,
                "verified_saved": bool(clean and self.saved and self.saved_after_review and not self.blocker)}
