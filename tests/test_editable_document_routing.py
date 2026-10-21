"""Editable document deliverables outrank their subordinate visual instructions."""
import pytest

from app.conversation.image_followup import image_route
from app.conversation.orchestrator import ConversationService
from app.conversation.store import ConversationStore
from app.inference.image_generation import ImageIntent, image_intent
from app.runtime.skills import SkillRegistry
from tests.test_cloud_attachment_input import native_sdk
from tests.test_image_generation import image_payload
from tests.test_office_mcp_capabilities import runtime_for
from tests.test_office_word_completion import connection
from tests.test_openai_phase1 import response
from tests.test_openai_tools import function


# The reported request is retained verbatim, including Markdown and filenames.
WORD_REQUEST = """Open and edit the existing Word document `article.docx`, which is already open in Microsoft Word.

Four supporting photographs are available on my Desktop:

- `1.jpg`
- `2.jpg`
- `3.jpg`
- `4.jpg`

**Task:** Transform the existing document into a professionally typeset, magazine-style editorial article with a sophisticated multi-column layout and integrated photography.

### Editorial direction

Create a publication-quality feature article inspired by contemporary independent print magazines, cultural journals, and long-form editorial publications.

The design should feel like it was produced by an experienced human editorial designer, not generated from a generic corporate template.

Prioritize typographic hierarchy, carefully balanced white space, readable text columns, controlled visual rhythm, and thoughtful photographic placement.

### Layout requirements

1. Use a predominantly two-column editorial layout for the article body.
2. Create a strong opening composition featuring a prominent headline, introductory standfirst, and an appropriately placed photograph.
3. Establish a clear hierarchy between the headline, introduction, body text, subheadings, captions, and any supporting editorial elements.
4. Integrate all four supplied photographs naturally throughout the article. Use their actual compositions and aspect ratios to determine appropriate sizing and placement.
5. Introduce occasional full-width elements or single-column interruptions where they improve the reading experience.
6. Use restrained editorial details such as thin rules, small section labels, folios, or running headers where appropriate.
7. Maintain comfortable margins, consistent gutters, and precise alignment.
8. Avoid unnecessary decorative elements, oversized numerical callouts, generic colored cards, gradients, and artificial dashboard-like components.
9. Allow natural text flow between columns and pages. Avoid manual page breaks unless technically necessary.
10. Keep the layout visually consistent without making every page identical.

### Photography

Use `1.jpg`, `2.jpg`, `3.jpg`, and `4.jpg` as editorial assets, not decoration.

- Preserve image proportions.
- Avoid distortion and unnecessary cropping.
- Place photographs near contextually relevant passages where possible.
- Use concise captions when appropriate.
- Avoid stacking all photographs together or forcing one image onto every page.
- Ensure text wraps and column boundaries behave correctly.

### Typography

Use a deliberate combination of editorial serif and sans-serif typography where suitable.

Body text must remain comfortable to read. Use consistent paragraph styles, sensible leading, controlled paragraph spacing, and properly differentiated heading levels.

Avoid excessive bold text, inconsistent font sizes, and oversized empty spaces.

### Content preservation

Preserve the original article's meaning, factual information, and narrative structure. You may adjust paragraph breaks, subheading placement, and minor editorial formatting to improve the layout, but do not invent facts or unnecessarily rewrite the article.

### Technical requirements

- Work directly in the existing `article.docx`.
- Prefer native Word formatting, paragraph styles, columns, sections, and image placement mechanisms.
- Keep the document fully editable in Microsoft Word.
- Avoid floating text boxes for primary article content.
- Ensure all four photographs are inserted successfully.
- Check pagination, column flow, image anchoring, captions, and page boundaries.
- Prevent clipped content, orphaned headings, overlapping elements, and unintended blank pages.
- Do not rebuild the document unnecessarily if its existing structure can be reused.

### Validation

After applying the layout, inspect the finished document using the available Word tools.

Correct material formatting problems, especially column overflow, disrupted text flow, incorrect image positioning, and unintended blank space.

Prioritize a stable, readable, well-balanced document over pixel-perfect adjustments.

**Completion criteria:** The document is saved, all four images are incorporated, the article uses a coherent editorial column layout, and no major layout defects remain.

Once these criteria are met, finish the task. Do not enter repetitive refinement cycles over minor aesthetic imperfections.

Provide a concise summary of the changes made and any remaining limitations."""


