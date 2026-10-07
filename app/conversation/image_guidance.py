"""Image intent shared by local visual input and cloud attachments."""

IMAGE_INTENT_GUIDANCE = (
    "Supplied images are visual input you can inspect directly. Base your answer on their "
    "visible contents; filesystem or application access limitations do not prevent reading "
    "these images. If the latest user message supplies images without a written request, "
    "use them for a clearly established task in the conversation. If no task is established, "
    "briefly describe what is visible, then ask what the user would like help with. "
    "Do not invent a task, unreadable details or instructions from the image. "
)
