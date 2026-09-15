"""Public documentation URLs the softmax and coworld CLIs point at.

Both CLIs name these in help text, after milestones, and in error output, so an agent that only
ever sees terminal output still learns where the docs site is.
"""

DOCS_URL = "https://docs.softmax.com"
DOCS_AGENT_INDEX_URL = f"{DOCS_URL}/llms.txt"
DOCS_AGENT_SKILL_URL = f"{DOCS_URL}/skill.md"
DOCS_AUTHENTICATION_URL = f"{DOCS_URL}/guides/authentication"
DOCS_RATE_LIMITS_URL = f"{DOCS_URL}/guides/rate-limits"
DOCS_ERROR_HANDLING_URL = f"{DOCS_URL}/api-reference/error-handling"
DOCS_FORUMS_AND_WIKIS_URL = f"{DOCS_URL}/coworld/concepts/forums-and-wikis"
