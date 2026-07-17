import re
import time
import requests
from bs4 import BeautifulSoup

# Replace with the two real product-page domains you want to compare
APPROVED_DOMAINS = ["site-a.example.com", "site-b.example.com"]


def fetch_html(url: str) -> dict:
    """Fetch raw HTML for an approved domain. Returns status, size, timing, html."""
    domain = url.split("/")[2]
    if domain not in APPROVED_DOMAINS:
        raise ValueError(f"Domain not approved: {domain}")

    start = time.time()
    resp = requests.get(url, timeout=10)
    elapsed = time.time() - start

    return {
        "url": url,
        "status": resp.status_code,
        "html": resp.text,
        "size": len(resp.text),
        "elapsed_sec": round(elapsed, 3),
    }


def extract_price(html: str) -> dict:
    """Parse a price out of HTML. Returns value + match count for validation."""
    soup = BeautifulSoup(html, "html.parser")
    matches = re.findall(r"\$\s?(\d+\.\d{2})", soup.get_text())
    return {
        "matches_found": len(matches),
        "price": float(matches[0]) if len(matches) == 1 else None,
        "raw_matches": matches,
    }


def compare_prices(price_a: float, price_b: float) -> dict:
    if price_a is None or price_b is None:
        return {"error": "Missing price — cannot compare"}
    cheaper = "A" if price_a < price_b else "B"
    return {
        "cheaper_site": cheaper,
        "price_a": price_a,
        "price_b": price_b,
        "difference": round(abs(price_a - price_b), 2),
    }
