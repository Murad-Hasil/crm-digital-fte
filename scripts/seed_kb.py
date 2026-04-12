"""
scripts/seed_kb.py
------------------
Seeds the `knowledge_base` table with chunked content from context/product-docs.md.

Embedding model : sentence-transformers all-MiniLM-L6-v2  (384 dims, local, free)
DB column       : embedding VECTOR(384)  — migrated from VECTOR(1536) by this script
Search strategy : cosine similarity via pgvector <=> operator

Usage:
    source venv/bin/activate
    python scripts/seed_kb.py

The script is idempotent: it deletes all existing KB rows then re-inserts,
so it is safe to re-run whenever product-docs.md changes.
"""

from __future__ import annotations

import asyncio
import os
import re
import sys
from pathlib import Path

import asyncpg
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
DOCS_PATH = ROOT / "context" / "product-docs.md"
ENV_PATH = ROOT / ".env"
EMBED_MODEL = "all-MiniLM-L6-v2"
EMBED_DIM = 384          # dimensions produced by all-MiniLM-L6-v2
TARGET_VECTOR_DIM = 384  # what we want in the DB column

# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

def chunk_markdown(text: str) -> list[dict]:
    """
    Split product-docs.md into meaningful chunks.

    Strategy:
    - Split on ## (Part) and ### (section) headers
    - Each chunk = one ### section (or a bare ## section if it has no ### children)
    - Title  = closest ## + ### header combo
    - Content = text under that header (stripped)
    - Category = Part name derived from the nearest ## header
    """
    chunks: list[dict] = []
    current_part = "General"
    current_section: list[str] = []
    current_title = ""

    def flush(title: str, part: str, lines: list[str]) -> None:
        body = "\n".join(lines).strip()
        if body and len(body) > 30:  # skip near-empty sections
            chunks.append({
                "title": title.strip(),
                "content": body,
                "category": part.strip(),
            })

    for line in text.splitlines():
        if line.startswith("## "):
            flush(current_title, current_part, current_section)
            current_part = line.lstrip("# ").strip()
            current_title = current_part
            current_section = []
        elif line.startswith("### "):
            flush(current_title, current_part, current_section)
            current_title = f"{current_part} — {line.lstrip('# ').strip()}"
            current_section = []
        else:
            current_section.append(line)

    flush(current_title, current_part, current_section)  # last section
    return chunks


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

async def ensure_vector_dim(conn: asyncpg.Connection, dim: int) -> None:
    """
    Check the current dimension of knowledge_base.embedding.
    If it differs from `dim`, drop the old index + column and recreate them.
    Safe to call when the table is empty.
    """
    row = await conn.fetchrow(
        """
        SELECT atttypmod
        FROM pg_attribute
        WHERE attrelid = 'knowledge_base'::regclass
          AND attname = 'embedding'
        """
    )
    if row is None:
        print("  [WARN] embedding column not found in knowledge_base — skipping dim check")
        return

    current_dim = row["atttypmod"]  # pgvector stores dim as atttypmod
    if current_dim == dim:
        print(f"  [OK] embedding column already VECTOR({dim})")
        return

    print(f"  [MIGRATE] Changing embedding from VECTOR({current_dim}) → VECTOR({dim})")
    await conn.execute("DROP INDEX IF EXISTS idx_knowledge_embedding")
    await conn.execute("ALTER TABLE knowledge_base DROP COLUMN IF EXISTS embedding")
    await conn.execute(f"ALTER TABLE knowledge_base ADD COLUMN embedding VECTOR({dim})")
    await conn.execute(
        f"""
        CREATE INDEX idx_knowledge_embedding
        ON knowledge_base
        USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 10)
        """
    )
    print(f"  [OK] Column and index recreated at VECTOR({dim})")


