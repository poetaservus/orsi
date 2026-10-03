"""Fixed Phase 3.2 evaluation stimuli; do not tune these to a failing router."""
from dataclasses import dataclass

from app.runtime.skills import SkillCandidate


CANDIDATES = (
    SkillCandidate("design-taste-frontend", "Frontend design guidance for polished interfaces, React components, dashboards and landing pages."),
    SkillCandidate("python-debugging", "Python debugging guidance for tracebacks, exceptions, failing tests, logic errors and memory leaks in Python code."),
    SkillCandidate("sql-analysis", "SQL analysis and query-generation guidance for relational joins, aggregations, schema queries and database query plans."),
)
FRONTEND_BODY = "For frontend design tasks, begin with FRONTEND-GUIDANCE: and give one concise UI design suggestion."


@dataclass(frozen=True, slots=True)
class RoutingCase:
    case_id: str
    category: str
    request: str
    expected: str | None
    obvious: bool = True


_GROUPS = {
    "frontend": (
        "Redesign this React landing page.",
        "Build a polished SaaS landing page with a pricing section.",
        "Improve the typography and spacing of my web dashboard.",
        "Design a responsive navigation bar for a React site.",
        "Create a minimal portfolio homepage layout.",
        "Give this signup interface better visual hierarchy.",
        "Design a clear mobile layout for a product page.",
        "Improve the colors and contrast of this frontend interface.",
    ),
    "sql": (
        "Write a SQL join between orders and customers.",
        "Analyze why this SQL query's execution plan is slow.",
        "Generate a SQL query for monthly revenue by customer.",
        "Explain why this GROUP BY SQL query returns duplicate rows.",
        "Fix the syntax error in this PostgreSQL SELECT query.",
        "Write a SQL window function for a running total.",
        "Compare these two relational query plans.",
        "Find the top three products per category using SQL.",
    ),
    "python": (
        "Debug this Python traceback ending in KeyError.",
        "Find why my Python pytest test fails with an assertion error.",
        "Fix a Python TypeError caused by adding a string to an integer.",
        "Investigate a memory leak in this Python script.",
        "Find the off-by-one bug in this Python loop.",
        "Explain this Python ImportError and how to fix it.",
        "Debug the exception raised by my Python async function.",
        "Find why this Python function returns the wrong result.",
    ),
    "ordinary": (
        "Hello, how are you?",
        "What's 17 * 31?",
        "What is the capital of France?",
        "Explain why rainbows form.",
        "Translate good morning into French.",
        "Thank you for your help.",
    ),
    "ambiguous": (
        "Help me improve this project.",
        "Fix the database-backed dashboard.",
        "Debug the website and its Python backend together.",
        "I need some coding advice but haven't chosen a language.",
    ),
    "unrelated_coding": (
        "Optimize this Rust iterator implementation.",
        "Write a Bash script to back up a folder.",
        "Debug this Java NullPointerException.",
        "Explain a C# LINQ expression.",
        "Implement binary search in C++.",
        "Find a deadlock in these Go channels.",
    ),
}
_EXPECTED = {"frontend": "design-taste-frontend", "sql": "sql-analysis", "python": "python-debugging"}
ROUTING_CASES = tuple(
    RoutingCase(f"{category}-{index}", category, request, _EXPECTED.get(category), category != "ambiguous")
    for category, requests in _GROUPS.items() for index, request in enumerate(requests, 1)
) + (
    RoutingCase("name-mention-1", "name_mentions", "What does the name design-taste-frontend mean?", None),
    RoutingCase("name-mention-2", "name_mentions", "Compare the python-debugging and sql-analysis skills.", None),
    RoutingCase("name-mention-3", "name_mentions", "Use python-debugging to investigate this Python traceback.", "python-debugging"),
    RoutingCase("name-mention-4", "name_mentions", "Use sql-analysis to write a relational join query.", "sql-analysis"),
)
