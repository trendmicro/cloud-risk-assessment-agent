from io import StringIO
import json
import os
from typing import Dict, Literal, Optional, Any
import pandas as pd
import sqlite3

# LangChain imports
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, ToolMessage
from langchain_core.prompts import PromptTemplate
from langgraph.graph import StateGraph, END, START
from langgraph.types import Command
from langgraph.graph.message import MessagesState
from langgraph.checkpoint.memory import MemorySaver
from langchain.schema.runnable.config import RunnableConfig
from langgraph.prebuilt import create_react_agent

# Chainlit imports
import chainlit as cl
import chainlit.data as cl_data
from chainlit.data.sql_alchemy import SQLAlchemyDataLayer
from mcp import ClientSession
from mcp.types import CallToolResult, TextContent

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
    user_query: Optional[str] = None
    sql_query: Optional[str] = None
    query_results: Optional[str] = None
    category: Optional[str] = None
    result_text: Optional[str] = None
    top5: Optional[str] = None
    dataframe: Optional[str] = None
    tool_message: Optional[str] = None




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

def is_mcp_tool_available() -> bool:
    """
    Check if any MCP tools are available.
    """
    mcp_tools = cl.user_session.get("mcp_tools", {})
    return bool(mcp_tools)

#-------------------------------
# Node Functions
#-------------------------------
async def classify_user_intent(state: AgentState):
    """
    Classify the user's query as either a report request or a regular question.
    """
    print("--------------do_intent---------------")

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
            next_node = "reason"
            if score > 30:
                next_node = "querydb"
            elif is_mcp_tool_available():
                next_node = "mcp_tool"
            return Command(
                update={"user_query": query},
                goto=next_node
            )
        except json.JSONDecodeError:
            # Handle invalid JSON response
            print("Failed to parse intent classification response")
            return Command(
                update={"user_query": query},
                goto="mcp_tool" if is_mcp_tool_available() else "reason"
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
    print("--------------do_querydb---------------")
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
            goto="mcp_tool"
        )

    except Exception as e:
        print(f"Error during query execution: {e}\n\n")
        return Command(
            update={"user_query": user_query},
            goto="mcp_tool"
        )

async def execute_mcp_tool(state: AgentState) -> Command[Literal["reason"]]:
    """
    Execute a tool call based on the user's question
    """
    print("--------------do_mcp_tool---------------")

    messages = state["messages"]

    tool_message = ""
    try:
        # Get tools from all MCP connections
        mcp_tools = cl.user_session.get("mcp_tools", {})
        if not mcp_tools:
            print("execute_mcp_tool: No MCP tools available.")
            return Command(
                update={"tool_message": ""},
                goto="reason"
            )
        
        all_tools = ""
        for conn_name, tools in mcp_tools.items():
            for tool in tools:
                all_tools += f"Tool Name: {tool['name']}\n"
                all_tools += f"Description: {tool['description']}\n"
                all_tools += f"Schema: {tool['input_schema']}\n"

        user_query = state.get("user_query", "")
        sql_query = state.get("sql_query", "")
        query_results = state.get("query_results", "")
    
        # Format the mcp prompt
        template = read_prompt("mcp")
        prompt = PromptTemplate(
            template=template,
            input_variables=["tools", "input", "sql_query", "scan_results"]
        )
        formatted_prompt = prompt.format(
            tools=all_tools, 
            input=user_query,
            sql_query=sql_query,
            scan_results=query_results
        )
        messages_history = [
            SystemMessage(content=read_file_prompt("./src/prompts/mcp_system_prompt.txt")),
            HumanMessage(content=formatted_prompt)
        ]
        response = await model.ainvoke(messages + messages_history)
        print(f"execute_mcp_tool: response = {response.content}\n\n")

        try:
            json_response = response.content.replace("```json", "").replace("```", "")
            tool_calls = json.loads(json_response)
            for tool_call in tool_calls:
                name = tool_call["name"]
                arguments = tool_call["arguments"]
                tool_result = await mcp_call_tool(name, arguments)
                tool_result_text = ""
                for content_item in tool_result.content:
                    if isinstance(content_item, TextContent):
                        tool_result_text += f"{(content_item.text)}\n"
                tool_message = tool_result_text
        except Exception as e:
            print(f"execute_mcp_tool: Error processing response: {e}, response: {json_response}")
        
    except Exception as e:
        print(f"execute_mcp_tool: Error during tool execution: {e}")
    
    return Command(
        update={"tool_message": tool_message},
        goto="reason"
    )

