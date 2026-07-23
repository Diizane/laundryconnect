"""Search-hit snippets: a short window of page text around the first match."""

SNIPPET_CONTEXT_CHARS = 80


def build_snippet(text: str, query: str, context: int = SNIPPET_CONTEXT_CHARS) -> str:
    """Return the text around the first case-insensitive match of `query`.

    Falls back to the start of the text if there is no match (defensive —
    callers only pass pages that already matched).
    """
    collapsed = " ".join(text.split())
    index = collapsed.lower().find(query.strip().lower())
    if index == -1:
        return collapsed[: context * 2].strip()

    start = max(0, index - context)
    end = min(len(collapsed), index + len(query) + context)
    snippet = collapsed[start:end].strip()
    if start > 0:
        snippet = f"…{snippet}"
    if end < len(collapsed):
        snippet = f"{snippet}…"
    return snippet
