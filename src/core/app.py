from io import StringIO
from typing import Dict, Optional
import pandas as pd # type: ignore

# LangChain imports
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage # type: ignore
from langgraph.graph import StateGraph, END, START # type: ignore
from langgraph.checkpoint.memory import MemorySaver # type: ignore
from langchain.schema.runnable.config import RunnableConfig # type: ignore

# Chainlit imports
import chainlit as cl # type: ignore

# Local imports
from src.core.agent_state import AgentState
from src.core.node_functions import classify_user_intent, execute_db_query, generate_summary_report, generate_insights, finalize_conclusion, provide_explanation
from src.db.db_setup import setup_database_connections

# Custom API
from fastapi import HTTPException, Response, APIRouter # type: ignore
from chainlit.server import app # type: ignore
from starlette.routing import BaseRoute, Route # type: ignore

checkpointer=MemorySaver()

#-------------------------------
# Graph node
#-------------------------------

builder = StateGraph(AgentState)

builder.add_node("intent", classify_user_intent)
builder.add_node("querydb", execute_db_query)
builder.add_node("summary", generate_summary_report)
builder.add_node("insight", generate_insights)
builder.add_node("conclude", finalize_conclusion)
builder.add_node("reason", provide_explanation)

# define the node which will display the reasoning result on web
REASONING_NODE = ["reason", "summary", "insight", "conclude"]

builder.add_edge(START, "intent")
builder.add_edge("summary", "insight")
builder.add_edge("insight", "conclude")
builder.add_edge("querydb", "reason")
builder.add_edge("conclude", END)
builder.add_edge("reason", END)

graph = builder.compile(
checkpointer=checkpointer
)

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
    config = {"configurable": {"thread_id": msg.thread_id}}

    cb = cl.LangchainCallbackHandler()
    final_answer = cl.Message(content="")
    
    async for msg, metadata in graph.astream({"messages": [HumanMessage(content=msg.content)]}, stream_mode="messages", config=RunnableConfig(callbacks=[], **config)):
        if (
            msg.content
            and not isinstance(msg, HumanMessage)
            and not isinstance(msg, SystemMessage)
            and metadata["langgraph_node"] in REASONING_NODE
        ):
            await final_answer.stream_token(msg.content)

        if (
            "finish_reason" in msg.response_metadata
            and msg.response_metadata["finish_reason"] == "stop"
        ):
            await final_answer.stream_token("\n\n")

        # Hack print report by dataframe
        if (
            "finish_reason" in msg.response_metadata
            and msg.response_metadata["finish_reason"] == "stop"
            and metadata["langgraph_node"] in ["insight"]
        ):
            state = graph.get_state(config=config)
            df_str = state.values["dataframe"]
            df = pd.read_csv(StringIO(df_str))
            elements = [cl.Dataframe(data=df, display="inline", name="Dataframe")]
            await cl.Message(content="Report Table:", elements=elements).send()

    await final_answer.send()

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

    if thread.get("metadata") is not None:
        metadata = thread["metadata"]
        # check type of metadata of the thread, if it is a string, convert it to a dictionary
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        
        if metadata.get("chat_history") is not None:
            state_messages = []
            chat_history = metadata["chat_history"]
            for message in chat_history:
                cl.user_session.get("chat_history").append(message)
                if message["role"] == "user":
                    state_messages.append(HumanMessage(content=message["content"]))
                else:
                    state_messages.append(AIMessage(content=message["content"]))

            thread_id = thread["id"]
            config = {"configurable": {"thread_id": thread_id}}
            state = graph.get_state(config).values
            if "messages" not in state:
                state["messages"] = state_messages
                graph.update_state(config, state)



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
