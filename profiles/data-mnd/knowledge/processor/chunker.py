"""
Knowledge Retrieval MVP - Markdown Chunker
"""

import re
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
import hashlib


@dataclass
class MarkdownChunk:
    """A chunk of markdown text with metadata."""
    text: str
    heading_path: List[str] = field(default_factory=list)
    wikilinks: List[str] = field(default_factory=list)
    token_count: int = 0
    char_count: int = 0
    start_line: int = 0
    end_line: int = 0

    def __post_init__(self):
        self.char_count = len(self.text)
        # Simple token approximation: 1 token ≈ 4 characters for English
        # This is a rough estimate; for better accuracy we could use tiktoken
        self.token_count = max(1, len(self.text) // 4)


class SectionAwareChunker:
    """Chunks markdown text while preserving section hierarchy."""

    def __init__(self, target_tokens: int = 400, overlap_tokens: int = 50):
        """
        Initialize the chunker.

        Args:
            target_tokens: Target number of tokens per chunk
            overlap_tokens: Number of tokens to overlap between chunks
        """
        self.target_tokens = target_tokens
        self.overlap_tokens = overlap_tokens
        self.heading_pattern = re.compile(r'^(#{1,6})\s+(.+)$', re.MULTILINE)
        self.wikilink_pattern = re.compile(r'\[\[([^\]]+)\]\]')

    def chunk_markdown(
        self,
        text: str,
        source_path: Optional[Path] = None
    ) -> List[MarkdownChunk]:
        """
        Chunk markdown text into section-aware pieces.

        Args:
            text: The markdown text to chunk
            source_path: Optional path to the source file (for logging)

        Returns:
            List of MarkdownChunk objects
        """
        if not text.strip():
            return []

        # Split text into lines for line number tracking
        lines = text.splitlines(True)
        
        # Find all headings with their line numbers
        headings = self._find_headings(lines)
        
        # If no headings, treat entire document as one section
        if not headings:
            headings = [(-1, [], "Document Root")]
        
        # Create sections based on headings
        sections = self._create_sections(lines, headings)
        
        # Chunk each section
        chunks = []
        for section_text, heading_path, start_line, end_line in sections:
            section_chunks = self._chunk_section(
                section_text, heading_path, start_line, end_line
            )
            chunks.extend(section_chunks)
        
        return chunks

    def _find_headings(self, lines: List[str]) -> List[Tuple[int, List[str], str]]:
        """
        Find all headings in the markdown lines.

        Returns:
            List of tuples: (line_number, heading_path_list, heading_text)
        """
        headings = []
        heading_stack = []  # Stack of (level, text) for current hierarchy
        
        for i, line in enumerate(lines):
            match = self.heading_pattern.match(line)
            if match:
                level = len(match.group(1))  # Number of # characters
                heading_text = match.group(2).strip()
                
                # Update heading stack: remove deeper or same level headings
                while heading_stack and heading_stack[-1][0] >= level:
                    heading_stack.pop()
                
                # Add current heading to stack
                heading_stack.append((level, heading_text))
                
                # Current path is all heading texts in stack
                heading_path = [text for _, text in heading_stack]
                headings.append((i, heading_path.copy(), heading_text))
        
        return headings

    def _create_sections(
        self,
        lines: List[str],
        headings: List[Tuple[int, List[str], str]]
    ) -> List[Tuple[str, List[str], int, int]]:
        """
        Create text sections based on heading boundaries.

        Returns:
            List of tuples: (section_text, heading_path, start_line, end_line)
        """
        sections = []
        
        for i, (line_num, heading_path, heading_text) in enumerate(headings):
            # Start line is after the heading line
            start_line = line_num + 1
            
            # End line is before the next heading, or end of document
            if i + 1 < len(headings):
                end_line = headings[i + 1][0]  # Start of next heading
            else:
                end_line = len(lines)  # End of document
            
            # Extract section text (excluding the heading line itself)
            section_lines = lines[start_line:end_line]
            section_text = "".join(section_lines).strip()
            
            # Only include non-empty sections
            if section_text:
                sections.append((section_text, heading_path, start_line, end_line - 1))
        
        return sections

    def _chunk_section(
        self,
        text: str,
        heading_path: List[str],
        start_line: int,
        end_line: int
    ) -> List[MarkdownChunk]:
        """
        Chunk a section of text into overlapping pieces.

        Args:
            text: The section text to chunk
            heading_path: The hierarchy of headings for this section
            start_line: Starting line number in the original document
            end_line: Ending line number in the original document

        Returns:
            List of MarkdownChunk objects
        """
        if not text.strip():
            return []

        # Simple approach: split by sentences or paragraphs, then group
        # For MVP, we'll use a simple character-based approach with overlap
        
        # Extract wikilinks from the entire section
        wikilinks = self._extract_wikilinks(text)
        
        # If text is small enough, return as single chunk
        estimated_tokens = len(text) // 4
        if estimated_tokens <= self.target_tokens:
            return [MarkdownChunk(
                text=text,
                heading_path=heading_path.copy(),
                wikilinks=wikilinks.copy(),
                start_line=start_line,
                end_line=end_line
            )]
        
        # Otherwise, split into overlapping chunks
        chunks = []
        start = 0
        text_length = len(text)
        
        while start < text_length:
            # Calculate end position for this chunk
            end = start + int(self.target_tokens * 4)  # Approximate chars
            
            # Try to break at a sentence or paragraph boundary
            if end < text_length:
                # Look for a good breaking point (newline or period + space)
                break_point = end
                # Search backwards for a good break point
                for i in range(end, max(start, end - 200), -1):
                    if text[i:i+2] == '\n\n' or (text[i] == '.' and i+1 < text_length and text[i+1] == ' '):
                        break_point = i + 2  # Include the newline or space
                        break
                    elif text[i] == '\n':
                        break_point = i + 1
                        break
                end = break_point
            
            # Extract chunk text
            chunk_text = text[start:end].strip()
            
            if chunk_text:
                # Extract wikilinks in this chunk (approximate)
                chunk_wikilinks = self._extract_wikilinks(chunk_text)
                
                chunk = MarkdownChunk(
                    text=chunk_text,
                    heading_path=heading_path.copy(),
                    wikilinks=chunk_wikilinks.copy(),
                    start_line=start_line,  # Approximate - could be refined
                    end_line=end_line       # Approximate - could be refined
                )
                chunks.append(chunk)
            
            # Move start position for next chunk (with overlap)
            if end >= text_length:
                break
            
            # Calculate overlap
            overlap_chars = int(self.overlap_tokens * 4)
            start = end - overlap_chars
            if start < 0:
                start = 0
        
        return chunks

    def _extract_wikilinks(self, text: str) -> List[str]:
        """Extract all wikilinks ([[link]]) from text."""
        matches = self.wikilink_pattern.findall(text)
        # Remove duplicates while preserving order
        seen = set()
        result = []
        for match in matches:
            if match not in seen:
                seen.add(match)
                result.append(match)
        return result