# MCP Integration

This project uses a lightweight custom MCP implementation to enrich the user query before reasoning.

Chainlit\'s latest version provides a built‑in MCP module that can run external tools. When available, the agent invokes the Chainlit MCP to process the latest user message. If the Chainlit MCP is not present, a local fallback defined in `src/utils/mcp.py` simply echoes the input. The enriched content is added as a new message before the reasoning step, allowing the LLM to generate more detailed answers.

