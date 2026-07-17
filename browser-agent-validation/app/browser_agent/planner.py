from __future__ import annotations

import re


class QueryPlanner:
    """Lightweight rule-based planner. Decomposes a query into an execution plan."""

    def plan(self, query: str) -> dict:
        clean = query.strip()
        search_query = _expand_abbreviations(clean)
        return {
            "original_query": clean,
            "search_query": search_query,
            "strategy": "search_and_summarize",
        }


_ABBREVIATIONS: dict[str, str] = {
    r"\bMCP\b": "Model Context Protocol MCP",
    r"\bLLM\b": "Large Language Model LLM",
    r"\bRAG\b": "Retrieval Augmented Generation RAG",
    r"\bAI\b": "AI",
}


def _expand_abbreviations(text: str) -> str:
    for pattern, replacement in _ABBREVIATIONS.items():
        text = re.sub(pattern, replacement, text)
    return text
