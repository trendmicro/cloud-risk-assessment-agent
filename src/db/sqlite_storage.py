import os
import sqlite3
from typing import Any, Dict, Union

from chainlit import make_async
from chainlit.data.storage_clients.base import BaseStorageClient
from chainlit.logger import logger

service_host = os.getenv("SERVICE_HOST", "http://localhost:8000")

class SQLiteStorageClient(BaseStorageClient):
    """
    Class to enable SQLite blob file storage with per-operation connections
    """

    def __init__(self, database_path: str):
        self.database_path = database_path
        try:
            # Initialize the database and create table if needed
            conn = sqlite3.connect(self.database_path)
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS blob_storage (
                    object_key TEXT PRIMARY KEY,
                    data BLOB,
                    mime_type TEXT
                )
            """)
            conn.commit()
            cursor.close()
            conn.close()
            logger.info("SqliteStorageClient initialized")
        except Exception as e:
            logger.warning(f"SqliteStorageClient initialization error: {e}")

    def sync_upload_file(self, object_key: str, data: Union[bytes, str], mime: str = "application/octet-stream") -> Dict[str, Any]:
        try:
            conn = sqlite3.connect(self.database_path)
            cursor = conn.cursor()
            
            uuid = object_key.split('/')[0]
            sql = "INSERT OR REPLACE INTO blob_storage (object_key, data, mime_type) VALUES (?, ?, ?)"
            if isinstance(data, str):
                data = data.encode('utf-8')
            cursor.execute(sql, (uuid, data, mime))
            conn.commit()
            
            cursor.close()
            conn.close()
            
            url = f"{service_host}/blob/{uuid}"
            return {"object_key": object_key, "url": url}
        except Exception as e:
            logger.warning(f"SqliteStorageClient, upload_file error: {e}")
            return {}

    async def upload_file(self, object_key: str, data: Union[bytes, str], mime: str = "application/octet-stream", overwrite: bool = True) -> Dict[str, Any]:
        return await make_async(self.sync_upload_file)(object_key, data, mime)

    def sync_download_file(self, object_key: str) -> str:
        try:
            conn = sqlite3.connect(self.database_path)
            cursor = conn.cursor()
            
            cursor.execute("SELECT data FROM blob_storage WHERE object_key = ?", (object_key,))
            blob = cursor.fetchone()
            
            cursor.close()
            conn.close()
            
            if blob:
                return blob[0]  # Return bytes directly
            return ""
        except Exception as e:
            logger.warning(f"SqliteStorageClient, get_read_url error: {e}")
            return object_key

    async def download_file(self, object_key: str) -> str:
        return await make_async(self.sync_download_file)(object_key)

    async def get_read_url(self, object_key: str) -> str:
        uuid = object_key.split('/')[0]
        return f"{service_host}/blob/{uuid}"

    def sync_delete_file(self, object_key: str) -> bool:
        try:
            conn = sqlite3.connect(self.database_path)
            cursor = conn.cursor()
            
            uuid = object_key.split('/')[0]
            cursor.execute("DELETE FROM blob_storage WHERE object_key = ?", (uuid,))
            conn.commit()
            
            cursor.close()
            conn.close()
            
            return True
        except Exception as e:
            logger.warning(f"SqliteStorageClient, delete_file error: {e}")
            return False

    async def delete_file(self, object_key: str) -> bool:
        return await make_async(self.sync_delete_file)(object_key)