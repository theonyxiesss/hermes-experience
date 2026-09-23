"""
Knowledge Retrieval MVP - Embedding Utility
"""

import os
from typing import List, Union, Optional
import numpy as np
from sentence_transformers import SentenceTransformer


class Embedder:
    """Handles text embedding using sentence-transformers models."""

    def __init__(self, model_name: Optional[str] = None):
        """
        Initialize the embedder with a sentence-transformers model.

        Args:
            model_name: Name of the sentence-transformers model to use.
                       If None, reads from knowledge config.
        """
        self.model_name = model_name
        self._model: Optional[SentenceTransformer] = None
        self._embedding_dimension: Optional[int] = None

    def _load_model(self) -> SentenceTransformer:
        """Lazy load the sentence-transformers model."""
        if self._model is None:
            if self.model_name is None:
                # Import here to avoid circular dependency
                from knowledge.config import KnowledgeConfig
                config = KnowledgeConfig()
                self.model_name = config.embedding_model
            
            self._model = SentenceTransformer(self.model_name)
            # Get embedding dimension by encoding a test string
            test_embedding = self._model.encode(["test"])
            self._embedding_dimension = test_embedding.shape[1]
        return self._model

    @property
    def embedding_dimension(self) -> int:
        """Get the dimensionality of the embedding vectors."""
        if self._embedding_dimension is None:
            self._load_model()  # This will set _embedding_dimension
        assert self._embedding_dimension is not None
        return self._embedding_dimension

    def embed_texts(self, texts: Union[str, List[str]]) -> np.ndarray:
        """
        Embed one or more texts into vectors.

        Args:
            texts: A single string or a list of strings to embed

        Returns:
            A numpy array of shape (len(texts), embedding_dimension)
        """
        model = self._load_model()
        
        # Ensure we have a list
        if isinstance(texts, str):
            texts = [texts]
        
        # Encode the texts
        embeddings = model.encode(
            texts,
            batch_size=32,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True  # Normalize to unit length for cosine similarity
        )
        
        return embeddings

    def embed_query(self, query: str) -> np.ndarray:
        """
        Embed a single query text.

        Args:
            query: The query string to embed

        Returns:
            A numpy array of shape (1, embedding_dimension)
        """
        return self.embed_texts([query])

    def embed_documents(self, documents: List[str]) -> np.ndarray:
        """
        Embed a list of documents.

        Args:
            documents: List of document strings to embed

        Returns:
            A numpy array of shape (len(documents), embedding_dimension)
        """
        return self.embed_texts(documents)