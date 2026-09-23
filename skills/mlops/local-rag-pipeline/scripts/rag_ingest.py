#!/usr/bin/env python3
"""
Минимальный RAG-инжест для DATA MIND (Obsidian vault).
Читает .md из МояБазаЗнаний/, чанкует, эмбеддит, кладёт в ChromaDB.
Запуск: python rag_ingest.py
Запрос: python rag_ingest.py "твой вопрос"
"""

import os
import sys
import re
from pathlib import Path
from typing import List, Dict, Any

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

# ─── CONFIG ──────────────────────────────────────────────────────────────
VAULT_ROOT = Path(__file__).parent / "МояБазаЗнаний"
CHROMA_DIR = Path(__file__).parent / ".chroma"
COLLECTION_NAME = "data_mind"
EMBED_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"  # ru+en, быстрый, 384-dim
CHUNK_SIZE = 500      # токенов ~символов/4
CHUNK_OVERLAP = 50
# ─────────────────────────────────────────────────────────────────────────


def split_markdown(text: str) -> List[str]:
    """Грубое чанкование по заголовкам + размеру."""
    # Сначала режем по заголовкам (# ## ###), сохраняя их
    parts = re.split(r'(?=^#{1,3}\s+)', text, flags=re.MULTILINE)
    chunks = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        # Если кусок слишком большой — режем скользящим окном по предложениям
        if len(part) > CHUNK_SIZE * 4:
            sentences = re.split(r'(?<=[.!?])\s+', part)
            cur = ""
            for s in sentences:
                if len(cur) + len(s) > CHUNK_SIZE * 4:
                    chunks.append(cur.strip())
                    cur = s
                else:
                    cur += " " + s
            if cur:
                chunks.append(cur.strip())
        else:
            chunks.append(part)
    return chunks


def iter_vault_files(root: Path) -> List[Path]:
    """Все .md файлы, исключая .obsidian, .git, archives."""
    skip_dirs = {".obsidian", ".git", "archives", ".trash", "inbox"}
    files = []
    for p in root.rglob("*.md"):
        if any(skip in p.parts for skip in skip_dirs):
            continue
        files.append(p)
    return files


def build_chunks() -> List[Dict[str, Any]]:
    """Возвращает список словарей: {id, text, metadata}."""
    model = SentenceTransformer(EMBED_MODEL)
    all_chunks = []
    for md_file in iter_vault_files(VAULT_ROOT):
        rel = md_file.relative_to(VAULT_ROOT)
        text = md_file.read_text(encoding="utf-8")
        # Убираем frontmatter --- ... ---
        text = re.sub(r'^---\n.*?\n---\n', '', text, flags=re.DOTALL)
        for i, chunk in enumerate(split_markdown(text)):
            if len(chunk) < 50:
                continue
            chunk_id = f"{rel.as_posix()}::chunk_{i}"
            all_chunks.append({
                "id": chunk_id,
                "text": chunk,
                "metadata": {
                    "source": rel.as_posix(),
                    "chunk_index": i,
                    "char_len": len(chunk),
                }
            })
    return all_chunks


def ingest():
    print(f"🔍 Сканирую {VAULT_ROOT} …")
    chunks = build_chunks()
    print(f"📄 Найдено чанков: {len(chunks)}")

    if not chunks:
        print("⚠️  Ничего не найдено. Проверь VAULT_ROOT.")
        return

    print(f"🧠 Загружаю эмбеддер: {EMBED_MODEL}")
    model = SentenceTransformer(EMBED_MODEL)

    print(f"💾 Подключаю ChromaDB в {CHROMA_DIR}")
    client = chromadb.PersistentClient(path=str(CHROMA_DIR), settings=Settings(anonymized_telemetry=False))
    coll = client.get_or_create_collection(name=COLLECTION_NAME, metadata={"hnsw:space": "cosine"})

    # Батчим по 100 чанков
    batch_size = 100
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i+batch_size]
        texts = [c["text"] for c in batch]
        ids = [c["id"] for c in batch]
        metas = [c["metadata"] for c in batch]

        print(f"  ➤ Эмбеддинг батча {i//batch_size + 1}/{(len(chunks)-1)//batch_size + 1} ({len(batch)} чанков)…")
        embeddings = model.encode(texts, show_progress_bar=False, normalize_embeddings=True).tolist()

        coll.upsert(ids=ids, documents=texts, embeddings=embeddings, metadatas=metas)

    print(f"✅ Готово. В коллекции '{COLLECTION_NAME}' теперь {coll.count()} векторов.")


def query(question: str, top_k: int = 5):
    print(f"🔎 Ищу: {question}")
    model = SentenceTransformer(EMBED_MODEL)
    client = chromadb.PersistentClient(path=str(CHROMA_DIR), settings=Settings(anonymized_telemetry=False))
    coll = client.get_collection(name=COLLECTION_NAME)

    q_emb = model.encode([question], normalize_embeddings=True).tolist()[0]
    res = coll.query(query_embeddings=[q_emb], n_results=top_k, include=["documents", "metadatas", "distances"])

    print(f"\n📋 Топ-{top_k} результатов:\n")
    for i, (doc, meta, dist) in enumerate(zip(res["documents"][0], res["metadatas"][0], res["distances"][0])):
        score = 1 - dist  # cosine similarity
        src = meta["source"]
        print(f"  {i+1}. [{score:.3f}] {src}")
        print(f"     {doc[:200]}…\n")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        query(" ".join(sys.argv[1:]))
    else:
        ingest()