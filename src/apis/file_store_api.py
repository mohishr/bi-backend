from fastapi import APIRouter, UploadFile, File, HTTPException, Query
from fastapi.responses import JSONResponse
from typing import List
from services.file_service import FileService, FileServiceError
from repositories.file_and_meta import sql_file_store

router = APIRouter()

file_service = FileService(sql_file_store)


@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    try:
        data = await file.read()
        result = file_service.upload_file(file.filename, data)
        return JSONResponse(result)
    except FileServiceError as e:
        raise HTTPException(400, str(e))


@router.post("/{file_id}/tags")
def add_tag(file_id: int, tag: str = Query(...)):
    try:
        return file_service.add_tag(file_id, tag)
    except FileServiceError as e:
        raise HTTPException(400, str(e))


@router.delete("/{file_id}/tags")
def remove_tag(file_id: int, tag: str = Query(...)):
    try:
        removed = file_service.remove_tag(file_id, tag)
        return {"removed": removed}
    except FileServiceError as e:
        raise HTTPException(400, str(e))


@router.delete("/{file_id}")
def delete_file(file_id: int):
    try:
        file_service.delete_file(file_id)
        return {"deleted": True}
    except FileServiceError as e:
        raise HTTPException(400, str(e))


@router.get("/recent")
def get_recent_files(limit: int = 10):
    try:
        return file_service.get_most_recent_files(limit)
    except FileServiceError as e:
        raise HTTPException(400, str(e))


@router.get("/{file_id}")
def get_file(file_id: int):
    try:
        return file_service.get_file_with_blob(file_id)
    except FileServiceError as e:
        raise HTTPException(404, str(e))


@router.get("/by-tag")
def get_by_tag(tag: str = Query(...)):
    try:
        return file_service.get_files_with_tag(tag)
    except FileServiceError as e:
        raise HTTPException(400, str(e))


@router.get("/search")
def search(pattern: str = Query(...)):
    try:
        return file_service.get_files_name_contains(pattern)
    except FileServiceError as e:
        raise HTTPException(400, str(e))


@router.get("/date-range")
def by_date(start_date: str = Query(...), end_date: str = Query(...)):
    try:
        return file_service.get_files_by_date_range(start_date, end_date)
    except FileServiceError as e:
        raise HTTPException(400, str(e))
