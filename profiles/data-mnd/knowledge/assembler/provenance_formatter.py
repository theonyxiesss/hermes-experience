"""
Knowledge Retrieval MVP - Provenance Formatter
"""

from typing import List, Optional
from datetime import datetime
from loguru import logger

from knowledge.config import KnowledgeConfig
from knowledge.types import KnowledgeChunk, Provenance, KnowledgeType, Confidence, RetrievalMethod


class ProvenanceFormatter:
    """Formats provenance information for inclusion in LLM context and answers."""

    def __init__(self):
        """Initialize the provenance formatter."""
        self.config = KnowledgeConfig()
        logger.info("Initialized ProvenanceFormatter")

    def format_provenance_for_context(self, chunk: KnowledgeChunk) -> str:
        """
        Format provenance information to be included in the LLM context.
        
        This creates a prefix that can be prepended to each chunk to provide
        source information to the LLM.

        Args:
            chunk: The knowledge chunk to format

        Returns:
            A string containing formatted provenance information
        """
        prov = chunk.provenance
        
        # Format timestamp
        timestamp_str = prov.timestamp.strftime("%Y-%m-%d") if prov.timestamp else "unknown date"
        
        # Format confidence
        confidence_str = prov.confidence.value.upper() if prov.confidence else "UNKNOWN"
        
        # Format retrieval method
        retrieval_str = prov.retrieval_method.value.upper() if prov.retrieval_method else "UNKNOWN"
        
        # Build the provenance string
        parts = [
            f"Source: {prov.source}",
            f"Document: {prov.document}",
            f"Section: {prov.section}",
            f"Date: {timestamp_str}",
            f"Confidence: {confidence_str}",
            f"Method: {retrieval_str}",
            f"Relevance: {prov.relevance_score:.2f}"
        ]
        
        provenance_text = " | ".join(parts)
        
        # Return as a comment-like prefix that won't interfere with the content
        return f"[PROVENANCE: {provenance_text}]"

    def format_sources_block(self, chunks: List[KnowledgeChunk]) -> str:
        """
        Format a Sources block for inclusion in the final answer.
        
        This creates a human-readable list of sources that supported the answer.

        Args:
            chunks: List of knowledge chunks that contributed to the answer

        Returns:
            A formatted Sources block string
        """
        if not chunks:
            return "Sources:\nNo sources found."
        
        # Deduplicate by document to avoid listing the same source multiple times
        seen_documents = set()
        unique_chunks = []
        for chunk in chunks:
            doc_key = chunk.provenance.document
            if doc_key not in seen_documents:
                seen_documents.add(doc_key)
                unique_chunks.append(chunk)
        
        # Sort by relevance score (descending) then by document name
        unique_chunks.sort(
            key=lambda c: (
                -c.provenance.relevance_score,  # Descending relevance
                c.provenance.document           # Ascending document name
            )
        )
        
        # Build the sources block
        lines = ["Sources:"]
        for i, chunk in enumerate(unique_chunks, 1):
            prov = chunk.provenance
            
            # Format timestamp
            timestamp_str = prov.timestamp.strftime("%Y-%m-%d") if prov.timestamp else "unknown date"
            
            # Format confidence
            confidence_str = prov.confidence.value.upper() if prov.confidence else "UNKNOWN"
            
            # Format retrieval method
            retrieval_str = prov.retrieval_method.value.upper() if prov.retrieval_method else "UNKNOWN"
            
            # Format the line
            line = (
                f"[{i}] {prov.document} → {prov.section} → "
                f"{timestamp_str} → {confidence_str} → {retrieval_str}"
            )
            lines.append(line)
        
        return "\n".join(lines)

    def format_inline_citation(self, chunk: KnowledgeChunk) -> str:
        """
        Format an inline citation reference.
        
        Args:
            chunk: The knowledge chunk to cite

        Returns:
            A short citation string like "[1]" or "[DATA MIND: 02_Projects/zarabotok.md]"
        """
        # For MVP, we'll use a simple format
        # In a full implementation, this would correlate with the sources block numbering
        return f"[DATA MIND: {chunk.provenance.document}]"