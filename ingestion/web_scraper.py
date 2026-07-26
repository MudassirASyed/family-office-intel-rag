"""
Generic web scraper for a firm's own site, used at the VERIFICATION
step - not discovery. Once you have a candidate name and a
hypothesized URL, use this to check what the firm says about itself.

Many true single-family offices have NO website at all - that's
expected and should be recorded as "no web presence found", not
treated as a failure of your code.
"""
import requests
from bs4 import BeautifulSoup

USER_AGENT = "Mozilla/5.0 (research project; contact your_email@example.com)"


def fetch_page_text(url: str, max_chars: int = 3000) -> str | None:
    """Returns cleaned visible text, or None if unreachable (common
    and expected for SFOs with no web presence)."""
    headers = {"User-Agent": USER_AGENT}
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
    except requests.RequestException:
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer"]):
        tag.decompose()
    return " ".join(soup.stripped_strings)[:max_chars]


def mentions_any(text: str, keywords: list[str]) -> list[str]:
    """Which of the given keywords actually appear in the text."""
    text_lower = text.lower()
    return [kw for kw in keywords if kw.lower() in text_lower]


if __name__ == "__main__":
    text = fetch_page_text("https://www.sec.gov/about")
    if text:
        print(text[:400])
    else:
        print("Page unreachable - this is a normal, expected outcome for many SFOs.")
