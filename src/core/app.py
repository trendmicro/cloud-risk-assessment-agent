from io import StringIO
import json
import os
from typing import Dict, Literal, Optional
import pandas as pd
import sqlite3

# LangChain imports
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.prompts import PromptTemplate
from langgraph.graph import StateGraph, END, START
from langgraph.types import Command
from langgraph.graph.message import MessagesState
from langgraph.checkpoint.memory import MemorySaver
from langchain.schema.runnable.config import RunnableConfig

# Chainlit imports
import chainlit as cl
import chainlit.data as cl_data
from chainlit.data.sql_alchemy import SQLAlchemyDataLayer

# Local imports
from src.utils.utils import token_count, read_prompt, read_file_prompt, messages_token_count, load_chat_model, get_latest_human_message, reasoning_prompt, trim_messages_to_max_tokens
from src.db.db_query import generate_query, is_valid_query, query_summary

# Custom API
from fastapi import FastAPI, HTTPException, Request, Response, APIRouter
from starlette.responses import StreamingResponse
from chainlit.server import app
from starlette.routing import BaseRoute, Route

checkpointer=MemorySaver()

#-------------------------------
# System Constants
#-------------------------------
SYSTEM_PROMPT = read_file_prompt("./src/prompts/report_system_prompt.txt")

VALID_REPORT_CATEGORIES = {"code", "container", "aws", "kubernetes", "all"}

#-------------------------------
# Database Configuration
#-------------------------------
from src.db.db_setup import setup_database_connections

app_context = setup_database_connections()
#-------------------------------
# Model setup
#-------------------------------
model = load_chat_model()
final_model = load_chat_model().with_config(tags=["final_node"])

#-------------------------------
# Chainlit Authentication
#-------------------------------
@cl.header_auth_callback
def header_auth_callback(headers: Dict) -> Optional[cl.User]:
    """Authenticate users via header information"""
    return cl.User(identifier="admin", metadata={"role": "admin", "provider": "header"})

#-------------------------------
# State Definition
#-------------------------------
class AgentState(MessagesState):
    """State maintained throughout the agent's workflow"""
    intention: Optional[str] = None
    user_query: Optional[str] = None
    sql_query: Optional[str] = None
    query_results: Optional[str] = None
    category: Optional[str] = None
    result_text: Optional[str] = None
    top5: Optional[str] = None
    dataframe: Optional[str] = None




#-------------------------------
# Helper Functions
#-------------------------------
def parse_report_command(input_string: str) -> str:
    """
    Parse a /report command and extract the category.
    Raises ValueError for invalid input.
    """
    command_prefix = "/report "
    
    if not input_string.startswith(command_prefix):
        raise ValueError("Input does not start with '/report'.")
        
    # Extract the argument after the prefix
    argument = input_string[len(command_prefix):].strip()
    
    if not argument:
        raise ValueError("No argument provided after '/report'.")
        
    if argument not in VALID_REPORT_CATEGORIES:
        raise ValueError(
            f"Invalid argument '{argument}'. Allowed arguments are "
            f"{', '.join(VALID_REPORT_CATEGORIES)}."
        )
        
    return argument

#-------------------------------
# Node Functions
#-------------------------------
async def classify_user_intent(state: AgentState):
    """
    Classify the user's query as either a report request or a regular question.
    """
    messages = state["messages"]
    query = get_latest_human_message(messages)
    print(f"\n\nUSER QUERY: {query} \n")
    
    try:
        # Try to parse as a report command
        category = parse_report_command(query)
        return Command(
            update={"category": category},
            goto="summary"
        )
    except ValueError:
        # Process as a regular question
        content = reasoning_prompt(
            "./src/prompts/intent_classification_prompt.txt", 
            question=query
        )
        intent_response = await model.ainvoke([HumanMessage(content=content)])
        
        try:
            res = json.loads(intent_response.content)
            score = res.get("Score", 0)
            
            if score > 30:
                return Command(
                    update={"intention": res, "user_query": query},
                    goto="querydb"
                )
            else:
                return Command(
                    update={"intention": res, "user_query": None},
                    goto="reason"
                )
        except json.JSONDecodeError:
            # Handle invalid JSON response
            print("Failed to parse intent classification response")
            return Command(
                update={"user_query": query},
                goto="reason"
            )
        
async def invoke_llm(state: AgentState):
    messages = state["messages"]
    response = await model.ainvoke(messages)
    # We return a list, because this will get added to the existing list
    return {"messages": [response]}

