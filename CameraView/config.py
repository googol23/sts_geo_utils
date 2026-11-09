"""Scene configuration loading from JSON or YAML."""

import json
from pathlib import Path


class SceneConfig:
    """Thin dictionary-backed scene configuration.

    Expected top-level keys: ``layout`` (matrix rows), ``cameras`` keyed by
    pad id, ``dimensions`` keyed by pad id, and optional ``render`` settings.
    """

    def __init__(self, data):
        if not isinstance(data, dict):
            raise ValueError("scene configuration must be a mapping")
        self.data = data
        self.layout = data.get("layout", {}).get("matrix")
        if not self.layout:
            raise ValueError("scene configuration requires layout.matrix")
        self.cameras = data.get("cameras", {})
        self.dimensions = data.get("dimensions", {})
        self.render = data.get("render", {})
        self.aliases = data.get("layout", {}).get("aliases", {})

    @classmethod
    def load(cls, filename):
        path = Path(filename)
        suffix = path.suffix.lower()
        text = path.read_text(encoding="utf-8")
        if suffix == ".json":
            data = json.loads(text)
        elif suffix in (".yaml", ".yml"):
            try:
                import yaml
            except ImportError as exc:
                raise RuntimeError("YAML loading requires PyYAML") from exc
            data = yaml.safe_load(text)
        else:
            raise ValueError("configuration file must end in .json, .yaml, or .yml")
        return cls(data)

    def for_pad(self, section, pad_id):
        """Fetch a pad-specific config, preferring its exact id then default."""
        values = getattr(self, section)
        alias = next(
            (name for name, target in self.aliases.items() if str(target) == str(pad_id)),
            None,
        )
        return values.get(str(pad_id), values.get(alias, values.get("default", {})))
