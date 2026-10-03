"""Phase 5.1 stimuli fixed before evaluating unchanged upstream TasteSkill."""

FRONTEND_TASKS = (
    ("saas", "Build a SaaS landing page."),
    ("dashboard", "Redesign an existing dashboard."),
    ("portfolio", "Create a minimal portfolio."),
    ("industrial", "Create an intentionally dense industrial interface."),
    ("improve", "Improve this generic AI-generated page."),
)

UNRELATED_TASKS = (
    ("python", "Why is this Python function throwing TypeError?"),
    ("greeting", "Hello."),
    ("arithmetic", "What is 17 times 23?"),
    ("sql", "Explain a SQL inner join."),
    ("git", "How do I undo the last Git commit without losing my changes?"),
)

TOOL_TASK = "Use filesystem.stat to inspect index.html and report whether it exists."

# Full-bundle routing may choose a task-specific style or the generic frontend
# variant. These accepted sets are fixed before submitting the live requests.
ACCEPTABLE_FRONTEND_SKILLS = {
    "saas": frozenset({"design-taste-frontend", "design-taste-frontend-v1", "gpt-taste"}),
    "dashboard": frozenset({"redesign-existing-projects"}),
    "portfolio": frozenset({"minimalist-ui", "design-taste-frontend", "design-taste-frontend-v1", "gpt-taste"}),
    "industrial": frozenset({"industrial-brutalist-ui"}),
    "improve": frozenset({"redesign-existing-projects", "design-taste-frontend", "design-taste-frontend-v1"}),
}
