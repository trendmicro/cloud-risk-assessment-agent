import sqlite3
import os
import re
from langchain_openai import ChatOpenAI
from langchain_nvidia_ai_endpoints import ChatNVIDIA
from langchain_core.messages import HumanMessage, SystemMessage
from langchain.prompts import PromptTemplate
import asyncio
import sqlparse
from sqlalchemy import create_engine, text
import pandas as pd
from src.utils.utils import reasoning_prompt

# Generate query string
async def generate_query(q, category, model):
    try:
        content = reasoning_prompt("./src/prompts/db_query_prompt.txt", QUESTION=q, category=category)
        local_messages = [
            SystemMessage(content="You are a SQL query generator. Respond only with a valid SQL query string, with no explanation or additional text. The output must be ready to run directly as a SQL command."),
            HumanMessage(content=content)
        ]
        response = await model.ainvoke(local_messages)
        #remove code delimiter if exist
        sql = response.content
        sql = sql.replace("```sql", "").replace("```", "")
        return sql
    except Exception as e:
        print(f"Error generating query string for question: {q}. Error: {e}")
        return None


def is_valid_query(query, engine):
    try:
        # Check for SQL injection by ensuring it is a read-only query
        parsed = sqlparse.parse(query)
        if not parsed or parsed[0].get_type() != "SELECT":
            return False
        
        # Ensure query can be safely compiled
        stmt = text(query)
        stmt.compile(engine)
        
        return True
    except Exception as e:
        print(f"Validation failed: {e}")
        return False

def limit_string_length(resource_string, max_length=200):
    if len(resource_string) <= max_length:
        return resource_string

    packages = resource_string.split(", ")
    result = ""
    for package in packages:
        new_part = package + ", "
        if len(result + new_part) > max_length - 3:  # Reserve space for ellipsis
            result = result.rstrip(", ")  # Remove trailing comma and space
            result += "..."
            break
        result += new_part
    return result

async def query_summary(conn, cate: str):
    category = cate.upper()
    if category not in ["CODE", "KUBERNETES", "AWS", "CONTAINER", "ALL"]:
        return None, None


    query_one = f"""SELECT
      id,
      type,
      description,
      resolution,
      severity,
      risk_score,
      COUNT(*) AS resource_count,
      group_concat(resource_name, ', ') AS resource_names
    FROM
      results
    WHERE
      type = "{category}"
    GROUP BY
      type,
      avdid,
      title,
      description,
      severity,
      risk_score
    ORDER BY
      risk_score DESC;"""

    query_all = f"""SELECT
      id,
      type,
      description,
      resolution,
      severity,
      risk_score,
      COUNT(*) AS resource_count,
      group_concat(resource_name, ', ') AS resource_names
    FROM
      results
    GROUP BY
      type,
      avdid,
      title,
      description,
      severity,
      risk_score
    ORDER BY
      risk_score DESC;"""

    if category == "ALL":
        table_df = pd.read_sql_query(query_all, conn)
    else:
        table_df = pd.read_sql_query(query_one, conn)

    summary_df = table_df.groupby(['type','severity']).agg(
        total_resource_count=('resource_count', 'sum'),
        issue_count=('id', 'count')
    ).reset_index()

    table_df['resource_names'] = table_df['resource_names'].apply(limit_string_length, max_length=200)

    return summary_df, table_df.head(30)
