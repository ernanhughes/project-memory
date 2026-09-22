"""Strong conventional RAG baseline for the Memory book (Chapter 3).

Ordinary retrieval engineering only: ingestion, chunking, embeddings,
PostgreSQL full-text search, pgvector dense search, reciprocal rank
fusion, cross-encoder reranking, bounded context assembly, and a
capable reader with citations. No relation inference, no event
ontology, no belief state, no consolidation, no learned memory policy.
"""

__version__ = "0.1.0"
