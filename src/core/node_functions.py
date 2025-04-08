from typing import Literal
import json

# Langchain imports
from langgraph.types import Command # type: ignore
from langchain_core.prompts import PromptTemplate # type: ignore
from langchain_core.messages import HumanMessage, SystemMessage # type: ignore

# Local imports
from src.utils.utils import token_count, read_prompt, read_file_prompt, messages_token_count, load_chat_model, get_latest_human_message, reasoning_prompt, parse_report_command
from src.db.db_query import generate_query, is_valid_query, query_summary
from src.core.agent_state import AgentState
from src.db.db_setup import setup_database_connections


app_context = setup_database_connections()

#-------------------------------
# Model setup
#-------------------------------
model = load_chat_model()
final_model = load_chat_model().with_config(tags=["final_node"])

SYSTEM_PROMPT = read_file_prompt("./src/prompts/report_system_prompt.txt")

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

        # Get response from the model
        explanation_response = await model.ainvoke([HumanMessage(content=formatted_prompt)])
        
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