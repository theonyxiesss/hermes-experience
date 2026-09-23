"""
Knowledge Retrieval MVP - Type Definitions
"""

from enum import Enum
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional


class KnowledgeType(Enum):
    """Types of knowledge that can be retrieved."""
    FACT = "fact"
    DECISION = "decision"
    HYPOTHESIS = "hypothesis"
    PREFERENCE = "preference"
    PROCEDURE = "procedure"
    REFERENCE = "reference"


class Confidence(Enum):
    """Confidence levels for knowledge chunks."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class RetrievalMethod(Enum):
    """Methods used to retrieve knowledge."""
    EXACT = "exact"
    VECTOR = "vector"
    HYBRID = "hybrid"


@dataclass
class Provenance:
    """Metadata about the source and retrieval of a knowledge chunk."""
    source: str  # e.g., "DATA MIND"
    document: str  # Relative path from vault root (e.g., "02_Projects/zarabotok.md")
    section: str  # Section heading or identifier
    timestamp: datetime  # When the source was last modified
    confidence: Confidence  # Confidence in the knowledge
    retrieval_method: RetrievalMethod  # How the chunk was retrieved
    relevance_score: float  # Normalized relevance score (0.0-1.0)
    content_hash: str  # SHA256 hash of the exact chunk text


@dataclass
class KnowledgeChunk:
    """A unit of knowledge with its provenance."""
    text: str  # The actual text content
    knowledge_type: KnowledgeType  # Type of knowledge
    provenance: Provenance  # Source and retrieval metadata

    def __post_init__(self):
        # Ensure provenance confidence matches chunk type if not set
        if self.provenance.confidence == Confidence.LOW and self.knowledge_type in [
            KnowledgeType.FACT,
            KnowledgeType.DECISION,
        ]:
            # FACT and DECISION should not be LOW confidence by default
            pass  # Keep as is, but could be adjusted in classifier (not implemented in MVP)