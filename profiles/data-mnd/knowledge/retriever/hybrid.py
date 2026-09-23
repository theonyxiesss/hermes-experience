"""
Knowledge Retrieval MVP - Hybrid Retriever
"""

from typing import List, Optional
from pathlib import Path
from loguru import logger

from knowledge.config import KnowledgeConfig
from knowledge.types import KnowledgeChunk
from knowledge.retriever.exact import ExactRetriever
from knowledge.retriever.vector import VectorRetriever


class HybridRetriever:
    """Combines exact and vector search results using weighted scoring."""

    def __init__(self, vault_path: Optional[Path] = None):
        """
        Initialize the hybrid retriever.

        Args:
            vault_path: Path to the knowledge vault. If None, reads from config.
        """
        self.config = KnowledgeConfig()
        
        if vault_path is None:
            self.vault_path = self.config.vault_path
        else:
            self.vault_path = vault_path
        
        # Initialize the sub-retrievers
        self.exact_retriever = ExactRetriever(vault_path)
        self.vector_retriever = VectorRetriever(vault_path)
        
        logger.info(f"Initialized HybridRetriever for vault: {self.vault_path}")

    def search(self, query: str, limit: int = 10) -> List[KnowledgeChunk]:
        """
        Search using both exact and vector retrieval, then fuse the results.

        Args:
            query: The search query text
            limit: Maximum number of results to return

        Returns:
            List of KnowledgeChunk objects sorted by relevance (descending)
        """
        logger.debug(f"Performing hybrid search for: '{query}' (limit={limit})")
        
        # Get weights from config
        weights = self.config.hybrid_weights
        exact_weight = weights.get("exact", 0.4)
        vector_weight = weights.get("vector", 0.6)
        
        logger.debug(f"Using weights: exact={exact_weight}, vector={vector_weight}")
        
        # Get results from both retrievers
        # We'll ask for more results than needed to account for deduplication and re-ranking
        search_limit = min(limit * 3, 50)  # Reasonable upper bound
        
        exact_results = self.exact_retriever.search(query, limit=search_limit)
        vector_results = self.vector_retriever.search(query, limit=search_limit)
        
        logger.debug(f"Exact search returned {len(exact_results)} chunks")
        logger.debug(f"Vector search returned {len(vector_results)} chunks")
        
        # Convert to dictionaries for easier manipulation
        exact_dicts = [self._chunk_to_dict(chunk, "exact") for chunk in exact_results]
        vector_dicts = [self._chunk_to_dict(chunk, "vector") for chunk in vector_results]
        
        # Combine and deduplicate by content_hash
        combined = self._deduplicate_by_content_hash(exact_dicts + vector_dicts)
        
        # Apply weighted scoring
        scored_results = self._apply_weighted_scoring(
            combined, exact_weight, vector_weight
        )
        
        # Sort by final score (descending)
        scored_results.sort(key=lambda x: x["final_score"], reverse=True)
        
        # Take top results and convert back to KnowledgeChunks
        top_results = scored_results[:limit]
        knowledge_chunks = [self._dict_to_chunk(item) for item in top_results]
        
        logger.debug(f"Hybrid search returned {len(knowledge_chunks)} chunks")
        return knowledge_chunks

    def _chunk_to_dict(self, chunk: KnowledgeChunk, retrieval_method: str) -> dict:
        """
        Convert a KnowledgeChunk to a dictionary for processing.
        
        Args:
            chunk: The KnowledgeChunk to convert
            retrieval_method: Either "exact" or "vector"
            
        Returns:
            Dictionary representation of the chunk
        """
        return {
            "text": chunk.text,
            "knowledge_type": chunk.knowledge_type,
            "provenance": chunk.provenance,
            "retrieval_method": retrieval_method,  # Will be overridden by hybrid
            "exact_score": chunk.provenance.relevance_score if retrieval_method == "exact" else 0.0,
            "vector_score": chunk.provenance.relevance_score if retrieval_method == "vector" else 0.0,
            "content_hash": chunk.provenance.content_hash
        }

    def _dict_to_chunk(self, item: dict) -> KnowledgeChunk:
        """
        Convert a dictionary back to a KnowledgeChunk.
        
        Args:
            item: Dictionary with chunk data
            
        Returns:
            KnowledgeChunk object
        """
        # Update the provenance with the hybrid retrieval method and final score
        provenance = item["provenance"]
        # Create a new provenance with updated values
        from knowledge.types import Provenance, RetrievalMethod
        from datetime import datetime
        
        new_provenance = Provenance(
            source=provenance.source,
            document=provenance.document,
            section=provenance.section,
            timestamp=provenance.timestamp,
            confidence=provenance.confidence,
            retrieval_method=RetrievalMethod(item["retrieval_method"]) if isinstance(item["retrieval_method"], str) else item["retrieval_method"],
            relevance_score=item["final_score"],
            content_hash=provenance.content_hash
        )
        
        return KnowledgeChunk(
            text=item["text"],
            knowledge_type=item["knowledge_type"],
            provenance=new_provenance
        )

    def _deduplicate_by_content_hash(self, chunks: List[dict]) -> List[dict]:
        """
        Remove duplicate chunks based on content_hash.
        Keeps the first occurrence (which could be from either retriever).
        
        Args:
            chunks: List of chunk dictionaries
            
        Returns:
            List of deduplicated chunk dictionaries
        """
        seen_hashes = set()
        deduplicated = []
        
        for chunk in chunks:
            content_hash = chunk["content_hash"]
            if content_hash not in seen_hashes:
                seen_hashes.add(content_hash)
                deduplicated.append(chunk)
        
        return deduplicated

    def _apply_weighted_scoring(
        self,
        chunks: List[dict],
        exact_weight: float,
        vector_weight: float
    ) -> List[dict]:
        """
        Apply weighted scoring to combine exact and vector scores.
        
        Args:
            chunks: List of chunk dictionaries
            exact_weight: Weight for exact search scores (0-1)
            vector_weight: Weight for vector search scores (0-1)
            
        Returns:
            List of chunk dictionaries with added final_score
        """
        # Normalize weights to sum to 1.0
        total_weight = exact_weight + vector_weight
        if total_weight > 0:
            exact_weight = exact_weight / total_weight
            vector_weight = vector_weight / total_weight
        
        for chunk in chunks:
            exact_score = chunk["exact_score"]
            vector_score = chunk["vector_score"]
            
            # Calculate weighted final score
            final_score = (exact_weight * exact_score) + (vector_weight * vector_score)
            
            # Add the scores to the chunk dictionary
            chunk["exact_score"] = exact_score
            chunk["vector_score"] = vector_score
            chunk["final_score"] = final_score
            chunk["retrieval_method"] = "hybrid"  # Mark as hybrid retrieval
        
        return chunks