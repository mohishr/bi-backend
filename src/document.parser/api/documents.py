# document.parser/app/api/documents.py
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/parsed-documents", tags=["Parsed Documents"])


@router.get("/")
def get_all_parsed_documents():
    """
    Return all parsed documents (metadata only).
    """
    # TODO: fetch parsed document metadata from storage
    return [
        {
            "document_id": 1,
            "name": "invoice_001.pdf",
            "parsed_at": "2025-01-01T10:00:00Z"
        },
        {
            "document_id": 2,
            "name": "report_2024.pdf",
            "parsed_at": "2025-01-02T12:30:00Z"
        }
    ]


@router.get("/{document_id}/text")
def get_document_text(document_id: int):
    """
    Return parsed text of a document.
    """
    # TODO: fetch parsed text by document_id
    if document_id <= 0:
        raise HTTPException(status_code=404, detail="Document not found")

    return {
        "document_id": document_id,
        "text": "This is the parsed text content of the document..."
    }
