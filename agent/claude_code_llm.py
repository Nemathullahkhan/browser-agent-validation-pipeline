import subprocess
from langchain_core.language_models.llms import LLM


class ClaudeCodeLLM(LLM):
    """LangChain LLM that shells out to the local `claude` CLI.

    Prerequisites:
      - Claude Code CLI installed  (`pip install claude-code` or via npm)
      - Logged in via OAuth       (`claude auth login`)
      - Session active            (`claude auth status` → loggedIn: true)

    No OPENAI_API_KEY or ANTHROPIC_API_KEY is read or required.
    """

    model: str = "sonnet"

    @property
    def _llm_type(self) -> str:
        return "claude-code-cli"

    def _call(self, prompt: str, stop=None, **kwargs) -> str:
        result = subprocess.run(
            [
                "claude", "-p", prompt,
                "--model", self.model,
                "--output-format", "text",
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            raise RuntimeError(f"claude CLI error: {result.stderr.strip()}")
        return result.stdout.strip()
