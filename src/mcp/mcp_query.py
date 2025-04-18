import os
import asyncio
import logging
from aiohttp.client_exceptions import ClientError
from mcp import ClientSession, types
from mcp.client.sse import sse_client

MCP_HOST = os.getenv("MCP_HOST", "")

async def call_tool(tool_name: str, arguments: dict):
    try:
        if not MCP_HOST:
            logging.error("MCP_HOST is not set.")
            return None
        
        async with sse_client(MCP_HOST) as streams:
            read_stream, write_stream = streams
            async with ClientSession(
                read_stream, write_stream
            ) as session:
                try:
                    await session.initialize()
                    return await session.call_tool(tool_name, arguments)
                except Exception as e:
                    logging.error(f"Error during session operation: {str(e)}")
                    raise
    except ClientError as ce:
        logging.error(f"Client connection error: {str(ce)}")
        return None
    except ConnectionError as conn_err:
        logging.error(f"Connection error to MCP_HOST: {str(conn_err)}")
        return None
    except asyncio.TimeoutError:
        logging.error("Connection timed out")
        return None
    except Exception as e:
        logging.error(f"Unexpected error in semantic search: {str(e)}")
        return None

async def perform_semantic_search(query_string: str, limit: int = 1) -> str:
    try:
        result = await call_tool("semantic_search", {"query": query_string, "limit": limit})
        if not result or not result.content or len(result.content) == 0:
            logging.warning("No results found for the semantic search.")
            return ""
        return result.content[0].text
    except Exception as e:
        logging.error(f"Unexpected error in semantic search: {str(e)}")
    return ""

async def perform_search_by_id(search_id: str) -> str:
    try:
        result = await call_tool("search_by_id", {"rule_id": search_id})
        if not result or not result.content or len(result.content) == 0:
            logging.warning("No results found for the search by ID.")
            return ""
        return result.content[0].text
    except Exception as e:
        logging.error(f"Unexpected error in search by ID: {str(e)}")
    return ""

async def run():
    result = await perform_search_by_id("S3-001")
    print(f"search by id result = \n{result}\n")

    result = await perform_semantic_search("what is the KMS-006?")
    print(f"semantic search result = \n{result}\n")

if __name__ == "__main__":
    import asyncio

    asyncio.run(run())