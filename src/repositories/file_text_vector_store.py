"""
Qdrant-based vector store for storing and retrieving file text with hybrid search.
Supports both dense embeddings (semantic meaning) and sparse vectors (IDF-based keyword matching).

Text is stored in MySQL (SQL database) and indexed in Qdrant for semantic/keyword search.

Models used:
- Dense: "sentence-transformers/all-MiniLM-L6-v2" (384 dims, fast, high quality)
- Sparse: "prithivida/Splade_PP_en_v1" (IDF + learned term importance)

Collection schema:
- Dense vectors: 384-dim COSINE distance (semantic similarity)
- Sparse vectors: BM25-like IDF scoring (keyword matching)
- Payload: filename, page_number, file_id, text snippet (for context)
- Full text: stored in MySQL file_text table
"""

import os
import uuid
from typing import Optional, Dict, List, Any
from qdrant_client import QdrantClient, models
from qdrant_client.models import Distance, VectorParams, SparseVectorParams
from utilities.logger import setup_logger

logger = setup_logger(__name__)

# Embedding models - using latest recommended models
DENSE_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"  # 384 dims, semantic
SPARSE_MODEL_NAME = "prithivida/Splade_PP_en_v1"  # IDF + learned term weights
COLLECTION_NAME = "documents"

# Dense vector config (384 dims for all-MiniLM-L6-v2)
DENSE_VECTOR_NAME = "dense"
DENSE_VECTOR_SIZE = 384
DENSE_DISTANCE = Distance.COSINE

# Sparse vector config (no fixed size, uses terms as indices)
SPARSE_VECTOR_NAME = "sparse"

# Qdrant configuration from environment
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", None)

# FastEmbed cache path - use temp directory to avoid permission issues on Windows
FASTEMBED_CACHE_PATH = os.getenv(
    "FASTEMBED_CACHE_PATH",
    os.path.expanduser("~/.cache/fastembed")
)
os.environ["FASTEMBED_CACHE_PATH"] = FASTEMBED_CACHE_PATH


class VectorStoreError(Exception):
    """Exception raised for vector store operations."""
    pass