async def provide_explanation(state: AgentState):
    """
    Generate an explanation based on query results
    """
    print("--------------do_reason---------------")

    try:
        user_query = state.get("user_query", "")
        sql_query = state.get("sql_query", "")
        query_results = state.get("query_results", "")
        messages = state.get("messages", [])
        tool_message = state.get("tool_message", "")

        # If the user query is missing, default to the latest human message
        if not user_query:
            user_query = get_latest_human_message(state["messages"])

        # Format the explanation prompt
        template = read_prompt("explanation")
        prompt = PromptTemplate(
            template=template,
            input_variables=["question", "sql_query", "scan_results", "tool_message"]
        )
        formatted_prompt = prompt.format(
            question=user_query, 
            sql_query=sql_query, 
            scan_results=query_results,
            tool_message=tool_message
        )
        
        # Limit prompt size to prevent token overflow
        if len(formatted_prompt) > 80000:
            formatted_prompt = formatted_prompt[:80000]

        messages = trim_messages_to_max_tokens(messages)
        messages.append(HumanMessage(content=formatted_prompt))
        messages.append(SystemMessage(content=""" You are a cybersecurity expert. Your task is to provide detailed explanations based on the user's question and the context provided.
            - Requirements:
                1. If there is no relevant context (e.g., DB and MCP data do not align with the user's question), ignore the context and answer the user's question directly based on your knowledge.
                2. Provide a detailed and natural response that directly addresses the question, ensuring clarity and relevance.
                3. If context (scan results) is provided and relevant, integrate it into the answer to enhance the response.
                4. Use markdown formatting for readability:
                    a. Use ### for headings and subheadings.
                    b. Use tables for structured data (max 10 rows for readability).
                    c. Include bullet points or numbered lists to explain key details or supplement the table.
                5. Include specific resource names or identifiers where relevant, but limit examples to a manageable number for clarity.
                6. Supplement the structured data with brief explanations to enhance understanding.
                7. Avoid duplicates: Ensure entries in tables, lists, or explanations are unique and concise.
                8. For questions that are irrelevant or out of scope:
                    Provide an appropriate response or redirect the user to ask questions relevant to cybersecurity or the intended context of the interaction.
                    If clarification is needed, politely ask the user to refine or refocus their query."""
            ))

        response = await model.ainvoke(messages)
        explanation_response = response.content

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
                "tool_message": None,
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
builder.add_node("mcp_tool", execute_mcp_tool)
builder.add_node("conclude", finalize_conclusion)
builder.add_node("reason", provide_explanation)
builder.add_node("report", invoke_llm)

# define the node which will display the resoning result on web
REASONING_NODE = ["reason", "report", "summary", "insight", "assessment", "remediation", "effort", "conclude"]

builder.add_edge(START, "intent")
builder.add_edge("summary", "insight")
builder.add_edge("insight", "conclude")
builder.add_edge("querydb", "mcp_tool")
builder.add_edge("mcp_tool", "reason")
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

@cl.on_mcp_connect
async def on_mcp(connection, session: ClientSession):
    # List available tools
    result = await session.list_tools()

    # Process tool metadata
    tools = [{
        "name": t.name,
        "description": t.description,
        "input_schema": t.inputSchema,
    } for t in result.tools]
    
    # Store tools for later use
    mcp_tools = cl.user_session.get("mcp_tools", {})
    mcp_tools[connection.name] = tools
    cl.user_session.set("mcp_tools", mcp_tools)

@cl.on_mcp_disconnect
async def on_mcp_disconnect(name: str, session: ClientSession):
    mcp_tools = cl.user_session.get("mcp_tools", {})
    if name in mcp_tools:
        del mcp_tools[name]
        cl.user_session.set("mcp_tools", mcp_tools)

@cl.step(type="tool")
async def mcp_call_tool(tool_name: str, tool_input: Dict[str, Any]):
    print(f"mcp_call_tool: name = {tool_name}, input = {tool_input}")
    mcp_name = None
    mcp_tools = cl.user_session.get("mcp_tools", {})

    for conn_name, tools in mcp_tools.items():
        if any(tool["name"] == tool_name for tool in tools):
            mcp_name = conn_name
            break

    if not mcp_name:
        return {"error": f"Tool '{tool_name}' not found in any connected MCP server"}

    mcp_session, _ = cl.context.session.mcp_sessions.get(mcp_name)

    try:
        result = await mcp_session.call_tool(tool_name, tool_input)
        return result
    except Exception as e:
        return {"error": f"Error calling tool '{tool_name}': {str(e)}"}
    

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
