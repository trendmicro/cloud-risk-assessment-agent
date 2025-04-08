from langgraph.graph.message import MessagesState
from typing import Optional

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