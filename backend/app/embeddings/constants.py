"""The function-embedding vector shared by the embedder, schema and search.

The embedding model fixes the vector length, the Neo4j vector index is created
for that length, and semantic search queries that index by name. All three read
these values so a model change cannot leave the index or search behind.
"""

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536
FUNCTION_EMBEDDING_INDEX = "function_embeddings"
