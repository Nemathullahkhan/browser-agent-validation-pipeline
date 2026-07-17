import re
from langchain.agents.output_parsers import ReActSingleInputOutputParser


class CleanReActOutputParser(ReActSingleInputOutputParser):
    """Strips backticks/keyword prefixes that llama3.1 adds to Action lines."""

    def parse(self, text: str):
        # Action: `fetch_html`  ->  Action: fetch_html
        text = re.sub(r"^Action:\s*`([^`]+)`\s*$", r"Action: \1", text, flags=re.MULTILINE)
        # Action Input: `url="http://..."` -> Action Input: http://...
        text = re.sub(
            r'^Action Input:\s*`?(?:url=)?["\']?(https?://[^\s"\'`\)]+)["\']?`?\s*$',
            r"Action Input: \1", text, flags=re.MULTILINE,
        )
        # Action Input: `{...}`  ->  Action Input: {...}
        text = re.sub(r"^Action Input:\s*`(.+)`\s*$", r"Action Input: \1", text, flags=re.MULTILINE)
        return super().parse(text)
