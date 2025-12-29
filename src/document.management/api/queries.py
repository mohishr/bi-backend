# app/api/queries.py
from fastapi import APIRouter, Query
from typing import List

router = APIRouter(prefix="/documents", tags=["Queries"])


@router.get("/")
def get_all_documents():
    """
    Get all documents (metadata only).
    """
    # TODO: fetch metadata list
    return [
        {"document_id": 1, "name": "file1.pdf", "tags": ["a", "b"]},
        {"document_id": 2, "name": "file2.pdf", "tags": ["b"]}
    ]


@router.get("/{document_id}/file")
def get_document_with_file(document_id: int):
    """
    Get document including file blob.
    """
    # TODO: return metadata + file (base64 or stream)
    return {
        "document_id": document_id,
        "filename": "file.pdf",
        "blob": "BASE64_ENCODED_DATA"
    }


@router.get("/filter/by-tags")
def get_documents_by_tags(tags: List[str] = Query(...)):
    """
    Get documents filtered by multiple tags.
    """
    # TODO: filter documents by tags
    return {
        "tags": tags,
        "documents": [
            {"document_id": 1, "name": "file1.pdf"}
        ]
    }
