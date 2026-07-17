from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from app.policies.models import PolicyConfig

_DEFAULT_POLICY_PATH = Path(__file__).parent / "default.yaml"


class PolicyLoader(ABC):
    @abstractmethod
    def load(self) -> PolicyConfig: ...


class YamlPolicyLoader(PolicyLoader):
    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> PolicyConfig:
        try:
            import yaml
        except ImportError:
            raise RuntimeError("PyYAML is required: pip install pyyaml")
        if not self._path.exists():
            raise FileNotFoundError(f"Policy file not found: {self._path}")
        with self._path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return PolicyConfig.model_validate(data or {})


def load_default_policy() -> PolicyConfig:
    """Load policy from default.yaml; fall back to built-in defaults if absent."""
    if _DEFAULT_POLICY_PATH.exists():
        return YamlPolicyLoader(_DEFAULT_POLICY_PATH).load()
    return PolicyConfig()


def load_policy(path: str | Path | None = None) -> PolicyConfig:
    """Load policy from *path* or fall back to default."""
    if path is not None:
        return YamlPolicyLoader(path).load()
    return load_default_policy()
