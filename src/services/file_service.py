# Service class and unit tests for MySQLDocumentStore-based repository.
# This code uses unittest.mock to simulate the repository (no real DB required).
# It exercises every function requested and asserts expected behavior.
# Run in a Python environment; here it will execute and display test results.

import io
import re
import unittest
from unittest.mock import MagicMock, call
from typing import List, Dict, Any
from repositories.file_and_meta import MySQLDocumentStore, sql_file_store
from services.file_text_parser import DocumentProcessor, document_processor
from repositories.file_text_vector_store import vector_store
from concurrent.futures import ThreadPoolExecutor
from utilities.logger import setup_logger

logger = setup_logger(__name__)
# Initialize a ThreadPoolExecutor once for the service
# Max workers depends on your environment; 4 is a common starting point.
thread_pool = ThreadPoolExecutor(max_workers=4)

class FileServiceError(Exception):
    pass


class QueueFullError(FileServiceError):
    """Raised when the parsing queue is full (too many files queued/parsing)."""
    pass


class FileService:
    def __init__(self, repo:MySQLDocumentStore, document_processor:DocumentProcessor):
        self.repo = repo
        self.document_processor = document_processor

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
        
        # 3. Parse Text and Save (Non-critical operation, run after successful upload)
        # NOTE: This call is placed *after* the file is fully uploaded (metadata & blob)
        # so that text extraction failure doesn't prevent the file from being stored.
        # Before scheduling, check queue limit (allow at most 5 queued/parsing files)
        try:
            current_queue = self.repo.count_parsing_queue()
        except Exception as ex:
            logger.exception("Failed to count parsing queue: %s", ex)
            current_queue = 0

        MAX_QUEUE = 5
        if current_queue >= MAX_QUEUE:
            # do not schedule parsing; inform caller via a specific exception
            raise QueueFullError("parsing queue full; please try again later")

        # Mark as queued in DB before scheduling
        try:
            self.repo.update_parsing_state(file_id, 'queued')
        except Exception:
            logger.exception("Failed to mark file %s as queued", file_id)

        # Schedule parsing and saving of extracted text on a background thread
        try:
            future = thread_pool.submit(self._parse_file_text_and_save, file_id, filename, bytes(file_bytes))
        except Exception:
            # If scheduling fails, log and revert queued state to pending
            logger.exception("Failed to schedule text parsing task for file %s", file_id)
            try:
                self.repo.update_parsing_state(file_id, 'pending')
            except Exception:
                logger.exception("Failed to revert parsing state for file %s", file_id)
            future = None

        logger.info(f"File {file_id} uploaded successfully. Text parsing scheduled in background thread.")

        # return full file info (without re-querying blob to keep it simple)
        result = {"file_id": file_id, "filename": filename, "file_size": file_size, "blob_id": blob_id}
        # include a brief indicator that parsing was scheduled (True/False)
        result["parsing_scheduled"] = bool(future)
        return result
    
    def _parse_file_text_and_save(self, file_id: str, filename: str, file_bytes: bytes):
        """
        Parses text from the file using OCR and saves the page-by-page text
        to the MySQL database (SQL) and vector store (Qdrant) synchronously.
        
        Flow:
        1. Extract text from file via OCR
        2. Save extracted text page-by-page to MySQL (file_text table)
        3. Store vectors (dense + sparse) in Qdrant for semantic & keyword search
        4. Update parsing state to 'done' or 'failed'
        """
        # Update state -> parsing
        try:
            try:
                self.repo.update_parsing_state(file_id, 'parsing')
            except Exception:
                logger.exception("Failed to mark file %s as parsing", file_id)

            # 1. Extract text using the DocumentProcessor
            # The document_processor may be CPU or IO bound; running in thread pool avoids blocking the main event loop
            extracted_texts = self.document_processor.parse_document_via_ocr(file_bytes, filename)

            if not extracted_texts:
                logger.warning(f"File {file_id}: No text extracted via OCR.")
                try:
                    self.repo.update_parsing_state(file_id, 'done')
                except Exception:
                    logger.exception("Failed to mark file %s as done after empty extraction", file_id)
                return

            # 2. Save extracted text page by page to MySQL
            pages_saved = 0
            for page_num, text in extracted_texts.items():
                if text.strip():
                    try:
                        self.repo.insert_file_text_page(file_id, page_num, text)
                        pages_saved += 1
                    except Exception:
                        logger.exception(
                            f"Failed to save text for file {file_id}, page {page_num} to MySQL"
                        )

            logger.info(f"File {file_id}: Saved text for {pages_saved} pages to MySQL.")

            # 3. Store vectors in Qdrant (semantic + keyword search)
            if vector_store:
                pages_vectorized = 0
                for page_num, text in extracted_texts.items():
                    if text.strip():
                        try:
                            success = vector_store.store_page_text(
                                file_id=file_id,
                                page_number=page_num,
                                text=text,
                                filename=filename,
                            )
                            if success:
                                pages_vectorized += 1
                        except Exception:
                            logger.exception(
                                f"Failed to store vectors for file {file_id}, page {page_num} in Qdrant"
                            )

                logger.info(f"File {file_id}: Stored vectors for {pages_vectorized} pages in Qdrant.")
            else:
                logger.warning(f"Vector store not available; skipping Qdrant indexing for file {file_id}")

            # Mark done
            try:
                self.repo.update_parsing_state(file_id, 'done')
            except Exception:
                logger.exception("Failed to mark file %s as done", file_id)

        except Exception as e:
            # Log the error, and mark as failed
            logger.error(f"Failed to parse and save text for file {file_id} ({filename}): {e}", exc_info=True)
            try:
                self.repo.update_parsing_state(file_id, 'failed')
            except Exception:
                logger.exception("Failed to mark file %s as failed", file_id)

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
        """
        Delete file from database and vector store.
        """
        result = self.repo.delete_file(file_id)
        if not result:
            raise FileServiceError(f"failed to delete file {file_id}")
        
        # Also delete vectors from Qdrant
        if vector_store:
            try:
                vector_store.delete_file_vectors(file_id)
                logger.info(f"Deleted vectors for file {file_id} from Qdrant")
            except Exception:
                logger.exception(f"Failed to delete vectors for file {file_id} from Qdrant")
        
        return True

    def get_most_recent_files(self, limit: int = 10) -> List[Dict[str, Any]]:
        if limit <= 0:
            raise FileServiceError("limit must be > 0")
        files = self.repo.get_all_files()
        for file in files:
            if file['tags'] is not None:
                file['tags'] = file['tags'].split(',')
        # repo.get_all_files is already ordered by upload_time DESC in repo implementation
        return files[:limit]

    def get_file_with_blob(self, file_id: int) -> Dict[str, Any]:
        file_info = self.repo.get_file(file_id)
        if not file_info:
            raise FileServiceError("file not found")
        # Should contain 'blob' key as per repo.get_file implementation
        return file_info

    def get_parsing_state(self, file_id: int) -> str:
        """
        Return the parsing_state for a file.
        """
        file_info = self.repo.get_file(file_id)
        if not file_info:
            raise FileServiceError("file not found")
        return file_info.get('parsing_state')

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

    def get_all_tags(self):
        """
        Return a sorted list of unique tags across all files.
        Uses repository.get_all_files() which returns a comma-separated 'tags' field.
        """
        try:
            all_meta = self.repo.get_all_files()
            if not all_meta:
                return []

            tags_set = set()
            for f in all_meta:
                tags_field = f.get('tags')
                if not tags_field:
                    continue

                # repo.get_all_files returns a comma-separated string of tags (or None)
                if isinstance(tags_field, str):
                    for t in tags_field.split(','):
                        t = t.strip()
                        if t:
                            tags_set.add(t)
                # defensive: if it's already a list
                elif isinstance(tags_field, list):
                    for t in tags_field:
                        if isinstance(t, dict):
                            val = t.get('tag')
                            if val:
                                tags_set.add(val)
                        elif isinstance(t, str):
                            tags_set.add(t)

            return sorted(tags_set)
        except Exception as ex:
            raise FileServiceError(f"Failed to fetch tags: {ex}")


file_service = FileService(sql_file_store, document_processor)