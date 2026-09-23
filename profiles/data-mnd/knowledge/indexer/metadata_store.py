"""
Knowledge Retrieval MVP - Metadata Store
"""

import sqlite3
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json


@dataclass
class FileRecord:
    """Record of a file in the vault."""
    id: int
    path: str  # Relative path from vault root
    hash: str  # SHA256 of file content
    mtime: float  # Modification time
    size: int  # File size in bytes
    indexed_at: datetime  # When it was last indexed


@dataclass
class ChunkRecord:
    """Record of a text chunk."""
    id: int
    file_id: int  # Foreign key to files table
    chunk_index: int  # Index within the file
    text: str  # The chunk text
    token_count: int  # Approximate token count
    heading_path: str  # JSON-encoded list of heading texts
    wikilinks: str  # JSON-encoded list of wikilinks
    start_line: int  # Starting line number in file
    end_line: int  # Ending line number in file
    vector_id: Optional[int]  # ID in the FAISS index (None if not indexed)
    content_hash: str  # SHA256 of chunk text (for deduplication)


class MetadataStore:
    """Handles storage and retrieval of file and chunk metadata."""

    def __init__(self, db_path: Path):
        """
        Initialize the metadata store.

        Args:
            db_path: Path to the SQLite database file
        """
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()

    def _init_database(self) -> None:
        """Initialize the database tables if they don't exist."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    path TEXT UNIQUE NOT NULL,
                    hash TEXT NOT NULL,
                    mtime REAL NOT NULL,
                    size INTEGER NOT NULL,
                    indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_id INTEGER NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    token_count INTEGER NOT NULL,
                    heading_path TEXT,  -- JSON array
                    wikilinks TEXT,     -- JSON array
                    start_line INTEGER NOT NULL,
                    end_line INTEGER NOT NULL,
                    vector_id INTEGER,
                    content_hash TEXT NOT NULL,
                    FOREIGN KEY (file_id) REFERENCES files (id),
                    UNIQUE (file_id, chunk_index)
                )
            """)
            
            # Create indexes for common queries
            conn.execute("CREATE INDEX IF NOT EXISTS idx_files_path ON files(path)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_file_id ON chunks(file_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_content_hash ON chunks(content_hash)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_vector_id ON chunks(vector_id) WHERE vector_id IS NOT NULL")
            
            conn.commit()

    def add_or_update_file(self, file_path: Path, vault_root: Path) -> int:
        """
        Add a new file record or update an existing one.
        
        Returns:
            The file ID
        """
        # Get relative path from vault root
        try:
            rel_path = file_path.relative_to(vault_root)
        except ValueError:
            # If file is not under vault root, use absolute path (shouldn't happen in normal operation)
            rel_path = file_path
        
        rel_path_str = str(rel_path)
        
        # Get file stats
        stat = file_path.stat()
        file_hash = self._compute_file_hash(file_path)
        
        with sqlite3.connect(self.db_path) as conn:
            # Check if file already exists
            cursor = conn.execute(
                "SELECT id, hash FROM files WHERE path = ?", 
                (rel_path_str,)
            )
            row = cursor.fetchone()
            
            if row is None:
                # Insert new file
                cursor = conn.execute("""
                    INSERT INTO files (path, hash, mtime, size)
                    VALUES (?, ?, ?, ?)
                """, (rel_path_str, file_hash, stat.st_mtime, stat.st_size))
                file_id = cursor.lastrowid
            else:
                file_id, existing_hash = row
                # Update if hash changed
                if existing_hash != file_hash:
                    conn.execute("""
                        UPDATE files 
                        SET hash = ?, mtime = ?, size = ?, indexed_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                    """, (file_hash, stat.st_mtime, stat.st_size, file_id))
                # If hash hasn't changed, we still update mtime/size in case of metadata changes
                else:
                    conn.execute("""
                        UPDATE files 
                        SET mtime = ?, size = ?, indexed_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                    """, (stat.st_mtime, stat.st_size, file_id))
            
            conn.commit()
            return file_id

    def _compute_file_hash(self, file_path: Path) -> str:
        """Compute SHA256 hash of file contents."""
        sha256_hash = hashlib.sha256()
        with file_path.open("rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    def get_file_by_path(self, file_path: Path, vault_root: Path) -> Optional[FileRecord]:
        """Get a file record by its path."""
        try:
            rel_path = file_path.relative_to(vault_root)
        except ValueError:
            rel_path = file_path
        
        rel_path_str = str(rel_path)
        
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM files WHERE path = ?", 
                (rel_path_str,)
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

    def get_all_files(self) -> List[FileRecord]:
        """Get all file records."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM files ORDER BY path")
            rows = cursor.fetchall()
            
            return [
                FileRecord(
                    id=row["id"],
                    path=row["path"],
                    hash=row["hash"],
                    mtime=row["mtime"],
                    size=row["size"],
                    indexed_at=datetime.fromisoformat(row["indexed_at"])
                )
                for row in rows
            ]

    def add_chunk(
        self,
        file_id: int,
        chunk_index: int,
        text: str,
        token_count: int,
        heading_path: List[str],
        wikilinks: List[str],
        start_line: int,
        end_line: int,
        content_hash: str
    ) -> int:
        """
        Add a new chunk record.
        
        Returns:
            The chunk ID
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                INSERT INTO chunks (
                    file_id, chunk_index, text, token_count, 
                    heading_path, wikilinks, start_line, end_line, content_hash
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                file_id,
                chunk_index,
                text,
                token_count,
                json.dumps(heading_path),
                json.dumps(wikilinks),
                start_line,
                end_line,
                content_hash
            ))
            chunk_id = cursor.lastrowid
            conn.commit()
            return chunk_id

    def update_chunk_vector_id(self, chunk_id: int, vector_id: int) -> None:
        """Update the vector ID for a chunk (linking it to the FAISS index)."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE chunks SET vector_id = ? WHERE id = ?",
                (vector_id, chunk_id)
            )
            conn.commit()

    def get_chunks_for_file(self, file_id: int) -> List[ChunkRecord]:
        """Get all chunks for a given file."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM chunks WHERE file_id = ? ORDER BY chunk_index",
                (file_id,)
            )
            rows = cursor.fetchall()
            
            return [
                ChunkRecord(
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
                for row in rows
            ]

    def get_chunk_by_id(self, chunk_id: int) -> Optional[ChunkRecord]:
        """Get a chunk by its ID."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM chunks WHERE id = ?", (chunk_id,))
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

    def get_unindexed_chunks(self, limit: int = 100) -> List[ChunkRecord]:
        """Get chunks that haven't been assigned a vector ID yet."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM chunks WHERE vector_id IS NULL LIMIT ?",
                (limit,)
            )
            rows = cursor.fetchall()
            
            return [
                ChunkRecord(
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
                for row in rows
            ]

    def delete_file_record(self, file_path: Path, vault_root: Path) -> bool:
        """
        Delete a file record and all its associated chunks.
        
        Returns:
            True if a record was deleted, False if not found
        """
        try:
            rel_path = file_path.relative_to(vault_root)
        except ValueError:
            rel_path = file_path
        
        rel_path_str = str(rel_path)
        
        with sqlite3.connect(self.db_path) as conn:
            # Get the file ID first
            cursor = conn.execute(
                "SELECT id FROM files WHERE path = ?", 
                (rel_path_str,)
            )
            row = cursor.fetchone()
            
            if row is None:
                return False  # File not found
            
            file_id = row[0]
            
            # Delete chunks first (foreign key constraint)
            conn.execute("DELETE FROM chunks WHERE file_id = ?", (file_id,))
            # Delete the file record
            conn.execute("DELETE FROM files WHERE id = ?", (file_id,))
            conn.commit()
            return True

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the stored data."""
        with sqlite3.connect(self.db_path) as conn:
            # Count files
            cursor = conn.execute("SELECT COUNT(*) FROM files")
            file_count = cursor.fetchone()[0]
            
            # Count chunks
            cursor = conn.execute("SELECT COUNT(*) FROM chunks")
            chunk_count = cursor.fetchone()[0]
            
            # Count indexed chunks (those with vector_id)
            cursor = conn.execute("SELECT COUNT(*) FROM chunks WHERE vector_id IS NOT NULL")
            indexed_chunk_count = cursor.fetchone()[0]
            
            return {
                "file_count": file_count,
                "chunk_count": chunk_count,
                "indexed_chunk_count": indexed_chunk_count,
                "pending_chunks": chunk_count - indexed_chunk_count
            }