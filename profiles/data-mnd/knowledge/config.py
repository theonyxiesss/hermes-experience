"""
Knowledge Retrieval MVP - Configuration
"""

import os
import yaml
from pathlib import Path
from typing import Any, Dict, List, Optional


class KnowledgeConfig:
    """Configuration for the knowledge retrieval system."""

    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize the configuration.

        Args:
            config_path: Path to the Hermes config.yaml file.
                         If None, attempts to locate it automatically.
        """
        if config_path is None:
            # Assume this file is in <hermes_profile>/knowledge/
            # So config.yaml is one level up
            config_path = Path(__file__).parent.parent / "config.yaml"

        self.config_path = config_path
        self._config: Dict[str, Any] = {}
        self._load_config()

    def _load_config(self) -> None:
        """Load configuration from the YAML file."""
        if not self.config_path.exists():
            # If config file doesn't exist, use defaults
            self._config = {}
            return

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                self._config = yaml.safe_load(f) or {}
        except Exception as e:
            # If we can't read the config, log and use defaults
            print(f"Warning: Could not load config from {self.config_path}: {e}")
            self._config = {}

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a configuration value by dot-notation key.

        Example: get("knowledge.vault_path")
        """
        keys = key.split(".")
        value = self._config
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        return value

    # Convenience properties for commonly accessed config values
    @property
    def enabled(self) -> bool:
        """Whether the knowledge system is enabled."""
        return self.get("knowledge.enabled", False)

    @staticmethod
    def _to_windows_path(path_str: str) -> str:
        """Convert MSYS/Git Bash paths (/c/...) to Windows paths (C:/...)."""
        import re
        # Match patterns like /c/, /d/, /e/, etc. at the start of a path
        match = re.match(r'^/([a-zA-Z])/(.*)', path_str)
        if match:
            drive = match.group(1).upper()
            rest = match.group(2)
            return f"{drive}:/{rest}"
        return path_str

    @property
    def vault_path(self) -> Path:
        """Path to the knowledge vault (DATA MIND)."""
        path_str = self.get("knowledge.vault_path", "")
        # Expand environment variables and user home
        path_str = os.path.expandvars(path_str)
        path_str = os.path.expanduser(path_str)
        # Handle MSYS/Git Bash paths (e.g., /c/Users/... -> C:/Users/...)
        path_str = self._to_windows_path(path_str)
        return Path(path_str)

    @property
    def embedding_model(self) -> str:
        """Name of the sentence-transformers model to use."""
        return self.get(
            "knowledge.embedding_model",
            "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        )

    @property
    def chunk_size(self) -> int:
        """Target number of tokens per chunk."""
        return self.get("knowledge.chunk_size", 400)

    @property
    def chunk_overlap(self) -> int:
        """Number of tokens to overlap between chunks."""
        return self.get("knowledge.chunk_overlap", 50)

    @property
    def index_path(self) -> Path:
        """Directory where the FAISS index and metadata are stored."""
        path_str = self.get(
            "knowledge.index_path",
            "${HERMES_HOME}/knowledge/embeddings",
        )
        path_str = os.path.expandvars(path_str)
        path_str = os.path.expanduser(path_str)
        # Handle MSYS/Git Bash paths
        path_str = self._to_windows_path(path_str)
        return Path(path_str)

    @property
    def update_frequency(self) -> int:
        """How often to run incremental indexing (in minutes)."""
        return self.get("knowledge.update_frequency", 15)

    @property
    def max_context_tokens(self) -> int:
        """Maximum number of tokens to include in the LLM context."""
        return self.get("knowledge.max_context_tokens", 8192)

    @property
    def hybrid_weights(self) -> Dict[str, float]:
        """Weights for hybrid retrieval (exact, vector)."""
        weights = self.get("knowledge.hybrid_weights", {"exact": 0.4, "vector": 0.6})
        # Ensure they sum to 1.0
        total = sum(weights.values())
        if total > 0:
            weights = {k: v / total for k, v in weights.items()}
        return weights

    @property
    def source_priority(self) -> List[str]:
        """Priority order for knowledge sources."""
        return self.get(
            "knowledge.source_priority",
            ["user_provided", "internal_docs", "structured_db", "external"],
        )

    @property
    def provenance_required(self) -> bool:
        """Whether provenance is required for knowledge chunks."""
        return self.get("knowledge.provenance.required", True)

    @property
    def provenance_include_timestamp(self) -> bool:
        """Whether to include timestamp in provenance."""
        return self.get("knowledge.provenance.include_timestamp", True)

    @property
    def provenance_include_confidence(self) -> bool:
        """Whether to include confidence in provenance."""
        return self.get("knowledge.provenance.include_confidence", True)