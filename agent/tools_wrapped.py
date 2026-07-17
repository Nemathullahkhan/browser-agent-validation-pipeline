import json

from langchain.tools import StructuredTool
from pydantic import BaseModel
from agent.tools import fetch_html, extract_price, compare_prices


class FetchInput(BaseModel):
    url: str


class ExtractInput(BaseModel):
    html: str


class CompareInput(BaseModel):
    input: str


def _compare_prices_from_text(input: str) -> dict:
    """Adapter for the ReAct agent's single-string action input.
    Accepts a JSON object string or a 'price_a, price_b' pair."""
    try:
        data = json.loads(input)
        price_a, price_b = data["price_a"], data["price_b"]
    except (json.JSONDecodeError, KeyError, TypeError):
        parts = [p.strip().strip("$") for p in input.replace(",", " ").split()]
        price_a, price_b = parts[0], parts[1]
    return compare_prices(float(price_a), float(price_b))


fetch_tool = StructuredTool.from_function(
    func=fetch_html,
    name="fetch_html",
    description="Fetch HTML from an approved product page URL.",
    args_schema=FetchInput,
)

extract_tool = StructuredTool.from_function(
    func=extract_price,
    name="extract_price",
    description="Extract a numeric price from fetched HTML.",
    args_schema=ExtractInput,
)

compare_tool = StructuredTool.from_function(
    func=_compare_prices_from_text,
    name="compare_prices",
    description=(
        "Compare two prices and return the cheaper option. "
        'Input must be a single JSON object string, e.g. {"price_a": 49.99, "price_b": 44.49}'
    ),
    args_schema=CompareInput,
)
