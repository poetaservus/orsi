"""Explicit local document support shared by both llama.cpp adapters."""
from app.inference.attachments import AttachmentError, has_attachments


class LocalDocumentInputs:
    supports_attachment_inputs = True
    supports_local_document_inputs = True

    def respond_with_attachments(self, messages, *, attachment_store):
        from app.conversation.local_documents import LocalDocuments
        return self.respond(LocalDocuments(attachment_store).project(messages))

    def count_attachment_message_tokens(self, messages, *, attachment_store=None):
        if attachment_store is None:
            raise AttachmentError("Local document accounting requires the verified attachment store.")
        from app.conversation.local_documents import LocalDocuments, LocalDocumentCounter
        return LocalDocumentCounter(self, LocalDocuments(attachment_store)).count_attachment_message_tokens(messages)

    @staticmethod
    def require_text_messages(messages):
        if has_attachments(messages):
            raise AttachmentError("Resolve local documents with the verified attachment store before inference.")
