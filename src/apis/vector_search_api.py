"""
Vector search API endpoints for semantic and keyword search.
"""

from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import JSONResponse
from typing import Optional, List, Dict, Any
from repositories.file_text_vector_store import vector_store, VectorStoreError
from utilities.logger import setup_logger

logger = setup_logger(__name__)

router = APIRouter()


@router.get("/semantic")
async def search_semantic(
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(10, ge=1, le=100, description="Max results"),
    threshold: Optional[float] = Query(0.5, ge=0.0, le=1.0, description="Min similarity score"),
):
    """
    Semantic search using dense embeddings (sentence-transformers/all-MiniLM-L6-v2).
    Returns documents sorted by semantic similarity.
    """
    if not vector_store:
        raise HTTPException(status_code=503, detail="Vector store not available")
    
    try:
        results = vector_store.search_semantic(
            query=q,
            limit=limit,
            score_threshold=threshold,
        )
        return JSONResponse({
            "query": q,
            "search_type": "semantic",
            "count": len(results),
            "results": results,
        })
    except Exception as e:
        logger.error(f"Semantic search error: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/keyword")
async def search_keyword(
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(10, ge=1, le=100, description="Max results"),
    threshold: Optional[float] = Query(0.1, ge=0.0, le=1.0, description="Min relevance score"),
):
    """
    Keyword search using sparse embeddings (SPLADE_PP_en_v1 for IDF-based matching).
    Returns documents sorted by term importance.
    """
    if not vector_store:
        raise HTTPException(status_code=503, detail="Vector store not available")
    
    try:
        results = vector_store.search_keyword(
            query=q,
            limit=limit,
            score_threshold=threshold,
        )
        return JSONResponse({
            "query": q,
            "search_type": "keyword",
            "count": len(results),
            "results": results,
        })
    except Exception as e:
        logger.error(f"Keyword search error: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/hybrid")
async def search_hybrid(
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(10, ge=1, le=100, description="Max results"),
    semantic_weight: float = Query(0.7, ge=0.0, le=1.0, description="Weight for semantic results"),
    keyword_weight: float = Query(0.3, ge=0.0, le=1.0, description="Weight for keyword results"),
):
    """
    Hybrid search combining semantic (dense) and keyword (sparse) results.
    Results are re-ranked by weighted combined score.
    
    Default weights: 70% semantic, 30% keyword (adjust for your use case).
    """
    if not vector_store:
        raise HTTPException(status_code=503, detail="Vector store not available")
    
    try:
        results = vector_store.search_hybrid(
            query=q,
            limit=limit,
            semantic_weight=semantic_weight,
            keyword_weight=keyword_weight,
        )
        return JSONResponse({
            "query": q,
            "search_type": "hybrid",
            "semantic_weight": semantic_weight,
            "keyword_weight": keyword_weight,
            "count": len(results),
            "results": results,
        })
    except Exception as e:
        logger.error(f"Hybrid search error: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/files/{file_id}/vector-count")
async def get_vector_count(file_id: int):
    """
    Get the number of vectors stored for a specific file.
    Useful for checking if vectorization completed.
    """
    if not vector_store:
        raise HTTPException(status_code=503, detail="Vector store not available")
    
    try:
        count = vector_store.get_file_vectors_count(file_id)
        return JSONResponse({
            "file_id": file_id,
            "vector_count": count,
        })
    except Exception as e:
        logger.error(f"Error getting vector count: {e}")
        raise HTTPException(status_code=400, detail=str(e))
