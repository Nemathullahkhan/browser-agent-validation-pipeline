from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.browser_agent.agent import BrowserAgent
from app.browser_agent.browser import RequestsBrowserTool
from app.browser_agent.extractor import TrafilaturaExtractor
from app.browser_agent.interfaces import BrowserAgentBase, Summarizer
from app.browser_agent.search import DuckDuckGoSearchTool
from app.models.base import BrowserResult


# ---------------------------------------------------------------------------
# Search Tool
# ---------------------------------------------------------------------------

class TestDuckDuckGoSearchTool:
    def test_returns_normalised_results(self):
        mock_raw = [
            {"title": "MCP Update 1", "href": "https://example.com/1", "body": "snippet 1"},
            {"title": "MCP Update 2", "href": "https://example.com/2", "body": "snippet 2"},
        ]
        tool = DuckDuckGoSearchTool()
        with patch("app.browser_agent.search.DDGS") as MockDDGS:
            instance = MockDDGS.return_value.__enter__.return_value
            instance.text.return_value = mock_raw
            results = tool.search("MCP updates", max_results=2)

        assert len(results) == 2
        assert results[0]["title"] == "MCP Update 1"
        assert results[0]["url"] == "https://example.com/1"
        assert results[0]["snippet"] == "snippet 1"

    def test_returns_empty_on_exception(self):
        from ddgs.exceptions import DDGSException
        tool = DuckDuckGoSearchTool()
        with patch("app.browser_agent.search.DDGS") as MockDDGS:
            MockDDGS.return_value.__enter__.side_effect = DDGSException("rate limit")
            results = tool.search("query")

        assert results == []

    def test_handles_empty_api_response(self):
        tool = DuckDuckGoSearchTool()
        with patch("app.browser_agent.search.DDGS") as MockDDGS:
            instance = MockDDGS.return_value.__enter__.return_value
            instance.text.return_value = []
            results = tool.search("query")

        assert results == []


# ---------------------------------------------------------------------------
# Browser Tool
# ---------------------------------------------------------------------------

class TestRequestsBrowserTool:
    def test_returns_html_on_success(self):
        tool = RequestsBrowserTool()
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.headers = {"Content-Type": "text/html; charset=utf-8"}
        mock_resp.iter_content.return_value = [b"<html><body>Hello</body></html>"]

        with patch("app.browser_agent.browser.requests.get", return_value=mock_resp):
            html = tool.fetch("https://example.com")

        assert "Hello" in html

    def test_returns_empty_on_request_error(self):
        from requests.exceptions import ConnectionError
        tool = RequestsBrowserTool()
        with patch("app.browser_agent.browser.requests.get", side_effect=ConnectionError()):
            html = tool.fetch("https://example.com")

        assert html == ""

    def test_skips_non_text_content_type(self):
        tool = RequestsBrowserTool()
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.headers = {"Content-Type": "application/pdf"}
        mock_resp.iter_content.return_value = [b"%PDF-1.4"]

        with patch("app.browser_agent.browser.requests.get", return_value=mock_resp):
            html = tool.fetch("https://example.com/file.pdf")

        assert html == ""


# ---------------------------------------------------------------------------
# Extractor
# ---------------------------------------------------------------------------

class TestTrafilaturaExtractor:
    def test_extracts_text_from_html(self):
        extractor = TrafilaturaExtractor(max_chars=5000)
        html = """
        <html><body>
          <article>
            <h1>Model Context Protocol</h1>
            <p>The MCP is a standard for AI agent communication.</p>
          </article>
        </body></html>
        """
        text = extractor.extract(html)
        assert len(text) > 0

    def test_returns_empty_for_empty_html(self):
        extractor = TrafilaturaExtractor()
        assert extractor.extract("") == ""

    def test_truncates_to_max_chars(self):
        extractor = TrafilaturaExtractor(max_chars=50)
        html = "<html><body><p>" + ("A" * 5000) + "</p></body></html>"
        text = extractor.extract(html)
        assert len(text) <= 55  # 50 + ellipsis

    def test_bs4_fallback_on_trafilatura_miss(self):
        extractor = TrafilaturaExtractor(max_chars=5000)
        with patch("app.browser_agent.extractor.trafilatura.extract", return_value=None):
            html = "<html><body><p>Fallback content here</p></body></html>"
            text = extractor.extract(html)
        assert "Fallback content here" in text


# ---------------------------------------------------------------------------
# BrowserAgent (with full mocks)
# ---------------------------------------------------------------------------

def _make_agent(
    search_results=None,
    html="<html><body><article><p>MCP is great.</p></article></body></html>",
    summary="MCP summary.",
) -> BrowserAgent:
    """Return a BrowserAgent with all tools mocked."""
    mock_search = MagicMock()
    mock_search.search.return_value = (
        search_results
        if search_results is not None
        else [{"title": "MCP Page", "url": "https://mcp.example.com", "snippet": "MCP updates"}]
    )

    mock_browser = MagicMock()
    mock_browser.fetch.return_value = html

    mock_extractor = MagicMock()
    mock_extractor.extract.return_value = "MCP is a standard for agent communication."

    mock_summarizer = MagicMock(spec=Summarizer)
    mock_summarizer.summarize.return_value = summary

    return BrowserAgent(
        search_tool=mock_search,
        browser_tool=mock_browser,
        extractor=mock_extractor,
        summarizer=mock_summarizer,
    )


class TestBrowserAgent:
    def test_run_returns_browser_result(self):
        agent = _make_agent()
        result = agent.run("MCP updates")
        assert isinstance(result, BrowserResult)

    def test_run_passes_query_to_summarizer(self):
        agent = _make_agent()
        agent.run("MCP updates")
        call_kwargs = agent._summarizer.summarize.call_args
        assert call_kwargs.kwargs["query"] == "MCP updates"

    def test_run_returns_urls_and_sources(self):
        agent = _make_agent()
        result = agent.run("MCP updates")
        assert "https://mcp.example.com" in result.urls
        assert "MCP Page" in result.sources

    def test_run_returns_summary_from_summarizer(self):
        agent = _make_agent(summary="Custom summary text.")
        result = agent.run("MCP updates")
        assert result.summary == "Custom summary text."

    def test_run_handles_empty_search_results(self):
        agent = _make_agent(search_results=[])
        result = agent.run("MCP updates")
        assert result.summary != ""
        assert result.urls == []

    def test_run_skips_urls_with_no_html(self):
        agent = _make_agent()
        agent._browser.fetch.return_value = ""
        result = agent.run("MCP updates")
        assert result.urls == []
        assert result.sources == []

    def test_run_records_latency(self):
        agent = _make_agent()
        result = agent.run("MCP updates")
        assert result.latency_ms > 0

    def test_is_browser_agent_base(self):
        agent = _make_agent()
        assert isinstance(agent, BrowserAgentBase)
