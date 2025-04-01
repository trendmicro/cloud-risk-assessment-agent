import asyncio
import csv
import os
from sqlalchemy import Column, Integer, String, Float, Text, PrimaryKeyConstraint, select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.exc import SQLAlchemyError
import json
import sqlite3

# Import from config module
from src.db.config import RESULTS_TABLE_SCHEMA, CHAT_HISTORY_TABLE_SCHEMA, SAMPLE_DATA, DEFAULT_DB_PATH

# Define the base class for declarative models
Base = declarative_base()

# Define the "results" table with a composite primary key (type, id, resource_name)
class Results(Base):
    __tablename__ = "results"

    type = Column(String)
    id = Column(String)
    resource_name = Column(String)
    service_name = Column(String)
    avdid = Column(String)
    title = Column(String)
    description = Column(Text)
    resolution = Column(Text)
    severity = Column(String)
    message = Column(Text)
    cvss_strings = Column(String)
    risk_score = Column(Float)
    cause_metadata = Column(Text)
    
    __table_args__ = (
        PrimaryKeyConstraint("type", "id", "resource_name"),
    )

    def __repr__(self):
        attributes = ", ".join(f"{key}={repr(value)}" for key, value in vars(self).items())
        return f"<Results({attributes})>"

# Create an async engine; using the "aiosqlite" dialect for SQLite.
DATABASE_URL = f"sqlite+aiosqlite:///{DEFAULT_DB_PATH}"
engine = create_async_engine(DATABASE_URL, echo=True)

# Create a session maker for async sessions.
AsyncSessionLocal = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

def ensure_directory_exists(db_path):
    """
    Ensure the directory for the database file exists.
    
    Args:
        db_path (str): Path to the database file
    """
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        print(f"Creating directory: {db_dir}")
        os.makedirs(db_dir, exist_ok=True)

def _init_db_sync(db_path, sql_script):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.executescript(sql_script)
    conn.commit()
    conn.close()

async def init_db_with_raw_sql(db_path, sql_script):

    """
    Initialize the database using raw SQL (async version).
    
    Args:
        db_path (str): Path to the database file
    """
    try:
        # Connect to (or create) SQLite database
        print(f"Using raw SQL method with DB PATH: {db_path}")
        
        # Run the synchronous function in a thread to avoid blocking
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _init_db_sync, db_path, sql_script)
        
        print("Tables created successfully using raw SQL")
        return True
    except Exception as e:
        print(f"Error creating tables with raw SQL: {e}")
        return False

async def init_db(db_path=DEFAULT_DB_PATH):
    """
    Initialize the database by creating the necessary tables (async version).
    
    Args:
        db_path (str): Path to the database file
    """
    print(f"Initializing DB at {db_path}...")
    
    # Ensure directory exists
    ensure_directory_exists(db_path)
    
    # First create the database using SQLAlchemy
    try:
        # Update the engine to use the provided path
        global engine, AsyncSessionLocal, DATABASE_URL
        engine = create_async_engine(DATABASE_URL, echo=True)
        AsyncSessionLocal = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        
        # Create tables using SQLAlchemy metadata
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            print("Tables created successfully using SQLAlchemy")
        return True
    except Exception as e:
        print(f"Error creating tables with SQLAlchemy: {e}")
        
        # Fallback to raw SQL as a backup method
        return await init_db_with_raw_sql(db_path, RESULTS_TABLE_SCHEMA)

async def init_sample(db_path=DEFAULT_DB_PATH):
    """
    Initialize the database with sample data (async version).
    
    Args:
        db_path (str): Path to the database file
    """
    print(f"Initializing DB with sample data at {db_path}...")
    
    # First initialize the database
    initialized = await init_db(db_path)
    
    if not initialized:
        raise Exception(f"Failed to initialize database at {db_path}")
    
    # Then add sample data using batch_upsert_records
    try:
        await batch_upsert_records(SAMPLE_DATA)
        print(f"Sample data added successfully to {db_path}")
        return True
    except Exception as e:
        print(f"Error adding sample data: {e}")
        return False

async def upsert_record(record_data: dict) -> Results:
    """
    Upsert (insert or update) a record into the results table.

    Args:
        record_data (dict): A dictionary of column values for the record.

    Returns:
        Results: The upserted record.
    """
    try:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                # Use merge to perform an upsert.
                merged_record = await session.merge(Results(**record_data))
            await session.commit()
            return merged_record
    except SQLAlchemyError as e:
        print(f"Error upserting record: {e}")
        raise

async def batch_upsert_records(records_data: list[dict]) -> list[Results]:
    """
    Upsert (insert or update) multiple records into the results table in a single transaction.

    Args:
        records_data (list[dict]): A list of dictionaries, each containing column values for a record.

    Returns:
        list[Results]: A list of upserted records.
    """
    upserted_records = []
    try:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                for record_data in records_data:
                    # Use merge to perform an upsert.
                    merged_record = await session.merge(Results(**record_data))
                    upserted_records.append(merged_record)
            await session.commit()
        return upserted_records
    except SQLAlchemyError as e:
        print(f"Error batch upserting records: {e}")
        raise

async def query_records(record_type: str):
    """
    Query records from the results table filtered by the type column.

    Args:
        record_type (str): The type value to filter by.

    Returns:
        List[Results]: A list of matching Results records.
    """
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Results).where(Results.type == record_type)
            )
            records = result.scalars().all()
            return records
    except SQLAlchemyError as e:
        print(f"Error querying records: {e}")
        raise

async def query_all_records():
    """
    Query all records from the results table.
    
    Returns:
        List[Results]: A list of all Records.
    """
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(Results))
            records = result.scalars().all()
            return records
    except SQLAlchemyError as e:
        print(f"Error querying all records: {e}")
        raise

async def export_to_csv(file_path: str):
    """
    Export all records in the results table to a CSV file.

    Args:
        file_path (str): The path to the CSV file.
    """
    try:
        records = await query_all_records()
        if not records:
            raise ValueError("No records found to export.")

        # Extract column names dynamically from the first record
        columns = [c for c in records[0].__dict__.keys() if not c.startswith('_')]

        with open(file_path, mode='w', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            # Write the header row
            writer.writerow(columns)
            # Write each record
            for record in records:
                writer.writerow([getattr(record, col, None) for col in columns])
    except (SQLAlchemyError, ValueError, IOError) as e:
        print(f"Error exporting to CSV: {e}")
        raise
