"""
Knowledge Retrieval MVP - Context Builder
"""

from typing import List, Optional
from dataclasses import dataclass
from loguru import logger

from knowledge.config import KnowledgeConfig
from knowledge.types import KnowledgeChunk, Provenance, KnowledgeType, Confidence


@dataclass
class ContextResult:
    """Result of context building."""
    chunks: List[KnowledgeChunk]
    total_tokens: int
    warning: Optional[str] = None  # Warning if context was truncated


class ContextBuilder:
    """Builds a context window from retrieved knowledge chunks."""

    def __init__(self, max_tokens: Optional[int] = None):
        """
        Initialize the context builder.

        Args:
            max_tokens: Maximum number of tokens for the context.
                       If None, reads from config.
        """
        self.config = KnowledgeConfig()
        self.max_tokens = max_tokens if max_tokens is not None else self.config.max_context_tokens
        logger.info(f"Initialized ContextBuilder with max_tokens={self.max_tokens}")

    def build_context(
        self,
        chunks: List[KnowledgeChunk],
        query: Optional[str] = None
    ) -> ContextResult:
        """
        Build a context window from knowledge chunks.

        Args:
            chunks: List of knowledge chunks to include in context
            query: Optional original query (can be used for relevance boosting)

        Returns:
            ContextResult containing the selected chunks and token count
        """
        if not chunks:
            return ContextResult(chunks=[], total_tokens=0)

        logger.debug(f"Building context from {len(chunks)} chunks (max_tokens={self.max_tokens})")
        
        # Sort chunks by priority:
        # 1. Confidence (HIGH > MEDIUM > LOW)
        # 2. Knowledge type (FACT/DECISION first, then others)
        # 3. Relevance score (higher is better)
        # 4. Token count (smaller chunks first for density)
        
        def chunk_priority(chunk: KnowledgeChunk) -> tuple:
            # Confidence weight: HIGH=3, MEDIUM=2, LOW=1
            confidence_weight = {
                Confidence.HIGH: 3,
                Confidence.MEDIUM: 2,
                Confidence.LOW: 1
            }.get(chunk.provenance.confidence, 1)
            
            # Knowledge type weight: FACT and DECISION are prioritized
            type_weight = {
                KnowledgeType.FACT: 2,
                KnowledgeType.DECISION: 2,
                KnowledgeType.PROCEDURE: 1,
                KnowledgeType.REFERENCE: 1,
                KnowledgeType.HYPOTHESIS: 1,
                KnowledgeType.PREFERENCE: 1
            }.get(chunk.knowledge_type, 1)
            
            # Relevance score (0-1 range)
            relevance_score = chunk.provenance.relevance_score
            
            # Token count (inverse - smaller chunks preferred)
            # Avoid division by zero
            token_count = max(1, len(chunk.text) // 4)  # Rough token estimate
            
            # Return tuple for sorting (higher values = higher priority)
            # We negate token_count because we want smaller chunks to have higher priority
            return (
                confidence_weight,
                type_weight,
                relevance_score,
                -token_count  # Negative so smaller chunks sort first
            )
        
        # Sort chunks by priority
        sorted_chunks = sorted(chunks, key=chunk_priority, reverse=True)
        
        # Select chunks until we reach the token limit
        selected_chunks = []
        total_tokens = 0
        
        for chunk in sorted_chunks:
            # Estimate token count for this chunk
            # Simple approximation: 1 token ≈ 4 characters
            chunk_tokens = max(1, len(chunk.text) // 4)
            
            # Check if adding this chunk would exceed the limit
            if total_tokens + chunk_tokens > self.max_tokens:
                # If we haven't selected any chunks yet, we have to take at least one
                if not selected_chunks:
                    # Take a truncated version of this chunk
                    # For simplicity, we'll just take the chunk and accept the overflow
                    # In a more sophisticated implementation, we'd truncate the text
                    selected_chunks.append(chunk)
                    total_tokens += chunk_tokens
                    logger.warning(
                        f"Single chunk exceeds token limit ({chunk_tokens} > {self.max_tokens}). "
                        f"Context will exceed limit by {total_tokens - self.max_tokens} tokens."
                    )
                break
            
            # Add the chunk
            selected_chunks.append(chunk)
            total_tokens += chunk_tokens
        
        logger.debug(f"Built context with {len(selected_chunks)} chunks, {total_tokens} tokens")
        
        # Check if we need to warn about truncation
        warning = None
        if len(selected_chunks) < len(chunks):
            warning = (
                f"Context truncated: {len(chunks) - len(selected_chunks)} chunks omitted "
                f"to stay within {self.max_tokens} token limit"
            )
            logger.info(warning)
        
        return ContextResult(
            chunks=selected_chunks,
            total_tokens=total_tokens,
            warning=warning
        )