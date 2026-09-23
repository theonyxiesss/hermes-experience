"""
Knowledge Retrieval MVP - Vector Search Retriever
"""

import numpy as np
import faiss
import sqlite3
import json
from pathlib import Path
from typing import List, Optional
from datetime import datetime
from loguru import logger

from knowledge.config import KnowledgeConfig
from knowledge.types import KnowledgeChunk, Provenance, KnowledgeType, Confidence, RetrievalMethod
from knowledge.utils.hasher import string_hash
from knowledge.assembler.provenance_formatter import ProvenanceFormatter
from knowledge.utils.embedder import Embedder
from knowledge.indexer.metadata_store import MetadataStore, ChunkRecord, FileRecord


class VectorRetriever:
    """Retrieves knowledge using vector/semantic search (FAISS)."""

    def __init__(self, vault_path: Optional[Path] = None):
        """
        Initialize the vector retriever.

        Args:
            vault_path: Path to the knowledge vault. If None, reads from config.
        """
        self.config = KnowledgeConfig()
        
        if vault_path is None:
            self.vault_path = self.config.vault_path
        else:
            self.vault_path = vault_path
        
        if not self.vault_path.exists():
            raise ValueError(f"Vault path does not exist: {self.vault_path}")
        
        # Initialize components
        self.embedder = Embedder()
        self.metadata_store = MetadataStore(
            self.config.index_path / "metadata.sqlite"
        )
        self.provenance_formatter = ProvenanceFormatter()
        
        # FAISS index
        self.index_path = self.config.index_path
        self.faiss_index_path = self.index_path / "index.faiss"
        self._faiss_index: Optional[faiss.Index] = None
        
        logger.info(f"Initialized VectorRetriever for vault: {self.vault_path}")

    def _get_faiss_index(self) -> faiss.Index:
        """Get or create the FAISS index."""
        if self._faiss_index is None:
            if self.faiss_index_path.exists():
                logger.info(f"Loading existing FAISS index from {self.faiss_index_path}")
                self._faiss_index = faiss.read_index(str(self.faiss_index_path))
                logger.info(f"Loaded FAISS index with {self._faiss_index.ntotal} vectors")
            else:
                logger.warning("FAISS index not found - returning empty results")
                # Create an empty index to avoid errors
                self._faiss_index = faiss.IndexFlatL2(self.embedder.embedding_dimension)
        return self._faiss_index

    def search(self, query: str, limit: int = 10) -> List[KnowledgeChunk]:
        """
        Search for semantic matches in the vault using vector similarity.

        Args:
            query: The search query text
            limit: Maximum number of results to return

        Returns:
            List of KnowledgeChunk objects sorted by relevance (descending)
        """
        logger.debug(f"Performing vector search for: '{query}' (limit={limit})")
        
        # Get the FAISS index
        index = self._get_faiss_index()
        
        if index.ntotal == 0:
            logger.warning("FAISS index is empty - returning no results")
            return []
        
        try:
            # Embed the query
            query_embedding = self.embedder.embed_query(query)
            
            # Search the index
            # Return more results than needed to account for filtering
            k = min(limit * 2, index.ntotal)
            distances, indices = index.search(query_embedding.astype('float32'), k)
            
            # Convert results to KnowledgeChunks
            knowledge_chunks = []
            for i, (distance, faiss_id) in enumerate(zip(distances[0], indices[0])):
                # Skip invalid results
                if faiss_id < 0 or faiss_id >= index.ntotal:
                    continue
                
                try:
                    chunk = self._faiss_result_to_knowledge_chunk(
                        faiss_id, distance, query
                    )
                    if chunk:
                        knowledge_chunks.append(chunk)
                except Exception as e:
                    logger.warning(f"Failed to convert FAISS result {faiss_id} to knowledge chunk: {e}")
                    continue
                
                if len(knowledge_chunks) >= limit:
                    break
            
            logger.debug(f"Vector search returned {len(knowledge_chunks)} chunks")
            return knowledge_chunks
            
        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            return []

    def _faiss_result_to_knowledge_chunk(
        self,
        faiss_id: int,
        distance: float,
        query: str
    ) -> Optional[KnowledgeChunk]:
        """
        Convert a FAISS search result to a KnowledgeChunk.
        
        Args:
            faiss_id: The ID in the FAISS index
            distance: The L2 distance from the query vector
            query: Original search query
            
        Returns:
            KnowledgeChunk or None if conversion failed
        """
        try:
            # Get the chunk record from metadata store
            faiss_id = int(faiss_id)
            chunk_record = self._get_chunk_by_vector_id(faiss_id)
            if chunk_record is None:
                logger.debug(f"No chunk record found for FAISS ID {faiss_id}")
                return None
            
            # Get the file record
            file_record = self._get_file_by_id(chunk_record.file_id)
            if file_record is None:
                logger.debug(f"No file record found for file ID {chunk_record.file_id}")
                return None
            
            # Get file modification time for timestamp
            file_mtime = file_record.mtime
            
            # Convert distance to relevance score (0-1 range)
            # For L2 distance, smaller is better. We'll use a simple transformation:
            # relevance = 1 / (1 + distance)
            # This gives us a score in (0,1] where 1 is identical vectors
            relevance_score = 1.0 / (1.0 + distance)
            
            # Get relative path for provenance
            rel_path = Path(file_record.path)
            
            # Parse heading path and wikilinks from JSON
            heading_path = chunk_record.heading_path
            wikilinks = chunk_record.wikilinks
            
            # Create provenance
            provenance = Provenance(
                source="DATA MIND",
                document=str(rel_path),
                section=" → ".join(heading_path) if heading_path else "Document Root",
                timestamp=datetime.fromtimestamp(file_mtime),
                confidence=Confidence.LOW,  # Default confidence in MVP
                retrieval_method=RetrievalMethod.VECTOR,
                relevance_score=relevance_score,
                content_hash=chunk_record.content_hash
            )
            
            # Create knowledge chunk (default to REFERENCE in MVP)
            knowledge_chunk = KnowledgeChunk(
                text=chunk_record.text,
                knowledge_type=KnowledgeType.REFERENCE,
                provenance=provenance
            )
            
            return knowledge_chunk
            
        except Exception as e:
            logger.debug(f"Failed to convert FAISS result to knowledge chunk: {e}")
            return None

    def _get_chunk_by_vector_id(self, vector_id: int) -> Optional[ChunkRecord]:
        """Get a chunk record by its vector ID."""
        try:
            with sqlite3.connect(self.metadata_store.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    "SELECT * FROM chunks WHERE vector_id = ?", 
                    (vector_id,)
                )
                row = cursor.fetchone()
                
                if row is None:
                    return None
                
                return ChunkRecord(
                    id=row["id"],
                    file_id=row["file_id"],
                    chunk_index=row["chunk_index"],
                    text=row["text"],
                    token_count=row["token_count"],
                    heading_path=json.loads(row["heading_path"]) if row["heading_path"] else [],
                    wikilinks=json.loads(row["wikilinks"]) if row["wikilinks"] else [],
                    start_line=row["start_line"],
                    end_line=row["end_line"],
                    vector_id=row["vector_id"],
                    content_hash=row["content_hash"]
                )
        except Exception as e:
            logger.debug(f"Failed to get chunk by vector ID {vector_id}: {e}")
            return None

    def _get_file_by_id(self, file_id: int) -> Optional[FileRecord]:
        """Get a file record by its ID."""
        try:
            with sqlite3.connect(self.metadata_store.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    "SELECT * FROM files WHERE id = ?", 
                    (file_id,)
                )
                row = cursor.fetchone()
                
                if row is None:
                    return None
                
                return FileRecord(
                    id=row["id"],
                    path=row["path"],
                    hash=row["hash"],
                    mtime=row["mtime"],
                    size=row["size"],
                    indexed_at=datetime.fromisoformat(row["indexed_at"])
                )
        except Exception as e:
            logger.debug(f"Failed to get file by ID {file_id}: {e}")
            return None