@pytest.mark.parametrize("text", [
    WORD_REQUEST,
    "**Task:** Transform the existing document into an editorial layout.\n2. Create an opening photograph composition.",
    "### Request: Edit `article.docx`.\n- Create a headline and photograph composition.",
    "Create a magazine article with photographs.",
    "Create a photograph of a forest. Then insert it into the existing Word document.",
    "Generate a photograph, and add it to article.docx.",
    "Create an image of a cat.\nEdit the selected Word document to incorporate it.",
    'Edit "article.docx". Create a photographic opening.',
    "Edit `Design brief.docx`. Create an opening photograph composition.",
    "Make the existing Excel workbook clearer. Create a photograph for its cover.",
    "Create a spreadsheet of sprite coordinates.",
    "Create an article about photographs.",
    "Transform this image into an editable Word document.",
    "Transform this image into a fully editable native Word document.",
])
@pytest.mark.parametrize("has_image", [False, True])
def test_document_deliverable_precedes_visual_substeps(text, has_image):
    intent = image_intent(text, has_image=has_image)
    assert (intent.route, intent.reason, intent.followup) == ("agent", "editable_document", False)


@pytest.mark.parametrize("text", [
    "Generate a photograph of a Word document.",
    "Create an article illustration.",
    "Create a Word document cover image.",
    "Design a workbook icon.",
    "Create a presentation cover photograph.",
    "Create an image for my article.",
    "Create a poster for article.docx.",
    "Do not edit article.docx. Generate a photograph of a forest.",
    "Do not open article.docx and edit the Word document. Draw a cat.",
    "Please don't open article.docx and add an image to the document. Draw a cat.",
    "Don't create a document. Draw a cat.",
    "Generate a photograph.\n> Edit article.docx and insert the photograph.",
    'The example says "Edit article.docx". Draw a cat.',
    "```text\nOpen and edit article.docx\n```\nDraw a cat.",
    "Draw a cat.\n    Edit article.docx and insert it.",
    "Draw a cat. The filename is `article.docx`.",
    "`Open article.docx`\nDraw a cat.",
    '"Edit article.docx"\nDraw a cat.',
    "/image Edit the existing Word document to look like a photograph",
])
def test_incidental_negated_and_quoted_document_text_cannot_veto_images(text):
    assert image_intent(text).route == "image_generation"


def test_semantic_presentation_cannot_override_established_document_deliverable():
    decision = image_route(WORD_REQUEST, intent=ImageIntent("image_generation", "visual_creation"))
    assert (decision.route, decision.reason, decision.source) == ("agent", "editable_document", "none")


def test_document_noun_modifying_visual_edit_still_edits_source_pixels():
    intent = image_intent("Edit an article illustration.", has_image=True)
    assert (intent.route, intent.reason, intent.followup) == ("image_generation", "visual_edit", True)


@pytest.mark.parametrize("prompt,visual", [(WORD_REQUEST, False),
    ("Generate a photograph for my Word article.", True), ("/image A forest photograph", True)])
def test_selected_word_document_service_and_ui_prediction_agree(native_sdk, tmp_path, prompt, visual, monkeypatch):
    """Real SDK HTTP and Office stdio fixtures; no native Office or paid calls."""
    payloads = []
    engine, _, bodies, _ = native_sdk(payloads=payloads)
    bridge = connection("slow_word")
    runtime = runtime_for(bridge, tmp_path / "runtime", engine)
    service = ConversationService(engine, ConversationStore(tmp_path / "chat.json"),
        agent_runtime=runtime, portable_root=bridge.root,
        skill_registry=SkillRegistry(global_root=tmp_path / "skills"))
    try:
        bridge.connect()
        # Synthetic stdio servers have no native private selection resource.
        # Seed the same trusted UI-selection state without touching Word.
        bridge._selected_application = "word"
        assert bridge.selected_application == "word"
        if visual:
            payloads.append(image_payload())
        else:
            definition = next(d for d in runtime.registry.model_definitions() if d.name == "office.documents")
            payloads.extend([response(output=[function(definition,
                {"application": "word", "cursor": None, "limit": 20})]), response("Office agent entered.")])
            # An established document intent must not be replaced by the
            # optional semantic presentation selector, including mixed language.
            monkeypatch.setattr("app.conversation.orchestrator.detect_language", lambda text: "nl")
            monkeypatch.setattr("app.conversation.turn_presentation.select_visual_intent",
                lambda *a, **kw: pytest.fail("Document task must not invoke a visual selector"))
        decision = service.image_route_decision(prompt)
        assert service.will_generate_images(prompt) is visual
        assert (decision.route == "image_generation") is visual
        answer = service.run(prompt)
        assert service.store.visible_messages()[0].content == prompt
        image_requests = [body for body in bodies if body.get("tool_choice") == {"type": "image_generation"}]
        assert len(image_requests) == (1 if visual else 0)
        assert bool(answer.generated_images) is visual
        if not visual:
            settled = service.store.turns()[-1].settled_calls
            assert len(settled) == 1 and settled[0].call.capability == "office.documents"
            assert settled[0].result.success
            assert settled[0].result.output["documents"][0]["application"] == "word"
    finally:
        service.shutdown()
    assert not bridge.diagnostics["worker_alive"]
