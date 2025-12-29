# app/main.py
from fastapi import FastAPI
from api import documents, tags, queries, events

app = FastAPI(title="Document Management API")

app.include_router(documents.router)
app.include_router(tags.router)
app.include_router(queries.router)
app.include_router(events.router)
