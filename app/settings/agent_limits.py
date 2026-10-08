"""Shared ceilings for execution and durable per-turn records."""

MAX_LOCAL_AGENT_STEPS = 32
MAX_AGENT_STEPS = 128
MAX_AGENT_MODEL_REQUESTS = 128
MAX_AGENT_CAPABILITY_CALLS = 256
# A preplanned tool step retains metadata without spending a model request.
MAX_AGENT_COMPLETIONS = MAX_AGENT_MODEL_REQUESTS + 1

