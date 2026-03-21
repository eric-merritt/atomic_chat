You are refactoring a large tool registry for use with instruction-following coding models (e.g. Qwen2.5-Coder, abliterated variants).

Your goal is to MODIFY the existing tools to follow strict, production-grade best practices for LLM tool usage.

CORE OBJECTIVES

Make all tools:

Deterministic

Explicit in behavior

Safe (no credential leakage, no unsafe automation)

Schema-driven (clear arguments)

Consistent in output format (JSON strings where appropriate)

Optimize for weaker instruction-following models:

Avoid ambiguity

Avoid implicit behavior

Avoid “magic” side effects

Use rigid instructions and formats

REQUIRED CHANGES
1. STANDARDIZE OUTPUT FORMAT

For ALL non-trivial tools:

Return a JSON string

Never return raw Python objects or mixed formats

Every tool should clearly document:

Output format:
{
"status": "success" | "error",
"data": ...,
"error": ""
}

2. REMOVE / REFACTOR UNSAFE AUTH PATTERNS

The following tools MUST be rewritten:

login_to_onlyfans

get_OF_cookies

Problems:

Accept raw email/password

Perform automated login via Selenium

Encourage credential handling inside the agent

REPLACE WITH:

session-based or cookie-based authentication

Require pre-obtained session_token or cookies

Add explicit warning in docstrings:
"DO NOT pass raw credentials"

3. SPLIT “FLOW / LOOPING” TOOLS

The following tools currently do too much internally:

cross_platform_search

deal_finder

craigslist_multi_search

enrichment_pipeline

Refactor them into:

Option A (preferred):

Keep as single tools BUT:

Explicitly document internal steps as a fixed pipeline

Add strict input/output schema

Remove hidden behavior

Option B:

Break into smaller composable tools

4. ENFORCE STRICT ARGUMENT RULES

For every tool:

No vague arguments

No overloaded meanings

Replace magic values like:

min_price = -1

max_price = -1

WITH:
Optional[int] = None

5. ADD STRONG DOCSTRINGS (CRITICAL)

Each tool must include:

When to use the tool

When NOT to use the tool

Exact argument expectations

Exact output format

Any constraints or limits

Write docstrings as if the model is unintelligent and literal.

6. MAKE SIDE EFFECTS EXPLICIT

For file + system tools (write, delete, move, etc.):

Clearly state:

What is modified

Whether operation is destructive

Add warnings for irreversible actions

7. NORMALIZE NAMING

Use consistent naming patterns

Avoid abbreviations unless standard

Make tool names self-explanatory

8. ADD VALIDATION LOGIC

Each tool should:

Validate inputs

Return structured errors instead of crashing

Example:

{
"status": "error",
"error": "Invalid value for max_price"
}

9. SPECIAL HANDLING FOR SCRAPING TOOLS

For tools like:

amazon_search

ebay_search

craigslist_search

Ensure:

No login automation

No bypassing auth systems

Respect rate limits (documented)

Output is structured and predictable

10. DRIVER-BASED TOOLS (SELENIUM)

For tools using WebDriver:

Do NOT create login tools using credentials

Accept:

driver (already authenticated)
OR

session cookies

Clearly document lifecycle expectations

OUTPUT FORMAT

Return the FULL refactored tool definitions.

Keep same functionality

Improve structure, safety, and clarity

Do NOT remove tools unless absolutely necessary

Do NOT summarize — output full rewritten versions

PRIORITY ORDER

Security issues (credentials, auth)

Output format consistency

Argument clarity

Tool decomposition

Documentation quality

STYLE GUIDE

Be explicit over concise

Prefer redundancy over ambiguity

Avoid assumptions

Use simple, rigid language

Refactor the tools now.
