#!/usr/bin/env python3
"""
Knowledge Search — Hermes integration entry point.

Usage: python knowledge_search.py <query> [--limit N] [--vault PATH]

Returns structured results with provenance as JSON for Hermes to consume.
"""

import sys, os, json, time, pathlib

# Ensure we can import the knowledge module
_script_dir = pathlib.Path(__file__).resolve().parent
_profile_dir = _script_dir.parent
sys.path.insert(0, str(_profile_dir))

# Read .env
_env_path = _profile_dir / ".env"
if _env_path.exists():
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if "=" in _line and not _line.startswith("#"):
                _k, _v = _line.split("=", 1)
                _v = _v.strip().strip("\"").strip("'")
                os.environ[_k.strip()] = _v

# Fix paths for Windows
if "WIKI_PATH" in os.environ:
    _p = os.environ["WIKI_PATH"]
    _p = _p.replace("/c/", "C:/").replace("/d/", "D:/")
    _p = _p.replace("\\", "/")
    os.environ["WIKI_PATH"] = _p
    os.environ["OBSIDIAN_VAULT_PATH"] = _p
if "HERMES_HOME" not in os.environ:
    os.environ["HERMES_HOME"] = str(_profile_dir)


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: python knowledge_search.py <query> [--limit N]"}))
        sys.exit(1)
    
    query = sys.argv[1]
    limit = 5
    if "--limit" in sys.argv:
        idx = sys.argv.index("--limit")
        if idx + 1 < len(sys.argv):
            limit = int(sys.argv[idx + 1])
    
    try:
        from knowledge.retriever.hybrid import HybridRetriever
        from knowledge.assembler.context_builder import ContextBuilder
        from knowledge.assembler.provenance_formatter import ProvenanceFormatter
        
        t0 = time.time()
        retriever = HybridRetriever()
        load_time = time.time() - t0
        
        # Check if index exists
        if not (retriever.vector_retriever.faiss_index_path.exists()):
            # Index doesn't exist yet — build it
            print(json.dumps({"warning": "Index not found, building now...", "load_time_ms": round(load_time * 1000)}), file=sys.stderr)
            from knowledge.indexer.pipeline import IndexingPipeline
            t0 = time.time()
            pipe = IndexingPipeline()
            stats = pipe.index_vault(full_reindex=False)
            build_time = time.time() - t0
            print(json.dumps({"info": f"Index built: {stats.get('chunk_count', 0)} chunks", "build_time_ms": round(build_time * 1000)}), file=sys.stderr)
        
        t0 = time.time()
        results = retriever.search(query, limit=limit)
        search_time = time.time() - t0
        
        # Build context
        builder = ContextBuilder()
        context = builder.build_context(results, query=query)
        
        # Format provenance
        formatter = ProvenanceFormatter()
        sources_block = formatter.format_sources_block(context.chunks)
        
        # Format output as JSON
        output = {
            "query": query,
            "result_count": len(results),
            "context_chunks": len(context.chunks),
            "context_tokens": context.total_tokens,
            "search_time_ms": round(search_time * 1000),
            "load_time_ms": round(load_time * 1000),
            "sources": sources_block,
            "results": [],
            "warning": context.warning
        }
        
        for chunk in context.chunks:
            p = chunk.provenance
            output["results"].append({
                "document": p.document,
                "section": p.section,
                "confidence": p.confidence.value if hasattr(p.confidence, 'value') else str(p.confidence),
                "method": p.retrieval_method.value if hasattr(p.retrieval_method, 'value') else str(p.retrieval_method),
                "relevance": round(p.relevance_score, 4),
                "timestamp": str(p.timestamp),
                "text": chunk.text[:500]
            })
        
        print(json.dumps(output, ensure_ascii=False, indent=2))
        
    except ImportError as e:
        print(json.dumps({"error": f"ImportError: {e}", "hint": "Run 'pip install sentence-transformers faiss-cpu'"}))
        sys.exit(1)
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)


if __name__ == "__main__":
    main()
