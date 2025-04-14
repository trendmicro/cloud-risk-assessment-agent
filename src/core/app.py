from typing import Dict, Optional
import pandas as pd #type: ignore
from io import StringIO

# LangChain imports
from langchain_core.messages import HumanMessage, AIMessage # type: ignore

# Chainlit imports
import chainlit as cl # type: ignore

# Local imports
from src.db.db_setup import setup_database_connections
from src.conductor.conductor import ConductorManager

# Custom API
from fastapi import HTTPException, Response, APIRouter # type: ignore
from chainlit.server import app # type: ignore
from starlette.routing import BaseRoute, Route # type: ignore

#-------------------------------
# Chainlit Authentication
#-------------------------------
@cl.header_auth_callback
def header_auth_callback(headers: Dict) -> Optional[cl.User]:
    """Authenticate users via header information"""
    return cl.User(identifier="admin", metadata={"role": "admin", "provider": "header"})

#-------------------------------
# chainlit workflow
#-------------------------------

@cl.on_chat_start
async def on_chat_start():
    cl.user_session.set("chat_history",[])

@cl.on_message
async def on_message(msg: cl.Message):
    chat_history = cl.user_session.get("chat_history")
    chat_history.append({"role": "user", "content": msg.content})
    
    query_result = cl.Message(content="")
    
    output = conductor.executeWorkflow("Cloud-Risk-Assessment-Agent", 1, {"query": msg.content})
    
    [result, insight, conclusion] = output["final_answer"].split(" + ")

    df = pd.read_csv(StringIO(result))
    elements = [cl.Dataframe(data=df, display="inline", name="Dataframe")]
    await cl.Message(content="Report Table:", elements=elements).send()

    await query_result.stream_token(AIMessage(content=insight).content)
    await query_result.stream_token(AIMessage(content=conclusion).content)

    await query_result.send()

@cl.set_starters
async def set_starters():
    return [
        cl.Starter(
            label="All scan executive summary report",
            message='/report all',
            icon="/public/ranking.png",
            ),
        cl.Starter(
            label="Kubernetes executive summary report",
            message='/report kubernetes',
            icon="/public/k8s.png",
            ),
        cl.Starter(
            label="AWS executive summary report",
            message="/report aws",
            icon="/public/aws.png",
            ),
        cl.Starter(
            label="Code executive summary report",
            message="/report code",
            icon="/public/code.png",
            ),
        cl.Starter(
            label="Container executive summary report",
            message="/report container",
            icon="/public/container.png",
            ),
    ]

@cl.on_chat_resume
async def on_chat_resume(thread):
    cl.user_session.set("chat_history", [])

    if thread.get("metadata") is not None and thread["metadata"].get("chat_history") is not None:
        state_messages = []
        chat_history = thread["metadata"]["chat_history"]
        for message in chat_history:
            cl.user_session.get("chat_history").append(message)
            if message["role"] == "user":
                state_messages.append(HumanMessage(content=message["content"]))
            else:
                state_messages.append(AIMessage(content=message["content"]))
            


cust_router = APIRouter()
app_context = setup_database_connections()
@cust_router.get("/blob/{object_key}")
async def serve_blob_file(
    object_key: str
):
    if app_context.storage_client is None:
        raise HTTPException(status_code=500, detail="Storage client not initialized")
    file_data = await app_context.storage_client.download_file(object_key)
    
    return Response(content=file_data, media_type="application/octet-stream")

serve_route: list[BaseRoute] = [
    r for r in app.router.routes if isinstance(r, Route) and r.name == "serve"
]

for route in serve_route:
    app.router.routes.remove(route)

app.include_router(cust_router)
app.router.routes.extend(serve_route)

#Start workers
conductor = ConductorManager()
