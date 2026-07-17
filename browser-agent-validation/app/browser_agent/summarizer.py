from __future__ import annotations

import logging

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama

from app.browser_agent.interfaces import Summarizer

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a research assistant. You receive web content collected for a user query.
Your task is to produce a clear, accurate, well-structured summary that directly answers the query.

Rules:
- Stay strictly within the provided content. Do not add external knowledge.
- Be concise but complete.
- If the content is insufficient to answer, say so explicitly.
- Do not fabricate facts, URLs, or citations.
"""

_USER_TEMPLATE = """\
Query: {query}

Sources:
{sources}

Web content:
{context}

Provide a comprehensive summary that answers the query based solely on the content above.
"""


class OllamaSummarizer(Summarizer):
    def __init__(self, model: str = "llama3.1", temperature: float = 0.0) -> None:
        self._model = model
        self._llm = ChatOllama(model=model, temperature=temperature)

    @property
    def model(self) -> str:
        return self._model

    def summarize(self, query: str, context: str, sources: list[str]) -> str:
        sources_text = "\n".join(f"- {s}" for s in sources) if sources else "None"
        user_msg = _USER_TEMPLATE.format(
            query=query,
            sources=sources_text,
            context=context or "(no content extracted)",
        )

        messages = [
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=user_msg),
        ]

        logger.info("Sending request to Ollama model=%s", self._model)
        response = self._llm.invoke(messages)
        text = response.content if hasattr(response, "content") else str(response)
        logger.info("Ollama response: %d chars", len(text))
        return text.strip()
