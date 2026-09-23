"""
Knowledge Retrieval MVP - Indexer Pipeline
"""

import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import numpy as np
import faiss
from loguru import logger

from knowledge.config import KnowledgeConfig
from knowledge.processor.chunker import SectionAwareChunker, MarkdownChunk
from knowledge.utils.hasher import file_hash, string_hash
from knowledge.utils.embedder import Embedder
from knowledge.indexer.metadata_store import MetadataStore, FileRecord, ChunkRecord
from knowledge.types import KnowledgeChunk, Provenance, KnowledgeType, Confidence, RetrievalMethod
from knowledge.assembler.provenance_formatter import ProvenanceFormatter


class IndexingPipeline:
    """Orchestrates the ingestion of documents into the knowledge base."""

    def __init__(self, vault_path: Optional[Path] = None):
        """
        Initialize the indexing pipeline.

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
        self.chunker = SectionAwareChunker(
            target_tokens=self.config.chunk_size,
            overlap_tokens=self.config.chunk_overlap
        )
        self.embedder = Embedder()
        self.metadata_store = MetadataStore(
            self.config.index_path / "metadata.sqlite"
        )
        self.provenance_formatter = ProvenanceFormatter()
        
        # FAISS index
        self.index_path = self.config.index_path
        self.index_path.mkdir(parents=True, exist_ok=True)
        self.faiss_index_path = self.index_path / "index.faiss"
        self._faiss_index: Optional[faiss.Index] = None
        
        logger.info(f"Initialized IndexingPipeline for vault: {self.vault_path}")

    def _get_faiss_index(self) -> faiss.Index:
        """Get or create the FAISS index."""
        if self._faiss_index is None:
            if self.faiss_index_path.exists():
                logger.info(f"Loading existing FAISS index from {self.faiss_index_path}")
                self._faiss_index = faiss.read_index(str(self.faiss_index_path))
            else:
                logger.info("Creating new FAISS index")
                # Using IndexFlatL2 for exact search (good for small datasets)
                self._faiss_index = faiss.IndexFlatL2(self.embedder.embedding_dimension)
                logger.info(f"Created FAISS index with dimension {self.embedder.embedding_dimension}")
        return self._faiss_index

    def _save_faiss_index(self) -> None:
        """Save the FAISS index to disk."""
        if self._faiss_index is not None:
            logger.info(f"Saving FAISS index to {self.faiss_index_path}")
            faiss.write_index(self._faiss_index, str(self.faiss_index_path))

    def _get_markdown_files(self) -> List[Path]:
        """Get all markdown files in the vault."""
        markdown_files = []
        for extension in ["*.md", "*.markdown"]:
            markdown_files.extend(self.vault_path.rglob(extension))
        return sorted(markdown_files)

    def _process_file(self, file_path: Path) -> Tuple[List[MarkdownChunk], str]:
        """
        Process a single markdown file into chunks.
        
        Returns:
            Tuple of (chunks, content_hash)
        """
        # Read the file
        try:
            text = file_path.read_text(encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to read file {file_path}: {e}")
            return [], ""
        
        # Compute content hash for change detection
        content_hash = string_hash(text)
        
        # Chunk the markdown
        chunks = self.chunker.chunk_markdown(text, file_path)
        
        logger.debug(f"Processed {file_path}: {len(chunks)} chunks")
        return chunks, content_hash

    def _chunks_to_knowledge_chunks(
        self,
        chunks: List[MarkdownChunk],
        file_path: Path,
        file_mtime: float
    ) -> List[KnowledgeChunk]:
        """
        Convert MarkdownChunks to KnowledgeChunks with provenance.
        
        In MVP, we assign a default knowledge type (REFERENCE) and confidence (MEDIUM).
        Full classification would be implemented in Phase 3.
        """
        knowledge_chunks = []
        rel_path = file_path.relative_to(self.vault_path)
        
        for i, chunk in enumerate(chunks):
            # Create provenance
            provenance = Provenance(
                source="DATA MIND",
                document=str(rel_path),
                section=" → ".join(chunk.heading_path) if chunk.heading_path else "Document Root",
                timestamp=datetime.fromtimestamp(file_mtime),
                confidence=Confidence.LOW,  # Default confidence in MVP
                retrieval_method=RetrievalMethod.VECTOR,  # Will be updated during retrieval
                relevance_score=0.0,  # Will be set during retrieval
                content_hash=string_hash(chunk.text)
            )
            
            # Create knowledge chunk (default to REFERENCE type in MVP)
            knowledge_chunk = KnowledgeChunk(
                text=chunk.text,
                knowledge_type=KnowledgeType.REFERENCE,  # Default in MVP
                provenance=provenance
            )
            knowledge_chunks.append(knowledge_chunk)
        
        return knowledge_chunks

    def index_file(self, file_path: Path) -> bool:
        """
        Index a single file (add or update in the knowledge base).
        
        Returns:
            True if the file was indexed (new or modified), False if unchanged
        """
        start_time = time.time()
        
        try:
            # Check if file needs indexing
            file_record = self.metadata_store.get_file_by_path(file_path, self.vault_path)
            current_hash = file_hash(file_path)
            
            if file_record is not None and file_record.hash == current_hash:
                logger.debug(f"File unchanged, skipping: {file_path}")
                return False  # File unchanged
            
            logger.info(f"Indexing file: {file_path}")
            
            # Process the file into chunks
            markdown_chunks, content_hash = self._process_file(file_path)
            if not markdown_chunks:
                logger.warning(f"No chunks generated for {file_path}")
                return False
            
            # Get file modification time
            file_mtime = file_path.stat().st_mtime
            
            # Convert to knowledge chunks
            knowledge_chunks = self._chunks_to_knowledge_chunks(
                markdown_chunks, file_path, file_mtime
            )
            
            # Extract texts for embedding
            texts = [chunk.text for chunk in knowledge_chunks]
            
            # Generate embeddings
            logger.debug(f"Generating embeddings for {len(texts)} chunks")
            embeddings = self.embedder.embed_texts(texts)
            
            # Ensure the file record exists before creating chunks
            file_id = file_record.id if file_record is not None else None
            if file_id is None:
                file_id = self.metadata_store.add_or_update_file(file_path, self.vault_path)
            
            # Store in metadata store and get chunk IDs
            chunk_ids = []
            for i, (mk, kc) in enumerate(zip(markdown_chunks, knowledge_chunks)):
                chunk_id = self.metadata_store.add_chunk(
                    file_id=file_id,
                    chunk_index=i,
                    text=kc.text,
                    token_count=mk.token_count,
                    heading_path=mk.heading_path,
                    wikilinks=mk.wikilinks,
                    start_line=mk.start_line,
                    end_line=mk.end_line,
                    content_hash=kc.provenance.content_hash
                )
                chunk_ids.append(chunk_id)
            
            # Add embeddings to FAISS index
            faiss_index = self._get_faiss_index()
            start_id = faiss_index.ntotal
            faiss_index.add(embeddings.astype('float32'))
            
            # Update chunk records with their vector IDs
            for i, chunk_id in enumerate(chunk_ids):
                vector_id = start_id + i
                self.metadata_store.update_chunk_vector_id(chunk_id, vector_id)
            
            # Save the index
            self._save_faiss_index()
            
            elapsed = time.time() - start_time
            logger.info(f"Indexed {file_path} in {elapsed:.2f}s ({len(knowledge_chunks)} chunks)")
            return True
            
        except Exception as e:
            logger.error(f"Failed to index file {file_path}: {e}")
            return False

    def index_vault(self, full_reindex: bool = False) -> Dict[str, Any]:
        """
        Index the entire vault.
        
        Args:
            full_reindex: If True, reindex all files. If False, only index new/changed files.
            
        Returns:
            Statistics about the indexing operation
        """
        start_time = time.time()
        logger.info(f"Starting vault indexing (full_reindex={full_reindex})")
        
        if full_reindex:
            logger.info("Performing full reindex - clearing all existing data")
            # Clear FAISS index
            self._faiss_index = faiss.IndexFlatL2(self.embedder.embedding_dimension)
            if self.faiss_index_path.exists():
                self.faiss_index_path.unlink()
            # Clear metadata store (files + chunks + vector IDs)
            if self.metadata_store.db_path.exists():
                self.metadata_store.db_path.unlink()
            # Re-initialize metadata store
            from knowledge.indexer.metadata_store import MetadataStore
            self.metadata_store = MetadataStore(self.config.index_path / "metadata.sqlite")
        
        # Get all markdown files in the vault
        markdown_files = self._get_markdown_files()
        logger.info(f"Found {len(markdown_files)} markdown files in vault")
        
        # Track statistics
        stats = {
            "total_files": len(markdown_files),
            "new_files": 0,
            "modified_files": 0,
            "unchanged_files": 0,
            "total_chunks": 0,
            "errors": 0,
            "start_time": start_time,
            "end_time": None
        }
        
        # Process each file
        for file_path in markdown_files:
            try:
                # Check if file exists in metadata
                file_record = self.metadata_store.get_file_by_path(file_path, self.vault_path)
                current_hash = file_hash(file_path)
                
                needs_indexing = (
                    full_reindex or 
                    file_record is None or 
                    file_record.hash != current_hash
                )
                
                if needs_indexing:
                    if self.index_file(file_path):
                        if file_record is None:
                            stats["new_files"] += 1
                        else:
                            stats["modified_files"] += 1
                    else:
                        stats["errors"] += 1
                else:
                    stats["unchanged_files"] += 1
                    
            except Exception as e:
                logger.error(f"Error processing file {file_path}: {e}")
                stats["errors"] += 1
        
        # Get final statistics from metadata store
        meta_stats = self.metadata_store.get_stats()
        stats.update(meta_stats)
        
        end_time = time.time()
        stats["end_time"] = end_time
        stats["elapsed_time"] = end_time - start_time
        
        logger.info(f"Indexing complete in {stats['elapsed_time']:.2f}s")
        logger.info(f"  New files: {stats['new_files']}")
        logger.info(f"  Modified files: {stats['modified_files']}")
        logger.info(f"  Unchanged files: {stats['unchanged_files']}")
        logger.info(f"  Errors: {stats['errors']}")
        logger.info(f"  Total chunks: {stats['chunk_count']}")
        logger.info(f"  Indexed chunks: {stats['indexed_chunk_count']}")
        
        return stats

    def delete_deleted_files(self) -> int:
        """
        Remove files from the metadata store that no longer exist in the vault.
        
        Returns:
            Number of files deleted
        """
        logger.info("Checking for deleted files...")
        
        # Get all files currently in metadata
        stored_files = self.metadata_store.get_all_files()
        deleted_count = 0
        
        for file_record in stored_files:
            file_path = self.vault_path / file_record.path
            if not file_path.exists():
                logger.info(f"Removing deleted file from index: {file_record.path}")
                if self.metadata_store.delete_file_record(file_path, self.vault_path):
                    deleted_count += 1
        
        if deleted_count > 0:
            logger.info(f"Removed {deleted_count} deleted files from metadata")
            # Note: We don't remove vectors from FAISS index here as it's complex
            # In a production system we might want to rebuild the index periodically
            # For MVP, we'll accept that deleted file vectors remain in the index
            # but are not accessible because their metadata is gone
        
        return deleted_count