async def generate_summary_report(state: AgentState):
    """Generate a summary report based on the specified category"""
    print("--------------do_summary---------------")
    category = state["category"]

    # Query database for summary data
    summary_df, details_df = await query_summary(app_context.get_connection(), category)
    
    # Convert results to string format
    result = details_df.to_string(index=False)
    top5_result = details_df.to_string()
    summary = summary_df.to_string(index=False)

    # Format prompt for the model
    template = read_prompt("summary")
    prompt = PromptTemplate(
        template=template,
        input_variables=["category", "summary", "result"]
    )
    formatted_prompt = prompt.format(
        category=category, 
        summary=summary, 
        result=result
    )
    
    # Create messages for the model
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=formatted_prompt)
    ]

    # Log token usage
    tokens = token_count(formatted_prompt)
    print(f"Token used: {tokens}\n")

    # Get response from the model
    response = await final_model.ainvoke(messages)

    # Store results in state
    df_str = details_df.to_csv(index=False)
    return {
        "dataframe": df_str, 
        "result_text": result, 
        "top5": top5_result, 
        "messages": [response]
    }

async def generate_insights(state: AgentState):
    """Generate insights based on the top 5 results"""
    print("--------------do_insight---------------")
    result = state["top5"]

    # Format prompt for insights
    template = read_prompt("insight")
    prompt = PromptTemplate(
        template=template,
        input_variables=["result"]
    )
    formatted_prompt = prompt.format(result=result)
    
    # Create messages for the model
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=formatted_prompt)
    ]
    
    # Get response from the model
    response = await final_model.ainvoke(messages)

    return {"messages": [response]}

async def finalize_conclusion(state: AgentState):
    """Generate a conclusion based on the full results"""
    print("--------------do_conclude---------------")
    messages = state["messages"]
    result = state["result_text"]

    # Add conclusion prompt to messages
    template = read_prompt("conclude")
    messages.append(HumanMessage(content=template))
    
    # Log token usage
    total_tokens = messages_token_count(messages)
    print(f"total message tokens: {total_tokens}")
    
    # Get response from the model
    response = await final_model.ainvoke(messages)
    
    return {"messages": [HumanMessage(content=result), response]}

async def execute_db_query(state: AgentState) -> Command[Literal["reason"]]:
    """
    Execute a database query based on the user's question
    """
    messages = state["messages"]
    user_query = state["user_query"]
    
    # Determine category if available
    category = state.get("category", "ALL").upper() if state.get("category") else "ALL"

    try:
        # Generate a database query using the model
        generated_query = await generate_query(user_query, category, model)

        # Validate the generated query
        if not is_valid_query(generated_query, app_context.get_engine()):
            print("Generated query is invalid or potentially unsafe.\n\n")
            return Command(
                update={"user_query": user_query},
                goto="reason"
            )

        # Execute the validated query
        print("Executing query...\n\n")
        cursor = app_context.get_connection().cursor()
        cursor.execute(generated_query)
        records = cursor.fetchall()

        # Prepare query results
        if records:
            columns = [desc[0] for desc in cursor.description]
            results_str = "\n".join(str(dict(zip(columns, row))) for row in records)
        else:
            results_str = "No results returned."

        print("Query results prepared.\n\n")
        return Command(
            update={
                "user_query": user_query, 
                "sql_query": generated_query, 
                "query_results": results_str, 
                "messages": messages + [SystemMessage(content="Query executed successfully.")]
            },
            goto="reason"
        )

    except Exception as e:
        print(f"Error during query execution: {e}\n\n")
        return Command(
            update={"user_query": user_query},
            goto="reason"
        )

async def provide_explanation(state: AgentState):
    """
    Generate an explanation based on query results
    """
    try:
        user_query = state.get("user_query", "")
        sql_query = state.get("sql_query", "")
        query_results = state.get("query_results", "")
        messages = state.get("messages", [])

        # If the user query is missing, default to the latest human message
        if not user_query:
            user_query = get_latest_human_message(state["messages"])

        # Format the explanation prompt
        template = read_prompt("explanation")
        prompt = PromptTemplate(
            template=template,
            input_variables=["question", "sql_query", "scan_results"]
        )
        formatted_prompt = prompt.format(
            question=user_query, 
            sql_query=sql_query, 
            scan_results=query_results
        )
        
        # Limit prompt size to prevent token overflow
        if len(formatted_prompt) > 80000:
            formatted_prompt = formatted_prompt[:80000]

        messages.append(HumanMessage(content=formatted_prompt))
        messages = trim_messages_to_max_tokens(messages)
        # Get response from the model
        explanation_response = await model.ainvoke(messages)
        
        # Clear state for next interaction
        return Command(
            update={
                "user_query": None,
                "sql_query": None,
                "query_results": None,
                "messages": state["messages"] + [explanation_response]
            }
        )

    except Exception as e:
        print(f"Error during explanation generation: {e}")
        return Command(
            update={
                "user_query": None,
                "sql_query": None,
                "query_results": None,
                "messages": state["messages"] + [
                    SystemMessage(content="An error occurred while generating the explanation. Please try again.")
                ]
            }
        )


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
builder.add_node("report", invoke_llm)

# define the node which will display the resoning result on web
REASONING_NODE = ["reason", "report", "summary", "insight", "assessment", "remediation", "effort", "conclude"]

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
