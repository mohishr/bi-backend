import pymysql
from typing import Optional, Dict, Any, List


class MySQLDocumentStore:
    def __init__(self, host: str, port: int, user: str, password: str, database: str):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.database = database

        self._create_database()
        self._create_tables()

    # ---------------------------------------------------------
    # Internal DB Connect
    # ---------------------------------------------------------
    def _connect(self, db=None):
        return pymysql.connect(
            host=self.host,
            user=self.user,
            password=self.password,
            database=db if db else self.database,
            cursorclass=pymysql.cursors.DictCursor,
            port=self.port
        )

    # ---------------------------------------------------------
    # Create Database
    # ---------------------------------------------------------
    def _create_database(self):
        conn = pymysql.connect(
            host=self.host,
            user=self.user,
            password=self.password
        )
        cursor = conn.cursor()

        try:
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS {self.database}")
            conn.commit()
        finally:
            cursor.close()
            conn.close()

    # ---------------------------------------------------------
    # Create Files, Blobs, Tags Tables
    # ---------------------------------------------------------
    def _create_tables(self):
        conn = self._connect()
        cursor = conn.cursor()

        files_table = """
        CREATE TABLE IF NOT EXISTS files (
            id BIGINT PRIMARY KEY AUTO_INCREMENT,
            filename VARCHAR(255) NOT NULL UNIQUE,
            file_size BIGINT NOT NULL,
            upload_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            parsing_state VARCHAR(20) DEFAULT 'pending'
        );
        """

        file_blobs_table = """
        CREATE TABLE IF NOT EXISTS file_blobs (
            id BIGINT PRIMARY KEY AUTO_INCREMENT,
            file_id BIGINT NOT NULL,
            blob_data LONGBLOB NOT NULL,
            CONSTRAINT fk_file_blob FOREIGN KEY (file_id)
                REFERENCES files(id) ON DELETE CASCADE
        );
        """

        tags_table = """
        CREATE TABLE IF NOT EXISTS tags (
            id BIGINT PRIMARY KEY AUTO_INCREMENT,
            file_id BIGINT NOT NULL,
            tag VARCHAR(255) NOT NULL,
            tagged_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_tag_file FOREIGN KEY (file_id)
                REFERENCES files(id) ON DELETE CASCADE
        );
        """
        file_text_table = """
        CREATE TABLE IF NOT EXISTS file_text (
            id BIGINT PRIMARY KEY AUTO_INCREMENT,
            file_id BIGINT NOT NULL,
            page_number INT NOT NULL,
            parsed_text TEXT,
            CONSTRAINT fk_file_text FOREIGN KEY (file_id)
                REFERENCES files(id) ON DELETE CASCADE
        );
        """

        try:
            cursor.execute(files_table)
            cursor.execute(file_blobs_table)
            cursor.execute(tags_table)
            cursor.execute(file_text_table)
            conn.commit()
        finally:
            cursor.close()
            conn.close()

    # ---------------------------------------------------------
    # Insert File Metadata
    # ---------------------------------------------------------
    def insert_file_metadata(self, filename: str, file_size: int) -> int:
        sql = """
            INSERT INTO files (filename, file_size)
            VALUES (%s, %s)
        """

        conn = self._connect()
        cursor = conn.cursor()

        try:
            cursor.execute(sql, (filename, file_size))
            conn.commit()
            return cursor.lastrowid
        finally:
            cursor.close()
            conn.close()

    def update_parsing_state(self, file_id: int, state: str) -> bool:
        """
        Update the parsing_state for a file. Returns True if a row was updated.
        Valid states: 'pending','queued','parsing','done','failed'
        """
        sql = """
            UPDATE files SET parsing_state = %s WHERE id = %s
        """

        conn = self._connect()
        cursor = conn.cursor()
        try:
            cursor.execute(sql, (state, file_id))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            cursor.close()
            conn.close()

    def count_parsing_queue(self) -> int:
        """
        Count files that are currently queued or parsing.
        """
        sql = """
            SELECT COUNT(*) as cnt FROM files WHERE parsing_state IN ('queued','parsing')
        """

        conn = self._connect()
        cursor = conn.cursor()
        try:
            cursor.execute(sql)
            row = cursor.fetchone()
            return int(row['cnt']) if row else 0
        finally:
            cursor.close()
            conn.close()

    # ---------------------------------------------------------
    # Insert Binary Blob
    # ---------------------------------------------------------
    def insert_file_blob(self, file_id: int, blob_data: bytes) -> int:
        sql = """
            INSERT INTO file_blobs (file_id, blob_data)
            VALUES (%s, %s)
        """

        conn = self._connect()
        cursor = conn.cursor()

        try:
            cursor.execute(sql, (file_id, blob_data))
            conn.commit()
            return cursor.lastrowid
        finally:
            cursor.close()
            conn.close()

    # ---------------------------------------------------------
    # Add Tag to File
    # ---------------------------------------------------------
    def add_tag(self, file_id: int, tag: str) -> int:
        sql = """
            INSERT INTO tags (file_id, tag)
            VALUES (%s, %s)
        """

        conn = self._connect()
        cursor = conn.cursor()

        try:
            cursor.execute(sql, (file_id, tag))
            conn.commit()
            return cursor.lastrowid
        finally:
            cursor.close()
            conn.close()

    # ---------------------------------------------------------
    # Remove a Tag from File
    # ---------------------------------------------------------
    def remove_tag(self, file_id: int, tag: str) -> bool:
        sql = """
            DELETE FROM tags
            WHERE file_id = %s AND tag = %s
        """

        conn = self._connect()
        cursor = conn.cursor()

        try:
            cursor.execute(sql, (file_id, tag))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            cursor.close()
            conn.close()

    # ---------------------------------------------------------
    # Delete File Completely (cascade)
    # ---------------------------------------------------------
    def delete_file(self, file_id: int) -> bool:
        sql = "DELETE FROM files WHERE id = %s"

        conn = self._connect()
        cursor = conn.cursor()

        try:
            cursor.execute(sql, (file_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            cursor.close()
            conn.close()

    # ---------------------------------------------------------
    # Fetch File with Metadata, Blob, Tags
    # ---------------------------------------------------------
    def get_file(self, file_id: int) -> Optional[Dict[str, Any]]:
        sql = """
            SELECT 
                f.id AS file_id,
                f.parsing_state,
                f.filename,
                f.file_size,
                f.upload_time,
                b.blob_data,
                t.tag,
                t.tagged_at
            FROM files f
            LEFT JOIN file_blobs b ON f.id = b.file_id
            LEFT JOIN tags t ON f.id = t.file_id
            WHERE f.id = %s
        """

        conn = self._connect()
        cursor = conn.cursor()

        try:
            cursor.execute(sql, (file_id,))
            rows = cursor.fetchall()

            if not rows:
                return None

            # Build structured response
            file_info = {
                "file_id": rows[0]["file_id"],
                "parsing_state": rows[0].get("parsing_state"),
                "filename": rows[0]["filename"],
                "file_size": rows[0]["file_size"],
                "upload_time": rows[0]["upload_time"],
                "blob": rows[0]["blob_data"],
                "tags": []
            }

            for r in rows:
                if r["tag"]:
                    file_info["tags"].append({
                        "tag": r["tag"],
                        "tagged_at": r["tagged_at"]
                    })

            return file_info

        finally:
            cursor.close()
            conn.close()

    # ---------------------------------------------------------
    # Fetch All Files Metadata
    # ---------------------------------------------------------
    def get_all_files(self) -> List[Dict[str, Any]]:
        sql = """
            SELECT 
                f.id AS file_id,
                f.filename,
                f.file_size,
                f.parsing_state,
                f.upload_time,
                GROUP_CONCAT(t.tag) AS tags
            FROM files f
            LEFT JOIN tags t on f.id = t.file_id
            GROUP BY f.id,f.filename, f.file_size, f.upload_time
            ORDER BY upload_time DESC;
        """

        conn = self._connect()
        cursor = conn.cursor()

        try:
            cursor.execute(sql)
            return cursor.fetchall()
        finally:
            cursor.close()
            conn.close()
    
    # ---------------------------------------------------------
    # Fetch MULTIPLE files (metadata + blob + tags)
    # ---------------------------------------------------------
    def get_files_with_tags(self, file_ids: List[int]):
        if not file_ids:
            return []

        # Build IN clause dynamically
        placeholders = ", ".join(["%s"] * len(file_ids))

        sql = f"""
            SELECT 
                f.id AS file_id,
                f.parsing_state,
                f.filename,
                f.file_size,
                f.upload_time,
                b.blob_data,
                t.tag,
                t.tagged_at
            FROM files f
            LEFT JOIN file_blobs b ON f.id = b.file_id
            LEFT JOIN tags t ON f.id = t.file_id
            WHERE f.id IN ({placeholders})
            ORDER BY f.upload_time DESC
        """

        conn = self._connect()
        cursor = conn.cursor()

        try:
            cursor.execute(sql, file_ids)
            rows = cursor.fetchall()

            if not rows:
                return []

            # Build dict keyed by file_id
            files_dict = {}

            for r in rows:
                fid = r["file_id"]

                if fid not in files_dict:
                    files_dict[fid] = {
                        "file_id": fid,
                        "parsing_state": r.get("parsing_state"),
                        "filename": r["filename"],
                        "file_size": r["file_size"],
                        "upload_time": r["upload_time"],
                        "blob": r["blob_data"],
                        "tags": []
                    }

                # add tag if exists
                if r["tag"]:
                    files_dict[fid]["tags"].append({
                        "tag": r["tag"],
                        "tagged_at": r["tagged_at"]
                    })

            # return sorted list
            return list(files_dict.values())

        finally:
            cursor.close()
            conn.close()

        # ---------------------------------------------------------
   
    # Get filtered files (metadata + tags) by upload date range
    # ---------------------------------------------------------
    def get_filtered_files_meta_with_tags(self,
                                          start_date: str,
                                          end_date: str):
        """
        Fetch files whose upload_time is between start_date and end_date.
        Returns metadata + tags (no blobs).
        
        Dates must be strings in the format: 'YYYY-MM-DD' or 'YYYY-MM-DD HH:MM:SS'
        """

        sql = """
            SELECT 
                f.id AS file_id,
                f.parsing_state,
                f.filename,
                f.file_size,
                f.upload_time,
                t.tag,
                t.tagged_at
            FROM files f
            LEFT JOIN tags t ON f.id = t.file_id
            WHERE f.upload_time BETWEEN %s AND %s
            ORDER BY f.upload_time DESC
        """

        conn = self._connect()
        cursor = conn.cursor()

        try:
            cursor.execute(sql, (start_date, end_date))
            rows = cursor.fetchall()

            if not rows:
                return []

            # Build structured dict keyed by file_id
            files_dict = {}
            for r in rows:
                fid = r["file_id"]

                if fid not in files_dict:
                    files_dict[fid] = {
                        "file_id": fid,
                        "parsing_state": r.get("parsing_state"),
                        "filename": r["filename"],
                        "file_size": r["file_size"],
                        "upload_time": r["upload_time"],
                        "tags": []
                    }

                # append tag if exists
                if r["tag"]:
                    files_dict[fid]["tags"].append({
                        "tag": r["tag"],
                        "tagged_at": r["tagged_at"]
                    })

            return list(files_dict.values())

        finally:
            cursor.close()
            conn.close()

    # Add methods to insert and fetch file text 
    # insert file text page wise
    # fetch file text for all pages at once ensure errors and typesafe
    def insert_file_text_page(self, file_id: int, page_number: int, parsed_text: str) -> int:
        """
        Insert parsed text for a specific page.
        If the page already exists, it will be updated instead.
        """

        sql = """
            INSERT INTO file_text (file_id, page_number, parsed_text)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE parsed_text = VALUES(parsed_text)
        """

        conn = self._connect()
        cursor = conn.cursor()

        try:
            cursor.execute(sql, (file_id, page_number, parsed_text))
            conn.commit()
            return cursor.lastrowid
        finally:
            cursor.close()
            conn.close()
            
    def get_text_for_file(self, file_id: int) -> List[Dict[str, Any]]:
        """
        Return all parsed pages for a file sorted by page_number ASC.
        Each item: { page_number: int, parsed_text: str }
        """
        sql = """
            SELECT page_number, parsed_text
            FROM file_text
            WHERE file_id = %s
            ORDER BY page_number ASC
        """

        conn = self._connect()
        cursor = conn.cursor()

        try:
            cursor.execute(sql, (file_id,))
            rows = cursor.fetchall()
            return rows if rows else []
        finally:
            cursor.close()
            conn.close()




# Initialize
sql_file_store = MySQLDocumentStore(
    host="localhost",
    port=3306,
    user="root",
    password="1234",
    database="documents"
)