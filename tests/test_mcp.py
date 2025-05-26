import pytest
from langchain_core.messages import HumanMessage

from src.utils.mcp import run_custom_mcp
from src.core.app import apply_mcp, AgentState


def test_run_custom_mcp_echo():
    assert run_custom_mcp("hello") == "hello"


@pytest.mark.asyncio
async def test_apply_mcp_without_chainlit(monkeypatch):
    import chainlit as cl
    monkeypatch.setattr(cl, "mcp", None, raising=False)
    state = AgentState(messages=[HumanMessage(content="hi")])
    result = await apply_mcp(state)
    assert len(result["messages"]) == 2
    assert result["messages"][1].content == "hi"
