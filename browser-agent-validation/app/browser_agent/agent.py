from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any

from app.browser_agent.browser import RequestsBrowserTool
from app.browser_agent.extractor import TrafilaturaExtractor
from app.browser_agent.interfaces import BrowserAgentBase, BrowserTool, Extractor, SearchTool, Summarizer
from app.browser_agent.planner import QueryPlanner
from app.browser_agent.search import DuckDuckGoSearchTool
from app.browser_agent.summarizer import OllamaSummarizer
from app.execution.engine import ExecutionEngine
from app.execution.interfaces import ExecutionContext, ExecutionEngineBase
from app.execution.tracer import save_trace
from app.models.base import BrowserResult, ExecutionTrace

logger = logging.getLogger(__name__)


class BrowserAgent(BrowserAgentBase):
    def __init__(
        self,
        search_tool: SearchTool,
        browser_tool: BrowserTool,
        extractor: Extractor,
        summarizer: Summarizer,
        engine: ExecutionEngineBase | None = None,
        planner: QueryPlanner | None = None,
        max_results: int = 5,
        max_total_context: int = 10_000,
        trace_path: str | Path = "trace.json",
    ) -> None:
        self._search = search_tool
        self._browser = browser_tool
        self._extractor = extractor
        self._summarizer = summarizer
        self._engine = engine or ExecutionEngine()
        self._planner = planner or QueryPlanner()
        self._max_results = max_results
        self._max_total_context = max_total_context
        self._trace_path = Path(trace_path)
        self._last_trace: ExecutionTrace | None = None

    @property
    def last_trace(self) -> ExecutionTrace | None:
        return self._last_trace

    def run(self, query: str) -> BrowserResult:
        ctx = ExecutionContext(execution_id=str(uuid.uuid4()), query=query)
        logger.info("BrowserAgent run — execution_id=%s query=%r", ctx.execution_id, query)

        plan: dict[str, Any] = {}
        search_results: list[dict] = []
        pages: dict[str, str] = {}
        context = ""
        successful_urls: list[str] = []
        successful_sources: list[str] = []
        summary = ""

        try:
            # ── Step 1: Planning ──────────────────────────────────────────────
            with self._engine.step(ctx, "planning") as step:
                step.set_inputs(query=query)
                plan = self._planner.plan(query)
                step.set_outputs(
                    search_query=plan["search_query"],
                    strategy=plan["strategy"],
                )

            # ── Step 2: Search ────────────────────────────────────────────────
            with self._engine.step(ctx, "search") as step:
                step.set_inputs(
                    search_query=plan["search_query"],
                    max_results=self._max_results,
                )
                search_results = self._search.search(
                    plan["search_query"], max_results=self._max_results
                )
                step.set_outputs(results_count=len(search_results))

            if not search_results:
                logger.warning("No search results — returning early")
                result = BrowserResult(
                    summary="No search results found for the query.",
                    sources=[],
                    urls=[],
                    latency_ms=0.0,
                )
                return result

            # ── Step 3: Browser ───────────────────────────────────────────────
            with self._engine.step(ctx, "browser") as step:
                urls = [r["url"] for r in search_results if r.get("url")]
                step.set_inputs(urls_count=len(urls))
                pages = {url: self._browser.fetch(url) for url in urls}
                fetched = sum(1 for h in pages.values() if h)
                step.set_outputs(fetched=fetched, skipped=len(urls) - fetched)

            # ── Step 4: Extraction ────────────────────────────────────────────
            with self._engine.step(ctx, "extraction") as step:
                context_parts: list[str] = []
                total_chars = 0

                for result in search_results:
                    url = result.get("url", "")
                    html = pages.get(url, "")
                    if not html:
                        continue
                    text = self._extractor.extract(html, url=url)
                    if not text:
                        continue
                    context_parts.append(f"[Source: {result.get('title', url)}]\n{text}")
                    successful_urls.append(url)
                    successful_sources.append(result.get("title", url))
                    total_chars += len(text)
                    if total_chars >= self._max_total_context:
                        break

                context = "\n\n---\n\n".join(context_parts)
                step.set_inputs(pages_count=len(pages))
                step.set_outputs(
                    sources_extracted=len(successful_urls),
                    context_chars=len(context),
                )

            # ── Step 5: Reasoning ─────────────────────────────────────────────
            with self._engine.step(ctx, "reasoning") as step:
                step.set_inputs(
                    query=query,
                    context_chars=len(context),
                    sources_count=len(successful_sources),
                )
                summary = self._summarizer.summarize(
                    query=query,
                    context=context,
                    sources=successful_sources,
                )
                step.set_outputs(summary_chars=len(summary))

            # ── Step 6: Response ──────────────────────────────────────────────
            with self._engine.step(ctx, "response") as step:
                step.set_inputs(
                    sources_count=len(successful_urls),
                    summary_chars=len(summary),
                )
                step.set_outputs(status="ok")

        except Exception as exc:
            logger.error("BrowserAgent run failed: %s", exc)
            raise

        finally:
            trace = self._engine.finalize(ctx)
            self._last_trace = trace
            save_trace(trace, self._trace_path)
            logger.info(
                "Trace saved → %s  (total %.0f ms)",
                self._trace_path,
                trace.total_duration_ms or 0,
            )

        return BrowserResult(
            summary=summary,
            sources=successful_sources,
            urls=successful_urls,
            latency_ms=self._last_trace.total_duration_ms or 0.0,
            token_usage={},
            metadata={
                "execution_id": ctx.execution_id,
                "search_results_found": len(search_results),
                "urls_fetched": len(successful_urls),
                "context_chars": len(context),
            },
        )


def create_browser_agent(
    model: str = "llama3.1",
    max_results: int = 5,
    max_total_context: int = 10_000,
    trace_path: str | Path = "trace.json",
    engine: ExecutionEngineBase | None = None,
) -> BrowserAgent:
    return BrowserAgent(
        search_tool=DuckDuckGoSearchTool(),
        browser_tool=RequestsBrowserTool(),
        extractor=TrafilaturaExtractor(),
        summarizer=OllamaSummarizer(model=model),
        engine=engine,
        max_results=max_results,
        max_total_context=max_total_context,
        trace_path=trace_path,
    )
