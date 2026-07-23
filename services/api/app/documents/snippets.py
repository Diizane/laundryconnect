"""Search-hit snippets: a short window of page text around the first match.

Matching is case-insensitive literal substring — deliberately the same
semantics as the repository's escaped ILIKE search, so a page the database
matched always yields a real snippet. With multiple matches on a page the
window around the FIRST match is returned (predictable, documented).
"""

SNIPPET_CONTEXT_CHARS = 80


def build_snippet(text: str, query: str, context: int = SNIPPET_CONTEXT_CHARS) -> str | None:
    """Return the text around the first case-insensitive match of `query`,
    or None when the query does not occur — callers must handle None rather
    than showing unrelated fallback context as if it matched."""
    collapsed = " ".join(text.split())
    needle = " ".join(query.split()).lower()
    if not needle:
        return None
    index = collapsed.lower().find(needle)
    if index == -1:
        return None

    start = max(0, index - context)
    end = min(len(collapsed), index + len(needle) + context)
    snippet = collapsed[start:end].strip()
    if start > 0:
        snippet = f"…{snippet}"
    if end < len(collapsed):
        snippet = f"{snippet}…"
    return snippet