class QdrantVectorStore:
    """
    Hybrid vector store using Qdrant with dense and sparse embeddings.
    
    Dense embeddings capture semantic meaning (similarity search).
    Sparse embeddings capture keyword/IDF importance (exact term matching).
    """

    # Class-level model caches to avoid reloading on every call
    _dense_model = None
    _sparse_model = None

    def __init__(self, url: Optional[str] = None, api_key: Optional[str] = None):
        """
        Initialize Qdrant client and ensure collection exists.
        
        Args:
            url: Qdrant server URL (defaults to QDRANT_URL env var or http://localhost:6333)
            api_key: Optional API key (defaults to QDRANT_API_KEY env var)
        """
        qdrant_url = url or QDRANT_URL
        qdrant_key = api_key or QDRANT_API_KEY
        
        try:
            self.client = QdrantClient(url=qdrant_url, api_key=qdrant_key)
            logger.info(f"Connected to Qdrant at {qdrant_url}")
        except Exception as e:
            logger.error(f"Failed to connect to Qdrant: {e}")
            raise VectorStoreError(f"Qdrant connection failed: {e}")

        self._ensure_collection_exists()

    def _ensure_collection_exists(self) -> None:
        """Create collection if it doesn't exist with proper schema."""
        try:
            if self.client.collection_exists(COLLECTION_NAME):
                logger.info(f"Collection '{COLLECTION_NAME}' already exists")
                return

            logger.info(f"Creating collection '{COLLECTION_NAME}' with dense and sparse vectors...")
            
            self.client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config={
                    DENSE_VECTOR_NAME: VectorParams(
                        size=DENSE_VECTOR_SIZE,
                        distance=DENSE_DISTANCE,
                    )
                },
                sparse_vectors_config={
                    SPARSE_VECTOR_NAME: SparseVectorParams()
                },
            )
            logger.info(f"Collection '{COLLECTION_NAME}' created successfully")
        except Exception as e:
            logger.error(f"Failed to ensure collection exists: {e}")
            raise VectorStoreError(f"Collection creation failed: {e}")

    def _generate_text_id(self, file_id: int, page_number: int) -> str:
        """Generate a unique ID for a document chunk (file_id + page_number)."""
        return f"file_{file_id}_page_{page_number}"

    def _encode_dense_vector(self, text: str) -> List[float]:
        """
        Encode text to dense vector using FastEmbed.
        Uses sentence-transformers/all-MiniLM-L6-v2 model.
        Caches model at class level to avoid reloading.
        """
        try:
            from fastembed import TextEmbedding

            # Lazy load and cache model (cached after first use)
            if QdrantVectorStore._dense_model is None:
                logger.info(f"Loading dense embedding model: {DENSE_MODEL_NAME}")
                QdrantVectorStore._dense_model = TextEmbedding(model_name=DENSE_MODEL_NAME)
                logger.info("Dense embedding model loaded successfully")
            
            embeddings = list(QdrantVectorStore._dense_model.embed([text]))
            
            if not embeddings or len(embeddings) == 0:
                raise VectorStoreError(f"Failed to encode dense vector for text")
            
            # Convert numpy array to list
            dense_vector = embeddings[0].tolist() if hasattr(embeddings[0], 'tolist') else list(embeddings[0])
            
            if len(dense_vector) != DENSE_VECTOR_SIZE:
                raise VectorStoreError(
                    f"Dense vector size mismatch: got {len(dense_vector)}, expected {DENSE_VECTOR_SIZE}"
                )
            
            return dense_vector
        except ImportError:
            logger.error("FastEmbed not installed. Install with: pip install fastembed")
            raise VectorStoreError("FastEmbed library not available")
        except Exception as e:
            logger.error(f"Error encoding dense vector: {e}")
            raise

    def _encode_sparse_vector(self, text: str) -> models.SparseVector:
        """
        Encode text to sparse vector using SPLADE model.
        Returns BM25-like sparse representation with term importance weights.
        Caches model at class level to avoid reloading.
        """
        try:
            from fastembed import SparseTextEmbedding

            # Lazy load and cache sparse model (cached after first use)
            if QdrantVectorStore._sparse_model is None:
                logger.info(f"Loading sparse embedding model: {SPARSE_MODEL_NAME}")
                QdrantVectorStore._sparse_model = SparseTextEmbedding(model_name=SPARSE_MODEL_NAME)
                logger.info("Sparse embedding model loaded successfully")
            
            sparse_embeddings = list(QdrantVectorStore._sparse_model.embed([text]))
            
            if not sparse_embeddings or len(sparse_embeddings) == 0:
                raise VectorStoreError("Failed to encode sparse vector for text")
            
            # sparse_embeddings[0] is a dict-like object {index: weight, ...}
            sparse_embedding = sparse_embeddings[0]
            
            # Convert to Qdrant SparseVector format {indices: [...], values: [...]}
            if isinstance(sparse_embedding, dict):
                indices = list(sparse_embedding.keys())
                values = list(sparse_embedding.values())
            else:
                # Handle if it returns a SparseVector-like object
                indices = sparse_embedding.indices
                values = sparse_embedding.values
            
            return models.SparseVector(indices=indices, values=values)
        except ImportError:
            logger.error("FastEmbed not installed. Install with: pip install fastembed")
            raise VectorStoreError("FastEmbed library not available")
        except Exception as e:
            logger.error(f"Error encoding sparse vector: {e}")
            raise

    def store_page_text(
        self,
        file_id: int,
        page_number: int,
        text: str,
        filename: str,
    ) -> bool:
        """
        Store parsed page text with both dense and sparse embeddings.
        
        Args:
            file_id: ID of the file in database
            page_number: Page number in the file
            text: Extracted text content
            filename: Original filename for context
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if not text or not isinstance(text, str):
                logger.warning(f"Invalid text for file {file_id}, page {page_number}")
                return False

            # Truncate text if too long (Qdrant payloads have size limits)
            # Store full text in MongoDB, only snippet in Qdrant payload
            text_snippet = text[:500] if len(text) > 500 else text

            logger.info(f"Encoding vectors for file {file_id}, page {page_number}...")

            # Encode both dense and sparse vectors
            dense_vector = self._encode_dense_vector(text)
            sparse_vector = self._encode_sparse_vector(text)

            # Prepare point with hybrid vectors and payload
            point_id = int(uuid.uuid4().int % (2**63))  # Qdrant expects uint64
            
            payload = {
                "file_id": file_id,
                "page_number": page_number,
                "filename": filename,
                "text_snippet": text_snippet,
            }

            point = models.PointStruct(
                id=point_id,
                vector={
                    DENSE_VECTOR_NAME: dense_vector,
                    SPARSE_VECTOR_NAME: sparse_vector,
                },
                payload=payload,
            )

            # Upsert point (insert or update if exists)
            logger.info(f"Upserting point for file {file_id}, page {page_number}...")
            self.client.upsert(
                collection_name=COLLECTION_NAME,
                points=[point],
            )

            logger.info(f"Successfully stored vectors for file {file_id}, page {page_number}")
            return True

        except VectorStoreError as e:
            logger.error(f"Vector store error for file {file_id}, page {page_number}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error storing vectors for file {file_id}, page {page_number}: {e}")
            return False

    def search_semantic(
        self,
        query: str,
        limit: int = 10,
        score_threshold: Optional[float] = 0.5,
    ) -> List[Dict[str, Any]]:
        """
        Search using dense vectors (semantic similarity).
        
        Args:
            query: Search query text
            limit: Maximum results
            score_threshold: Minimum similarity score (0-1)
            
        Returns:
            List of matching documents with metadata
        """
        try:
            from qdrant_client.models import NearestQuery
            
            query_vector = self._encode_dense_vector(query)
            
            results = self.client.query_points(
                collection_name=COLLECTION_NAME,
                query=NearestQuery(
                    nearest=query_vector,
                ),
                using=DENSE_VECTOR_NAME,
                limit=limit,
            )

            return [
                {
                    "file_id": hit.payload.get("file_id"),
                    "page_number": hit.payload.get("page_number"),
                    "filename": hit.payload.get("filename"),
                    "text_snippet": hit.payload.get("text_snippet"),
                    "score": hit.score,
                    "search_type": "semantic",
                }
                for hit in results.points
            ]
        except Exception as e:
            logger.error(f"Error in semantic search: {e}")
            return []

    def search_keyword(
        self,
        query: str,
        limit: int = 10,
        score_threshold: Optional[float] = 0.1,
    ) -> List[Dict[str, Any]]:
        """
        Search using sparse vectors (keyword/IDF-based).
        
        Args:
            query: Search query text
            limit: Maximum results
            score_threshold: Minimum relevance score
            
        Returns:
            List of matching documents with metadata
        """
        try:
            from qdrant_client.models import NearestQuery
            
            query_sparse = self._encode_sparse_vector(query)
            
            results = self.client.query_points(
                collection_name=COLLECTION_NAME,
                query=NearestQuery(
                    nearest=query_sparse,
                ),
                using=SPARSE_VECTOR_NAME,
                limit=limit,
            )

            return [
                {
                    "file_id": hit.payload.get("file_id"),
                    "page_number": hit.payload.get("page_number"),
                    "filename": hit.payload.get("filename"),
                    "text_snippet": hit.payload.get("text_snippet"),
                    "score": hit.score,
                    "search_type": "keyword",
                }
                for hit in results.points
            ]
        except Exception as e:
            logger.error(f"Error in keyword search: {e}")
            return []

    def search_hybrid(
        self,
        query: str,
        limit: int = 10,
        semantic_weight: float = 0.7,
        keyword_weight: float = 0.3,
    ) -> List[Dict[str, Any]]:
        """
        Hybrid search combining semantic and keyword results.
        
        Args:
            query: Search query
            limit: Maximum results
            semantic_weight: Weight for semantic search (0-1)
            keyword_weight: Weight for keyword search (0-1)
            
        Returns:
            Merged and re-ranked results
        """
        try:
            # Normalize weights
            total = semantic_weight + keyword_weight
            sem_w = semantic_weight / total if total > 0 else 0.5
            kw_w = keyword_weight / total if total > 0 else 0.5

            # Perform both searches
            semantic_results = self.search_semantic(query, limit=limit * 2)
            keyword_results = self.search_keyword(query, limit=limit * 2)

            # Merge results by (file_id, page_number) and combine scores
            merged = {}
            for result in semantic_results:
                key = (result["file_id"], result["page_number"])
                if key not in merged:
                    merged[key] = result.copy()
                    merged[key]["combined_score"] = result["score"] * sem_w
                else:
                    merged[key]["combined_score"] += result["score"] * sem_w

            for result in keyword_results:
                key = (result["file_id"], result["page_number"])
                if key not in merged:
                    merged[key] = result.copy()
                    merged[key]["combined_score"] = result["score"] * kw_w
                else:
                    merged[key]["combined_score"] += result["score"] * kw_w

            # Sort by combined score
            sorted_results = sorted(
                merged.values(),
                key=lambda x: x.get("combined_score", 0),
                reverse=True,
            )

            return sorted_results[:limit]
        except Exception as e:
            logger.error(f"Error in hybrid search: {e}")
            return []

    def delete_file_vectors(self, file_id: int) -> bool:
        """
        Delete all vectors associated with a file.
        
        Args:
            file_id: ID of the file
            
        Returns:
            True if successful
        """
        try:
            self.client.delete(
                collection_name=COLLECTION_NAME,
                points_selector=models.FilterSelector(
                    filter=models.Filter(
                        must=[
                            models.HasIdCondition(
                                has_id=[
                                    int(uuid.uuid5(uuid.NAMESPACE_DNS, f"file_{file_id}_page_*").int % (2**63))
                                ]
                            )
                        ]
                    )
                ),
            )
            logger.info(f"Deleted vectors for file {file_id}")
            return True
        except Exception as e:
            logger.error(f"Error deleting vectors for file {file_id}: {e}")
            # Use fallback: filter by file_id in payload
            try:
                self.client.delete(
                    collection_name=COLLECTION_NAME,
                    points_selector=models.FilterSelector(
                        filter=models.Filter(
                            must=[
                                models.FieldCondition(
                                    key="file_id",
                                    match=models.MatchValue(value=file_id),
                                )
                            ]
                        )
                    ),
                )
                logger.info(f"Deleted vectors for file {file_id} (fallback filter)")
                return True
            except Exception as e2:
                logger.error(f"Fallback delete also failed: {e2}")
                return False

    def get_file_vectors_count(self, file_id: int) -> int:
        """Get count of vectors stored for a file."""
        try:
            result = self.client.count(
                collection_name=COLLECTION_NAME,
                count_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="file_id",
                            match=models.MatchValue(value=file_id),
                        )
                    ]
                ),
            )
            return result.count
        except Exception as e:
            logger.error(f"Error counting vectors for file {file_id}: {e}")
            return 0


# Global vector store instance (uses env vars for configuration)
try:
    vector_store = QdrantVectorStore()
except VectorStoreError as e:
    logger.warning(f"Vector store initialization deferred: {e}")
    vector_store = None
