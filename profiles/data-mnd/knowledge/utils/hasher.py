"""
Knowledge Retrieval MVP - Hashing Utility
"""

import hashlib
from pathlib import Path
from typing import Union


def file_hash(file_path: Union[str, Path]) -> str:
    """
    Compute the SHA256 hash of a file's contents.

    Args:
        file_path: Path to the file

    Returns:
        Hexadecimal SHA256 hash string

    Raises:
        FileNotFoundError: If the file does not exist
        IOError: If the file cannot be read
    """
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"File not found: {file_path}")

    sha256_hash = hashlib.sha256()
    # Read in chunks to handle large files efficiently
    with path.open("rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def string_hash(text: str) -> str:
    """
    Compute the SHA256 hash of a string.

    Args:
        text: The string to hash

    Returns:
        Hexadecimal SHA256 hash string
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def content_hash(content: Union[str, bytes]) -> str:
    """
    Compute the SHA256 hash of content (string or bytes).

    Args:
        content: String or bytes to hash

    Returns:
        Hexadecimal SHA256 hash string
    """
    if isinstance(content, str):
        content = content.encode("utf-8")
    elif not isinstance(content, bytes):
        raise TypeError("Content must be string or bytes")
    return hashlib.sha256(content).hexdigest()