async def seed(chunks: list[dict], embeddings: list[list[float]], dsn: str) -> int:
    """Truncate the knowledge_base table and insert all chunks with embeddings."""
    conn = await asyncpg.connect(dsn)
    try:
        await ensure_vector_dim(conn, TARGET_VECTOR_DIM)

        # Wipe existing rows so re-runs are idempotent
        deleted = await conn.fetchval("SELECT count(*) FROM knowledge_base")
        await conn.execute("DELETE FROM knowledge_base")
        print(f"  [DB] Cleared {deleted or 0} existing rows")

        # Register pgvector codec so we can pass a plain list as VECTOR
        await conn.execute("SET search_path = public")

        inserted = 0
        for chunk, vec in zip(chunks, embeddings):
            # pgvector expects the vector as a string '[0.1,0.2,...]' or use the
            # asyncpg json encoder; simplest: pass as a formatted string literal
            vec_str = "[" + ",".join(f"{v:.8f}" for v in vec) + "]"
            await conn.execute(
                """
                INSERT INTO knowledge_base (title, content, category, embedding)
                VALUES ($1, $2, $3, $4::vector)
                """,
                chunk["title"],
                chunk["content"],
                chunk["category"],
                vec_str,
            )
            inserted += 1

        print(f"  [DB] Inserted {inserted} chunks")
        return inserted
    finally:
        await conn.close()


# ---------------------------------------------------------------------------
# Verification query
# ---------------------------------------------------------------------------

async def verify(query: str, dsn: str, model: SentenceTransformer) -> None:
    """Run a sample cosine similarity search and print the top-3 results."""
    q_vec = model.encode(query, normalize_embeddings=True).tolist()
    # Embed the vector literal directly — safe because it's ML-generated, not user input.
    # asyncpg parameter binding with ::vector cast has a known Neon SSL connection quirk.
    vec_literal = "[" + ",".join(f"{v:.8f}" for v in q_vec) + "]"

    sql = f"""
        SELECT title, category,
               1 - (embedding <=> '{vec_literal}'::vector) AS score,
               LEFT(content, 200) AS snippet
        FROM knowledge_base
        ORDER BY embedding <=> '{vec_literal}'::vector
        LIMIT 3
    """
    conn = await asyncpg.connect(dsn)
    try:
        rows = await conn.fetch(sql)
    except Exception as e:
        print(f"  [ERROR in verify] {e}")
        rows = []
    finally:
        await conn.close()

    print(f"\n  Sample query: '{query}'")
    print("  " + "-" * 60)
    for r in rows:
        score_val = float(r['score']) if r['score'] is not None else 0.0
        print(f"  [{score_val:.3f}] {r['title']}  (category: {r['category']})")
        print(f"         {r['snippet'][:120]}...")
        print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:
    load_dotenv(ENV_PATH)
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        sys.exit("ERROR: DATABASE_URL not set in .env")

    # ---- 1. Read and chunk the docs ----------------------------------------
    print(f"\n[1/4] Reading {DOCS_PATH.relative_to(ROOT)} ...")
    raw = DOCS_PATH.read_text(encoding="utf-8")
    chunks = chunk_markdown(raw)
    print(f"      {len(chunks)} chunks extracted")
    for i, c in enumerate(chunks, 1):
        print(f"      {i:2}. [{c['category'][:30]}] {c['title'][:70]}")

    # ---- 2. Generate embeddings ---------------------------------------------
    print(f"\n[2/4] Loading sentence-transformers model: {EMBED_MODEL} ...")
    import warnings, logging as _logging
    warnings.filterwarnings("ignore", category=FutureWarning, module="sentence_transformers")
    _logging.getLogger("sentence_transformers").setLevel(_logging.ERROR)
    _logging.getLogger("transformers").setLevel(_logging.ERROR)
    model = SentenceTransformer(EMBED_MODEL)
    print(f"      Model dim: {model.get_embedding_dimension()}")

    texts = [f"{c['title']}\n\n{c['content']}" for c in chunks]
    print(f"[3/4] Generating {len(texts)} embeddings ...")
    vecs = model.encode(texts, show_progress_bar=True, normalize_embeddings=True)
    print(f"      Done — shape: {vecs.shape}")

    # ---- 3. Upsert into DB --------------------------------------------------
    print("\n[4/4] Seeding database ...")
    count = await seed(chunks, vecs.tolist(), dsn)

    # ---- 4. Verify with sample queries --------------------------------------
    print("\n[VERIFY] Running sample similarity searches ...")
    for q in [
        "How do I launch an H100 GPU instance?",
        "spot instance preemption warning time",
        "AccessDenied error when uploading to bucket",
        "reserved instance pricing discount",
    ]:
        await verify(q, dsn, model)

    print(f"\n✓ Knowledge base seeded with {count} chunks. RAG is live.\n")


if __name__ == "__main__":
    asyncio.run(main())
