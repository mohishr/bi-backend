from fastapi import APIRouter, UploadFile, File, HTTPException, Query
from fastapi.responses import JSONResponse
from typing import List
from services.file_service import FileServiceError, file_service, QueueFullError
import base64
from fastapi import APIRouter, HTTPException

router = APIRouter()


##Upload
@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    try:
        data = await file.read()
        result = file_service.upload_file(file.filename, data)
        return JSONResponse(result)
    except QueueFullError as e:
        # Client should retry later
        raise HTTPException(status_code=429, detail=str(e))
    except FileServiceError as e:
        raise HTTPException(400, str(e))

#Add tag
@router.post("/{file_id}/tags")
def add_tag(file_id: int, tag: str = Query(...)):
    try:
        return file_service.add_tag(file_id, tag)
    except FileServiceError as e:
        raise HTTPException(400, str(e))

#Delete tag
@router.delete("/{file_id}/tags")
def remove_tag(file_id: int, tag: str = Query(...)):
    try:
        removed = file_service.remove_tag(file_id, tag)
        return {"removed": removed}
    except FileServiceError as e:
        raise HTTPException(400, str(e))

#Delete file
@router.delete("/{file_id}")
def delete_file(file_id: int):
    try:
        file_service.delete_file(file_id)
        return {"deleted": True}
    except FileServiceError as e:
        raise HTTPException(400, str(e))

#Get files
@router.get("/recent")
def get_recent_files(limit: int = 10):
    try:
        return file_service.get_most_recent_files(limit)
    except FileServiceError as e:
        raise HTTPException(400, str(e))


# Get all tags (unique list)
@router.get("/tags")
def get_all_tags():
    try:
        return file_service.get_all_tags()
    except FileServiceError as e:
        raise HTTPException(400, str(e))


# Parsing status for a file
@router.get("/{file_id}/parsing-status")
def get_parsing_status(file_id: int):
    try:
        state = file_service.get_parsing_state(file_id)
        return {"file_id": file_id, "parsing_state": state}
    except FileServiceError as e:
        raise HTTPException(404, str(e))
#Get file
@router.get("/{file_id}")
def get_file_with_meta(file_id: int):
    try:
        data = file_service.get_file_with_blob(file_id)

        # Convert bytes → base64 string
        if data.get("blob"):
            data["blob"] = base64.b64encode(data["blob"]).decode("utf-8")

        return data

    except FileServiceError as e:
        raise HTTPException(404, str(e))
@router.get("/file_text/{file_id}")
def get_file_text_and_meta(file_id: int):
    try:
        data = file_service.get_file_with_blob(file_id)

        # Convert bytes → base64 string
        if data.get("blob"):
            data["blob"] = base64.b64encode(data["blob"]).decode("utf-8")

        return data

    except FileServiceError as e:
        raise HTTPException(404, str(e))


# @router.get("/by-tag")
# def get_by_tag(tag: str = Query(...)):
#     try:
#         return file_service.get_files_with_tag(tag)
#     except FileServiceError as e:
#         raise HTTPException(400, str(e))


# @router.get("/search")
# def search(pattern: str = Query(...)):
#     try:
#         return file_service.get_files_name_contains(pattern)
#     except FileServiceError as e:
#         raise HTTPException(400, str(e))


# @router.get("/date-range")
# def by_date(start_date: str = Query(...), end_date: str = Query(...)):
#     try:
#         return file_service.get_files_by_date_range(start_date, end_date)
#     except FileServiceError as e:
#         raise HTTPException(400, str(e))
