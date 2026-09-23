"""
Knowledge Retrieval MVP - CLI Command Group
"""

import typer
from typing import Optional
from pathlib import Path
from loguru import logger

from knowledge.config import KnowledgeConfig
from knowledge.indexer.pipeline import IndexingPipeline


app = typer.Typer(name="knowledge", help="Knowledge retrieval and indexing commands.")


@app.command()
def index(
    full: bool = typer.Option(False, "--full", "-f", help="Perform a full reindex of all files"),
    vault: Optional[Path] = typer.Option(None, "--vault", "-v", help="Path to the knowledge vault"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose logging")
):
    """
    Index the knowledge vault.
    
    Examples:
        hermes knowledge index              # Incremental indexing (new/changed files)
        hermes knowledge index --full       # Full reindex of all files
        hermes knowledge index --vault /path/to/vault
    """
    if verbose:
        logger.enable("knowledge")
    else:
        logger.disable("knowledge")  # Disable our internal logs unless verbose
    
    try:
        pipeline = IndexingPipeline(vault_path=vault)
        logger.info("Starting knowledge vault indexing...")
        
        stats = pipeline.index_vault(full_reindex=full)
        
        # Print summary
        print("\n" + "="*50)
        print("KNOWLEDGE VAULT INDEXING COMPLETE")
        print("="*50)
        print(f"Total files processed: {stats['total_files']}")
        print(f"New files: {stats['new_files']}")
        print(f"Modified files: {stats['modified_files']}")
        print(f"Unchanged files: {stats['unchanged_files']}")
        print(f"Errors: {stats['errors']}")
        print(f"Total chunks: {stats['chunk_count']}")
        print(f"Indexed chunks: {stats['indexed_chunk_count']}")
        print(f"Pending chunks: {stats.get('pending_chunks', 0)}")
        print(f"Elapsed time: {stats['elapsed_time']:.2f} seconds")
        print("="*50)
        
        if stats['errors'] > 0:
            logger.warning(f"Indexing completed with {stats['errors']} errors")
            raise typer.Exit(code=1)
        else:
            logger.info("Indexing completed successfully")
            
    except Exception as e:
        logger.error(f"Indexing failed: {e}")
        raise typer.Exit(code=1)


@app.command()
def stats(
    vault: Optional[Path] = typer.Option(None, "--vault", "-v", help="Path to the knowledge vault"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose logging")
):
    """
    Show statistics about the knowledge index.
    
    Examples:
        hermes knowledge stats
        hermes knowledge stats --vault /path/to/vault
    """
    if verbose:
        logger.enable("knowledge")
    else:
        logger.disable("knowledge")
    
    try:
        from knowledge.indexer.metadata_store import MetadataStore
        from knowledge.config import KnowledgeConfig
        
        config = KnowledgeConfig()
        vault_path = vault if vault is not None else config.vault_path
        
        metadata_store = MetadataStore(
            config.index_path / "metadata.sqlite"
        )
        
        stats = metadata_store.get_stats()
        
        print("\n" + "="*40)
        print("KNOWLEDGE INDEX STATISTICS")
        print("="*40)
        print(f"Vault path: {vault_path}")
        print(f"Index path: {config.index_path}")
        print(f"Files indexed: {stats['file_count']}")
        print(f"Total chunks: {stats['chunk_count']}")
        print(f"Indexed chunks: {stats['indexed_chunk_count']}")
        print(f"Pending chunks (awaiting embedding): {stats['pending_chunks']}")
        print("="*40)
        
    except Exception as e:
        logger.error(f"Failed to get stats: {e}")
        raise typer.Exit(code=1)


@app.command()
def test(
    query: str = typer.Argument(..., help="Query to test the knowledge retrieval"),
    limit: int = typer.Option(5, "--limit", "-l", help="Maximum number of results to return"),
    vault: Optional[Path] = typer.Option(None, "--vault", "-v", help="Path to the knowledge vault"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose logging")
):
    """
    Test knowledge retrieval with a sample query.
    
    Examples:
        hermes knowledge test "Какой у меня статус проекта zarabotok?"
        hermes knowledge test "finance" --limit 10
    """
    if verbose:
        logger.enable("knowledge")
    else:
        logger.disable("knowledge")
    
    try:
        from knowledge.retriever.hybrid import HybridRetriever
        from knowledge.assembler.context_builder import ContextBuilder
        from knowledge.assembler.provenance_formatter import ProvenanceFormatter
        
        # Initialize retriever
        retriever = HybridRetriever(vault_path=vault)
        context_builder = ContextBuilder()
        provenance_formatter = ProvenanceFormatter()
        
        logger.info(f"Testing knowledge retrieval for query: '{query}'")
        
        # Perform search
        chunks = retriever.search(query, limit=limit)
        
        if not chunks:
            print("No results found.")
            return
        
        # Build context
        context_result = context_builder.build_context(chunks, query=query)
        
        # Format sources
        sources_block = provenance_formatter.format_sources_block(context_result.chunks)
        
        # Display results
        print("\n" + "="*60)
        print(f"QUERY: {query}")
        print("="*60)
        print(f"Found {len(chunks)} total results, using {len(context_result.chunks)} in context")
        print(f"Context tokens: {context_result.total_tokens}")
        if context_result.warning:
            print(f"Warning: {context_result.warning}")
        print("-"*60)
        print("RESULTS:")
        print("-"*60)
        
        for i, chunk in enumerate(context_result.chunks, 1):
            print(f"{i}. [{chunk.provenance.retrieval_method.value.upper()}] "
                  f"[{chunk.provenance.confidence.value.upper()}] "
                  f"Score: {chunk.provenance.relevance_score:.3f}")
            print(f"   Document: {chunk.provenance.document}")
            print(f"   Section: {chunk.provenance.section}")
            print(f"   Text: {chunk.text[:200]}{'...' if len(chunk.text) > 200 else ''}")
            print()
        
        print("-"*60)
        print("SOURCES:")
        print("-"*60)
        print(sources_block)
        print("="*60)
        
    except Exception as e:
        logger.error(f"Test failed: {e}")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()