# app/api/events.py
from fastapi import APIRouter

router = APIRouter(prefix="/events", tags=["Event Queue"])


@router.get("/next")
def get_next_event():
    """
    Listener fetches next document event.
    """
    # TODO: peek or dequeue from event queue
    return {
        "event_id": "evt-123",
        "document_id": 1,
        "type": "DOCUMENT_UPLOADED"
    }


@router.post("/{event_id}/ack")
def acknowledge_event(event_id: str):
    """
    Acknowledge event and remove from queue.
    """
    # TODO: remove event from queue
    return {"event_id": event_id, "acknowledged": True}
