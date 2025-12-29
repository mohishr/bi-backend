# app/api/tags.py
from fastapi import APIRouter, Query

router = APIRouter(prefix="/documents/{document_id}/tags", tags=["Tags"])


@router.post("/")
def add_tag(document_id: int, tag: str = Query(...)):
    """
    Add a tag to a document.
    """
    # TODO: attach tag to document
    return {"document_id": document_id, "tag": tag, "added": True}


@router.delete("/")
def remove_tag(document_id: int, tag: str = Query(...)):
    """
    Remove a tag from a document.
    """
    # TODO: remove tag from document
    return {"document_id": document_id, "tag": tag, "removed": True}
