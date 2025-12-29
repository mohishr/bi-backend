# app/api/documents.py
from fastapi import APIRouter, UploadFile, File, HTTPException

router = APIRouter(prefix="/documents", tags=["Documents"])


@router.post("/")
async def create_document(file: UploadFile = File(...)):
    """
    Create a document and enqueue an event.
    """
    # TODO: persist document
    # TODO: push document_id to event queue
    return {
        "document_id": 1,
        "filename": file.filename,
        "status": "created"
    }


@router.delete("/{document_id}")
def delete_document(document_id: int):
    """
    Delete a document.
    """
    # TODO: delete document from persistence
    return {"deleted": True, "document_id": document_id}
