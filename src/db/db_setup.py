import os
import sqlite3
from sqlalchemy import create_engine

import chainlit.data as cl_data
from chainlit.data.sql_alchemy import SQLAlchemyDataLayer
from chainlit.logger import logger
from src.db.sqlite_storage import SQLiteStorageClient
from src.db.config import DEFAULT_DB_PATH

class AppContext:
    def __init__(self):
        self.storage_client = None
        self.conn = None
        self.engine = None
        self.db_path = DEFAULT_DB_PATH
        self._last_modified = None

    def check_and_reconnect(self):
        """Check if database file has been modified and reconnect if needed"""
        try:
            if not os.path.exists(self.db_path):
                logger.error(f"Database file not found: {self.db_path}")
                return False
            
            current_modified = os.path.getmtime(self.db_path)
            if self._last_modified != current_modified:
                # Close existing connection if it exists
                if self.conn:
                    self.conn.close()
                
                # Reconnect
                self.conn = sqlite3.connect(self.db_path)
                self.engine = create_engine(f"sqlite:///{self.db_path}")
                self._last_modified = current_modified
                return True
            return False
        except (sqlite3.Error, OSError) as e:
            logger.error(f"Database reconnection error: {e}")
            return False

    def get_connection(self):
        self.check_and_reconnect()
        return self.conn
    
    def get_engine(self):
        self.check_and_reconnect()
        return self.engine

def setup_database_connections():
    """
    Configure and return database connections based on environment
    """

    app_context = AppContext()
    # Initial connection
    app_context.check_and_reconnect()

    # SQLite setup
    conn_str = f"sqlite+aiosqlite:///{app_context.db_path}"
    app_context.storage_client = SQLiteStorageClient(database_path=app_context.db_path)
    
    # Set up data layer
    logger.info(f"Using database connection: {conn_str}")
    cl_data._data_layer = SQLAlchemyDataLayer(
        conninfo=conn_str,
        storage_provider=app_context.storage_client
    )

    return app_context
