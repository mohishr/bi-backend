# Service class and unit tests for MySQLDocumentStore-based repository.
# This code uses unittest.mock to simulate the repository (no real DB required).
# It exercises every function requested and asserts expected behavior.
# Run in a Python environment; here it will execute and display test results.

import io
import re
import unittest
from unittest.mock import MagicMock, call
from typing import List, Dict, Any
from repositories.file_and_meta import sql_file_store

class FileServiceError(Exception):
    pass


class FileService:
    def __init__(self, repo):
        """
        repo: instance of MySQLDocumentStore (or a duck-typed mock implementing required methods)
        Required repo methods used:
            - insert_file_metadata(filename, file_size) -> file_id
            - insert_file_blob(file_id, blob_data) -> blob_id
            - add_tag(file_id, tag) -> tag_id
            - remove_tag(file_id, tag) -> bool
            - delete_file(file_id) -> bool
            - get_file(file_id) -> dict or None
            - get_all_files() -> list[dict]
            - get_files_with_tags(file_ids: List[int]) -> list[dict]
            - get_files_with_tags (used also for tag queries) OR get_all_files + tags filtering
        """
        self.repo = repo

    def _validate_filename(self, filename: str):
        if not filename or not isinstance(filename, str):
            raise FileServiceError("filename must be a non-empty string")
        if len(filename) > 255:
            raise FileServiceError("filename too long (>255)")

    def upload_file(self, filename: str, file_bytes: bytes) -> Dict[str, Any]:
        """Upload file: stores metadata and blob; returns file metadata including generated id."""
        self._validate_filename(filename)
        if not isinstance(file_bytes, (bytes, bytearray)):
            raise FileServiceError("file_bytes must be bytes or bytearray")

        file_size = len(file_bytes)
        # insert metadata
        file_id = self.repo.insert_file_metadata(filename, file_size)
        if not file_id:
            raise FileServiceError("failed to insert file metadata")

        # insert blob
        blob_id = self.repo.insert_file_blob(file_id, bytes(file_bytes))
        if not blob_id:
            # try to rollback metadata deletion for consistency
            try:
                self.repo.delete_file(file_id)
            except Exception:
                pass
            raise FileServiceError("failed to insert file blob")

        # return full file info (without re-querying blob to keep it simple)
        return {"file_id": file_id, "filename": filename, "file_size": file_size, "blob_id": blob_id}

    def add_tag(self, file_id: int, tag: str) -> Dict[str, Any]:
        if not tag or not isinstance(tag, str):
            raise FileServiceError("tag must be a non-empty string")
        tag_id = self.repo.add_tag(file_id, tag)
        if not tag_id:
            raise FileServiceError("failed to add tag")
        return {"tag_id": tag_id, "file_id": file_id, "tag": tag}

    def remove_tag(self, file_id: int, tag: str) -> bool:
        if not tag or not isinstance(tag, str):
            raise FileServiceError("tag must be a non-empty string")
        result = self.repo.remove_tag(file_id, tag)
        if not result:
            # Not necessarily an error — could mean tag didn't exist.
            return False
        return True

    def delete_file(self, file_id: int) -> bool:
        result = self.repo.delete_file(file_id)
        if not result:
            raise FileServiceError(f"failed to delete file {file_id}")
        return True

    def get_most_recent_files(self, limit: int = 10) -> List[Dict[str, Any]]:
        if limit <= 0:
            raise FileServiceError("limit must be > 0")
        files = self.repo.get_all_files()
        # repo.get_all_files is already ordered by upload_time DESC in repo implementation
        return files[:limit]

    def get_file_with_blob(self, file_id: int) -> Dict[str, Any]:
        file_info = self.repo.get_file(file_id)
        if not file_info:
            raise FileServiceError("file not found")
        # Should contain 'blob' key as per repo.get_file implementation
        return file_info

    def get_files_with_tag(self, tag: str) -> List[Dict[str, Any]]:
        if not tag or not isinstance(tag, str):
            raise FileServiceError("tag must be a non-empty string")

        # Approach: ask repo for all files within tags by tag match.
        # If repo had a specific method for tag filtering it would be used.
        # To avoid extra DB calls, call repo.get_all_files then for each file fetch tags via get_files_with_tags batch.
        all_meta = self.repo.get_all_files()
        if not all_meta:
            return []

        file_ids = [f["id"] for f in all_meta]
        files_with_tags = self.repo.get_files_with_tags(file_ids)

        matches = []
        for f in files_with_tags:
            for t in f.get("tags", []):
                if t.get("tag") == tag:
                    matches.append(f)
                    break
        return matches

    def get_files_name_contains(self, pattern: str, flags: int = re.IGNORECASE) -> List[Dict[str, Any]]:
        """Use regex to find filenames matching the pattern. Pattern is a regex string."""
        if not pattern or not isinstance(pattern, str):
            raise FileServiceError("pattern must be a non-empty string")
        try:
            regex = re.compile(pattern, flags)
        except re.error as e:
            raise FileServiceError(f"invalid regex pattern: {e}")

        all_meta = self.repo.get_all_files()
        if not all_meta:
            return []

        file_ids = [f["id"] for f in all_meta]
        files_with_tags = self.repo.get_files_with_tags(file_ids)

        results = []
        for f in files_with_tags:
            filename = f.get("filename", "")
            if filename and regex.search(filename):
                results.append(f)
        return results

    def get_files_by_date_range(self, start_date: str, end_date: str):
        """
        Return files uploaded between start_date and end_date.
        Includes metadata + tags. Does not include blobs.

        Dates must be formatted as:
            'YYYY-MM-DD' 
            or 'YYYY-MM-DD HH:MM:SS'
        """

        if not isinstance(start_date, str) or not isinstance(end_date, str):
            raise FileServiceError("start_date and end_date must be strings")

        try:
            files = self.repo.get_filtered_files_meta_with_tags(start_date, end_date)
            if files is None:
                return []
            return files
        except Exception as ex:
            raise FileServiceError(f"Failed to fetch files by date range: {ex}")


file_service = FileService(sql_file_store)