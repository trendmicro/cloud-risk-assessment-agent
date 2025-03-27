import os
import sqlite3
from sqlalchemy import create_engine

import chainlit.data as cl_data
from chainlit.data.sql_alchemy import SQLAlchemyDataLayer
from src.db.postgres_storage import PostgreSQLStorageClient
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
                print(f"Database file not found: {self.db_path}")
                return False
            
            current_modified = os.path.getmtime(self.db_path)
            if self._last_modified != current_modified:
                # Close existing connection if it exists
                if self.conn:
                    self.conn.close()
                
                # Reconnect
                self.conn = sqlite3.connect(self.db_path)
                #self.engine = create_engine(f"sqlite:///{self.db_path}")
                self._last_modified = current_modified
                return True
            return False
        except (sqlite3.Error, OSError) as e:
            print(f"Database reconnection error: {e}")
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
    # Determine if using PostgreSQL (from environment) or SQLite (fallback)
    use_postgres = all([
        os.getenv("POSTGRES_USER"),
        os.getenv("POSTGRES_PASSWORD")
    ])

    app_context = AppContext()
    # Initial connection
    app_context.check_and_reconnect()

    if use_postgres:
        # PostgreSQL setup
        dbhost = os.getenv("POSTGRES_HOST", "db")
        dbport = os.getenv("POSTGRES_PORT", "5432")
        dbuser = os.getenv("POSTGRES_USER")
        dbpassword = os.getenv("POSTGRES_PASSWORD")
        conn_str = f"{dbuser}:{dbpassword}@{dbhost}:{dbport}"

        # Create storage client for PostgreSQL
        app_context.storage_client = PostgreSQLStorageClient(database_url=f"postgresql://{conn_str}")
        conn_str = f"sqlite+aiosqlite:///{app_context.db_path}"
        # Set up data layer
        cl_data._data_layer = SQLAlchemyDataLayer(
            conninfo=conn_str,
            storage_provider=app_context.storage_client
        )

    return app_context
