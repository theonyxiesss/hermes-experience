"""
Knowledge Retrieval MVP - Exact Search Retriever
"""

import subprocess
import shlex
import json
import shutil
from pathlib import Path
from typing import List, Optional, Dict, Any
import re
from datetime import datetime
from loguru import logger

from knowledge.config import KnowledgeConfig
from knowledge.types import KnowledgeChunk, Provenance, KnowledgeType, Confidence, RetrievalMethod
from knowledge.utils.hasher import string_hash
from knowledge.assembler.provenance_formatter import ProvenanceFormatter


class ExactRetriever:
    """Retrieves knowledge using exact/keyword search (via ripgrep or Hermes search_files)."""

    def __init__(self, vault_path: Optional[Path] = None):
        """
        Initialize the exact retriever.

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
        
        self.provenance_formatter = ProvenanceFormatter()
        logger.info(f"Initialized ExactRetriever for vault: {self.vault_path}")

    def search(self, query: str, limit: int = 10) -> List[KnowledgeChunk]:
        """
        Search for exact matches in the vault.

        Extracts keywords from natural-language queries for better matching.

        Args:
            query: The search query (can be a phrase, keyword, etc.)
            limit: Maximum number of results to return

        Returns:
            List of KnowledgeChunk objects sorted by relevance
        """
        logger.debug(f"Performing exact search for: '{query}' (limit={limit})")
        
        # Extract keywords from natural-language queries
        queries = self._extract_keywords(query)
        
        # Try to use ripgrep directly if available, otherwise fall back to direct file search
        all_results = []
        for q in queries:
            try:
                results = self._search_with_rg(q, limit)
            except Exception as e:
                logger.debug(f"Ripgrep failed for '{q}': {e}")
                results = self._search_direct_files(q, limit)
            all_results.extend(results)
        
        # Deduplicate by file path + line number
        seen = set()
        unique_results = []
        for r in all_results:
            key = (str(r.get('absolute_path', '')), r.get('line_number', 0))
            if key not in seen:
                seen.add(key)
                unique_results.append(r)
        
        # Convert results to KnowledgeChunks
        knowledge_chunks = []
        for result in unique_results[:limit]:
            try:
                chunk = self._result_to_knowledge_chunk(result, query)
                if chunk:
                    knowledge_chunks.append(chunk)
            except Exception as e:
                logger.warning(f"Failed to convert result to knowledge chunk: {e}")
                continue
        
        logger.debug(f"Exact search returned {len(knowledge_chunks)} chunks")
        return knowledge_chunks
    
    def _extract_keywords(self, query: str) -> List[str]:
        """Extract keywords from a natural-language query."""
        # Remove punctuation and split into words
        words = re.findall(r'[a-zA-Z\u0430-\u044f\u0410-\u042f\u0451\u04010-9_-]+', query)
        # Filter out common stop words (Russian + English)
        stop_words = {
            '\u043a\u0430\u043a\u043e\u0439', '\u043a\u0430\u043a\u0438\u0435', '\u043a\u0430\u043a\u0430\u044f', '\u043a\u0430\u043a\u043e\u0435',
            '\u043a\u0430\u043a', '\u0447\u0442\u043e', '\u0433\u0434\u0435', '\u043a\u043e\u0433\u0434\u0430', '\u043f\u043e\u0447\u0435\u043c\u0443',
            '\u043c\u043e\u0439', '\u043c\u043e\u044f', '\u043c\u043e\u0435', '\u043c\u043e\u0438',
            '\u0443', '\u0432', '\u043d\u0430', '\u0441', '\u043a', '\u043f\u043e', '\u043e\u0442', '\u043e', '\u043e\u0431',
            '\u044d\u0442\u043e', '\u044d\u0442\u043e\u0442', '\u044d\u0442\u0430', '\u044d\u0442\u0438',
            '\u0438', '\u0430', '\u043d\u043e', '\u0434\u0430', '\u0438\u043b\u0438', '\u043d\u0435', '\u043d\u0438', '\u0436\u0435', '\u0431\u044b',
            'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been',
            'i', 'my', 'me', 'you', 'your', 'he', 'she', 'it', 'we', 'they',
            'what', 'where', 'when', 'why', 'how', 'who', 'which',
            'current', 'status', 'project', 'projects', 'work', 'working',
            'tell', 'show', 'give', 'find', 'list', 'get', 'help',
            'about', 'for', 'with', 'without', 'from', 'to', 'into',
            'this', 'that', 'these', 'those',
            'now', 'currently', 'today', 'yesterday', 'recent'
        }
        # Build set of Russian stop words using Unicode escapes
        ru_stops = {chr(0x043a)+chr(0x0430)+chr(0x043a)+chr(0x043e)+chr(0x0439),  # какои?
                    chr(0x043a)+chr(0x0430)+chr(0x043a)+chr(0x0438)+chr(0x0435),  # какие
                    chr(0x043a)+chr(0x0430)+chr(0x043a),  # как
                    chr(0x0447)+chr(0x0442)+chr(0x043e),  # что
                    chr(0x0433)+chr(0x0434)+chr(0x0435),  # где
                    chr(0x043c)+chr(0x043e)+chr(0x0439),  # мои?
                    chr(0x043c)+chr(0x043e)+chr(0x044f),  # моя
                    chr(0x043c)+chr(0x043e)+chr(0x0435),  # мое
                    chr(0x043c)+chr(0x043e)+chr(0x0438),  # мои
                    chr(0x0443),  # у
                    chr(0x0432),  # в
                    chr(0x043d)+chr(0x0430),  # на
                    chr(0x0441),  # с
                    chr(0x043a),  # к
                    chr(0x043f)+chr(0x043e),  # по
                    chr(0x043e)+chr(0x0442),  # от
                    chr(0x043e),  # о
                    chr(0x043e)+chr(0x0431),  # об
                    chr(0x0438),  # и
                    chr(0x0430),  # а
                    chr(0x043d)+chr(0x043e),  # но
                    chr(0x0434)+chr(0x0430),  # да
                    chr(0x0438)+chr(0x043b)+chr(0x0438),  # или
                    chr(0x043d)+chr(0x0435),  # не
                    chr(0x043d)+chr(0x0438),  # ни
                    chr(0x0436)+chr(0x0435),  # же
        }
        stop_words.update(ru_stops)
        lowercase_words = [w.lower() for w in words]
        keywords = [w for i, w in enumerate(words) if lowercase_words[i] not in stop_words and len(w) > 2]
        if not keywords:
            return [query]
        result = [query]
        result.append(' '.join(keywords))
        if len(keywords) >= 2:
            result.extend(keywords[:3])
        return result

    def _search_with_rg(self, query: str, limit: int) -> List[Dict[str, Any]]:
        """
        Search using ripgrep (rg) command line tool.
        
        Returns:
            List of dictionaries with keys: file_path, line_number, line_text, match_text
        """
        # Check if rg is available
        if not shutil.which("rg"):
            raise FileNotFoundError("ripgrep (rg) not found in PATH")
        
        # Build the rg command
        # -i: case-insensitive
        # -n: show line numbers
        # --json: output as JSON for easier parsing
        # -m: limit number of matches
        cmd = [
            "rg",
            "--json",
            "-i",
            "-n",
            f"-m{limit * 2}",  # Get extra to account for filtering
            shlex.quote(query),
            str(self.vault_path)
        ]
        
        # Execute the command
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30  # 30 second timeout
        )
        
        if result.returncode not in [0, 1]:  # rg returns 1 when no matches found
            raise subprocess.CalledProcessError(result.returncode, cmd, result.stdout, result.stderr)
        
        # Parse JSON output
        matches = []
        for line in result.stdout.strip().split('\n'):
            if not line:
                continue
            try:
                data = json.loads(line)
                if data.get("type") == "match":
                    match_data = data["data"]
                    file_path = Path(match_data["path"]["text"])
                    line_number = match_data["line_number"]
                    line_text = match_data["lines"]["text"]
                    # Extract the actual match text from the line
                    submatches = match_data.get("submatches", [])
                    if submatches:
                        match_text = submatches[0]["match"]["text"]
                    else:
                        match_text = query  # Fallback
                    
                    matches.append({
                        "file_path": file_path,
                        "line_number": line_number,
                        "line_text": line_text.rstrip('\n'),
                        "match_text": match_text,
                        "absolute_path": self.vault_path / file_path
                    })
                    
                    if len(matches) >= limit:
                        break
            except (json.JSONDecodeError, KeyError) as e:
                logger.debug(f"Failed to parse rg JSON line: {e}")
                continue
        
        return matches

    def _search_with_hermes_tool(self, query: str, limit: int) -> List[Dict[str, Any]]:
        """
        Fallback search using Hermes search_files tool via subprocess.
        This is less ideal but ensures we have a fallback.
        """
        # This would require importing and using the Hermes agent's search_files tool
        # For MVP, we'll implement a simpler direct file search
        logger.warning("Using fallback direct file search (not optimized)")
        return self._search_direct_files(query, limit)

    def _search_direct_files(self, query: str, limit: int) -> List[Dict[str, Any]]:
        """
        Direct file search by reading files and using regex.
        Less efficient but works as a fallback.
        """
        matches = []
        query_pattern = re.compile(re.escape(query), re.IGNORECASE)
        
        # Get all markdown files
        markdown_files = []
        for extension in ["*.md", "*.markdown"]:
            markdown_files.extend(self.vault_path.rglob(extension))
        
        for file_path in markdown_files:
            try:
                content = file_path.read_text(encoding="utf-8")
                lines = content.splitlines()
                
                for line_num, line in enumerate(lines, 1):  # 1-indexed line numbers
                    if query_pattern.search(line):
                        matches.append({
                            "file_path": file_path.relative_to(self.vault_path),
                            "line_number": line_num,
                            "line_text": line,
                            "match_text": query,
                            "absolute_path": file_path
                        })
                        
                        if len(matches) >= limit:
                            break
            except Exception as e:
                logger.debug(f"Failed to read file {file_path}: {e}")
                continue
            
            if len(matches) >= limit:
                break
        
        return matches

    def _result_to_knowledge_chunk(
        self,
        result: Dict[str, Any],
        query: str
    ) -> Optional[KnowledgeChunk]:
        """
        Convert a search result to a KnowledgeChunk.
        
        Args:
            result: Dictionary from search results
            query: Original search query
            
        Returns:
            KnowledgeChunk or None if conversion failed
        """
        try:
            file_path = result["absolute_path"]
            line_number = result["line_number"]
            line_text = result["line_text"]
            
            # Get file modification time for timestamp
            file_mtime = file_path.stat().st_mtime
            
            # Extract a snippet around the match for better context
            # For simplicity, we'll use the whole line, but could extract more context
            chunk_text = line_text
            
            # Get relative path for provenance
            rel_path = file_path.relative_to(self.vault_path)
            
            # Try to extract section heading from the file
            section = self._extract_section_heading(file_path, line_number)
            
            # Create provenance
            provenance = Provenance(
                source="DATA MIND",
                document=str(rel_path),
                section=section,
                timestamp=datetime.fromtimestamp(file_mtime),
                confidence=Confidence.LOW,  # Exact search gets medium confidence by default
                retrieval_method=RetrievalMethod.EXACT,
                relevance_score=1.0,  # Exact match gets max relevance
                content_hash=string_hash(chunk_text)
            )
            
            # Create knowledge chunk (default to REFERENCE in MVP)
            knowledge_chunk = KnowledgeChunk(
                text=chunk_text,
                knowledge_type=KnowledgeType.REFERENCE,
                provenance=provenance
            )
            
            return knowledge_chunk
            
        except Exception as e:
            logger.debug(f"Failed to convert result to knowledge chunk: {e}")
            return None

    def _extract_section_heading(self, file_path: Path, line_number: int) -> str:
        """
        Extract the section heading for a given line number in a markdown file.
        
        Returns:
            The heading text or "Document Root" if not found
        """
        try:
            content = file_path.read_text(encoding="utf-8")
            lines = content.splitlines()
            
            # Look backwards from the line to find the nearest heading
            for i in range(line_number - 1, -1, -1):  # Convert to 0-indexed
                line = lines[i]
                # Match markdown heading: #, ##, ###, etc.
                heading_match = re.match(r'^(#{1,6})\s+(.+)$', line)
                if heading_match:
                    return heading_match.group(2).strip()
            
            return "Document Root"
        except Exception:
            return "Document Root"