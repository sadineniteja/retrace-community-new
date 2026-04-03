"""
Agent service — LangGraph CodeAct agent powered by the ReTrace knowledge base.

Ported from IQWorksAtlas langgraph_codeact/__init__.py (create_codeact) and
interactive_tool_agent.py (setup_agent_async).

Pipeline:
  1. Load LLM settings → build LangChain ChatModel
  2. Build StructuredTool instances (including knowledge base tool)
  3. Create LangGraph StateGraph (CodeAct pattern)
  4. Stream execution via agent.astream() → SSE events
"""

import ast
import io
import inspect
import json
import re
import sys
import time
import traceback
from contextlib import redirect_stdout
from datetime import datetime
from typing import Any, AsyncIterator, Optional
from uuid import uuid4

import structlog
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver
import asyncio
import queue
import threading
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession
from typing_extensions import TypedDict, Annotated

from app.core.config import settings as app_settings
from app.tools.utils import extract_python_code, extract_tool_call_as_python, strip_text_from_code_response

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# State schema
# ---------------------------------------------------------------------------

class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    script: Optional[str]
    context: dict
    current_iteration: int
    max_iterations: int
    is_final_answer: bool
    syntax_error_count: int
    has_native_tool_calls: bool


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_AGENT_SYSTEM_TEMPLATE = """\
You are the ReTrace AI agent by Lumena Technologies for the product **{product_name}**.

{user_platform_section}

{product_description_section}

You can execute Python code to interact with the system using the tools listed below.

## HOW TO USE TOOLS

**CRITICAL:** To call tools, output only a ```python code block with real Python that calls the tools (e.g. terminal(...), web_search(...)) and print() the result. Only ```python blocks are run; no other format is executed. When you have the answer for the user, respond with plain text only (no code block).

Generate a Python code block to call tools.  **Always `print()` results** so you
can see the output.

```python
result = terminal("ls -la")
print(result)
```

When you have a complete answer, respond with **plain text only** (no code block).
That text becomes the final answer shown to the user.

## RULES
- For **terminal commands, web searches, knowledge base queries, and general logic**: generate Python code in ```python blocks to call tools.
- For **file operations** (`write_file`, `read_file`, `str_replace`, `delete_file`): these are available as **native tools**. Call them directly — do NOT wrap them in ```python blocks. The system will execute them automatically.
- Always print() results in ```python blocks so you can see output.
- When done, respond with plain text (no code block) — that is your final answer.
- Only use the tools listed under AVAILABLE TOOLS below. Do NOT call tools that are not listed.
{kb_rules_section}- You can call tools multiple times with different queries to gather comprehensive information.
- If the evidence is insufficient, say so.
- Do NOT generate code after your final text answer.
- Maximum {max_iterations} tool-use iterations allowed.
- Do NOT use `import os`, `import subprocess`, `import shutil`, `import pathlib`, or other Python standard library modules for system operations. Always use the provided tools instead (e.g. `terminal("ls -la")`, `read_file("path")`, `write_file("path", "content")`).
- Do NOT use `open()`, `os.listdir()`, `Path()`, or any direct Python file I/O. Use the provided `read_file`, `write_file`, `delete_file`, and `terminal` tools for all file and system operations.
- Only use `import` for data processing libraries (e.g. `json`, `re`, `math`) when needed to parse or format tool output.
- When using the `screenops` tool: it returns a JSON object with a "result" field (and optionally "iterations"). Before writing to a file or using the content, parse the return value: if it is a string, use `json.loads(screenops_result)` to get a dict, then use the "result" field only (e.g. `description_text = data["result"]` or `data.get("result", "")`). Pass that string to `write_file`, not the raw return value.

## TOOL SELECTION GUIDE
- **Finding files by name/pattern**: use `glob_search("*.py")` — NOT `terminal("find ...")`
- **Searching file contents**: use `grep("pattern", "path")` — NOT `terminal("grep ...")`
- **Editing files (targeted changes)**: use `str_replace(file, old, new)` — NOT rewriting the whole file
- **Deleting files**: use `delete_file("path")` — NOT `terminal("rm ...")`
- **Reading web pages**: use `web_fetch("url")` — returns clean text
- **Web search**: use `web_search("query")` for quick lookups, `web_research("query")` for comprehensive research, `web_advanced(...)` for advanced searches with operators
- **Multi-step tasks**: use `todo_write(...)` to plan and track progress

- **SSH**: ALWAYS pass the remote command inline: `terminal('ssh user@host "cmd"')`. NEVER open an interactive session (`ssh user@host` alone) — it will timeout.

{tool_descriptions}
"""

_KB_RULES = """\
- You have one **knowledge_base** tool with four actions (pass the `action` parameter):
  * `knowledge_base(action="search", query="...", keywords=[...], top_k=10)` — **Use this FIRST for any product question.** Fast hybrid search. Always provide a `keywords` list of 5-15 synonyms, related terms, and alternative phrasings alongside your query to maximize recall.
  * `knowledge_base(action="read_file", file_path="...")` — Read the full content of a specific file. Use after search to get complete details. Supports fuzzy path matching.
  * `knowledge_base(action="list", category="all")` — List what's in the KB. Categories: 'all', 'key_files', 'directories', 'files'. Only use when the user asks "what's in this product" or you need a broad overview.
  * `knowledge_base(action="browse", path="/some/path")` — Browse the folder tree at a path. Like `ls` for the KB.
- **Strategy**: For most questions, a single `search` call with good keywords is enough. Only use `list` for broad discovery, `read_file` to drill into a specific file from search results, and `browse` to explore a directory.
- When calling search, always include a `keywords` list with synonyms and related terms. Example: query="authentication" → keywords=["auth", "login", "password", "credentials", "oauth", "token", "session", "security"].
"""


def _platform_label(platform: Optional[str]) -> str:
    """Return a human-readable OS label for the system prompt."""
    if not platform or not str(platform).strip():
        return ""
    p = str(platform).strip().lower()
    if p in ("darwin", "mac", "macos", "os x"):
        return "User platform: **macOS (darwin)**. Use Unix paths (e.g. ~/Desktop), .dmg/.zip for downloads, and commands appropriate for macOS."
    if p in ("win32", "windows", "win"):
        return "User platform: **Windows**. Use Windows paths (e.g. %USERPROFILE%\\Desktop), .exe/.msi for downloads, and commands appropriate for Windows."
    if p in ("linux", "linux2"):
        return "User platform: **Linux**. Use Unix paths (e.g. ~/Desktop) and commands appropriate for Linux."
    return f"User platform: **{platform}**. Use paths and commands appropriate for this OS."


def _build_system_prompt(
    product_name: str,
    tool_descriptions: str,
    product_description: Optional[str] = None,
    kb_summary: Optional[str] = None,
    max_iterations: int = 10,
    available_tool_names: Optional[list[str]] = None,
    user_platform: Optional[str] = None,
) -> str:
    sections: list[str] = []
    has_kb = available_tool_names is None or "knowledge_base" in (available_tool_names or [])

    user_platform_section = _platform_label(user_platform)
    if user_platform_section:
        user_platform_section = user_platform_section + "\n\n"

    if product_description:
        sections.append(f"## PRODUCT DESCRIPTION\n\n{product_description}")

    if kb_summary:
        sections.append(f"## PRODUCT KNOWLEDGE SUMMARY (from trained KB)\n\n{kb_summary}")

    if has_kb:
        if sections:
            sections.append(
                "This product has a trained knowledge base. Use `knowledge_base(action=\"search\", query=\"...\", keywords=[...])` "
                "to query it. For simple overview questions, the summary above may already contain the answer — respond directly without a tool call if so."
            )
        elif product_name and product_name != "General Assistant":
            sections.append(
                "This product has a trained knowledge base. Use `knowledge_base(action=\"search\", query=\"...\", keywords=[...])` "
                "to query it when you need specific information about the product."
            )
        else:
            sections.append(
                "No product is selected. You are operating as a general-purpose assistant. "
                "Use the available tools (terminal, file operations, web search, etc.) to help the user."
            )
    else:
        sections.append(
            "No knowledge base tool is available. "
            "Use the available tools (terminal, file operations, web search, etc.) to help the user."
        )

    product_desc_section = "\n\n".join(sections)

    return _AGENT_SYSTEM_TEMPLATE.format(
        product_name=product_name,
        tool_descriptions=tool_descriptions,
        product_description_section=product_desc_section,
        user_platform_section=user_platform_section,
        kb_rules_section=_KB_RULES if has_kb else "",
        max_iterations=max_iterations,
    )




# ---------------------------------------------------------------------------
# Gemini detection (for thought_signature / tool_call compatibility)
# ---------------------------------------------------------------------------

def _is_gemini_model(llm_settings: dict) -> bool:
    """Return True when the chat model is Google Gemini.

    Gemini thinking models require thought_signature on function calls.
    We avoid synthetic tool_calls for Gemini so the API does not reject the conversation.
    """
    api_url = (llm_settings.get("api_url") or "").strip()
    model_name = (llm_settings.get("model_name") or "").strip()
    return (
        "generativelanguage.googleapis.com" in api_url
        or "aiplatform.googleapis.com" in api_url
        or model_name.startswith("gemini")
    )


# ---------------------------------------------------------------------------
# LangChain model builder
# ---------------------------------------------------------------------------

def _build_langchain_model(llm_settings: dict) -> Any:
    """Create a LangChain ChatModel from ReTrace LLM settings."""
    provider = llm_settings.get("provider", "openai")
    api_key = llm_settings.get("api_key", "")
    model_name = llm_settings.get("model_name", app_settings.REASONING_MODEL)
    api_url = llm_settings.get("api_url")

    is_anthropic = provider == "anthropic" or (
        provider == "custom" and api_url and "anthropic.com" in api_url
    )
    if is_anthropic:
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            api_key=api_key,
            model=model_name,
        )
    else:
        # openai or custom — both use OpenAI-compatible API
        from langchain_openai import ChatOpenAI
        import httpx as _httpx
        kwargs: dict[str, Any] = {
            "api_key": api_key,
            "model": model_name,
            "timeout": 300,
            "http_client": None,
        }
        if api_url:
            kwargs["base_url"] = api_url
            # Custom/local LLM servers may be slow to respond — use generous timeouts
            kwargs["http_async_client"] = _httpx.AsyncClient(timeout=_httpx.Timeout(300.0, connect=30.0))
            # Disable thinking for local models (e.g. Qwen) — benchmarks show
            # no-thinking is faster with comparable or better accuracy on V2 tasks.
            # sglang uses chat_template_kwargs to toggle thinking mode.
            kwargs["extra_body"] = {"chat_template_kwargs": {"enable_thinking": False}}
        if llm_settings.get("default_headers"):
            kwargs["default_headers"] = llm_settings["default_headers"]
        return ChatOpenAI(**kwargs)


# ---------------------------------------------------------------------------
# Native tool names for hybrid mode (MCP Builder)
# ---------------------------------------------------------------------------

NATIVE_TOOL_NAMES = {"write_file", "str_replace", "read_file", "delete_file"}

# When MCP Builder is active, ALL tools should be native (no CodeAct sandbox)
MCP_BUILDER_NATIVE_TOOL_NAMES = {
    "write_file", "str_replace", "read_file", "delete_file",
    "terminal", "knowledge_base", "web_search", "web_fetch",
    "web_research", "web_advanced", "grep", "glob_search",
    "download_file", "todo_write",
}

# ---------------------------------------------------------------------------
# CodeAct graph builder (ported from langgraph_codeact/__init__.py)
# ---------------------------------------------------------------------------

def _build_codeact_graph(
    model: Any,
    tools: list[StructuredTool],
    system_prompt: str,
    max_iterations: int = 10,
    use_gemini_compat: bool = False,
    main_event_loop: Optional[asyncio.AbstractEventLoop] = None,
) -> StateGraph:
    """Build the LangGraph CodeAct agent graph.

    When use_gemini_compat is True (Gemini models), we avoid synthetic tool_calls
    and represent code execution as assistant text + user message with result,
    so Gemini never sees function_call parts that require thought_signature.

    Nodes:
      call_model — invoke LLM, extract Python code
      sandbox    — execute code with tools in scope

    Edges:
      START → call_model
      call_model →(code)→ sandbox
      call_model →(text)→ END
      sandbox → call_model
    """

    # Map tool names → callable functions for the sandbox.
    # Some tools are async-only (coroutine but no func).  The sandbox runs
    # inside exec() which is synchronous (in a worker thread), so we wrap
    # async coroutines to submit them to the MAIN FastAPI event loop via
    # run_coroutine_threadsafe.  This is critical because Playwright browser
    # sessions and WebSocket objects are bound to that main loop — creating
    # a new loop with asyncio.run() would cause cross-loop errors.
    def _wrap_async(coro_fn):
        """Return a sync wrapper that dispatches to the main event loop."""
        import functools

        @functools.wraps(coro_fn)
        def wrapper(*args, **kwargs):
            if main_event_loop and main_event_loop.is_running():
                # Submit the coroutine to the MAIN event loop (where
                # Playwright, WebSockets, and the browser manager live).
                future = asyncio.run_coroutine_threadsafe(
                    coro_fn(*args, **kwargs), main_event_loop
                )
                return future.result(timeout=120)
            else:
                # Fallback: create a new loop (shouldn't happen in practice)
                return asyncio.run(coro_fn(*args, **kwargs))
        return wrapper

    tools_context: dict[str, Any] = {}
    for tool in tools:
        if isinstance(tool, StructuredTool):
            if tool.func is not None:
                tools_context[tool.name] = tool.func
            elif tool.coroutine is not None:
                tools_context[tool.name] = _wrap_async(tool.coroutine)
            else:
                tools_context[tool.name] = tool
        else:
            # MCP adapter tools are async-only — wrap for sync sandbox
            if hasattr(tool, 'ainvoke'):
                def _make_sync_mcp_wrapper(t):
                    def sync_wrapper(**kwargs):
                        import concurrent.futures
                        try:
                            loop = asyncio.get_running_loop()
                        except RuntimeError:
                            loop = None
                        if loop and loop.is_running():
                            with concurrent.futures.ThreadPoolExecutor() as pool:
                                return pool.submit(asyncio.run, t.ainvoke(kwargs)).result(timeout=30)
                        else:
                            return asyncio.run(t.ainvoke(kwargs))
                    return sync_wrapper
                tools_context[getattr(tool, "name", str(tool))] = _make_sync_mcp_wrapper(tool)
            else:
                fn = getattr(tool, "func", None) or getattr(tool, "coroutine", None) or tool
                if asyncio.iscoroutinefunction(fn):
                    tools_context[getattr(tool, "name", str(tool))] = _wrap_async(fn)
                else:
                    tools_context[getattr(tool, "name", str(tool))] = fn

    # ── call_model node ──────────────────────────────────────────────
    def call_model(state: AgentState):
        current_iteration = state.get("current_iteration", 0) + 1
        max_iter = state.get("max_iterations", max_iterations)
        syntax_error_count = state.get("syntax_error_count", 0)

        # Guard: too many syntax errors
        if syntax_error_count >= 3:
            msg = AIMessage(content="I encountered multiple syntax errors. Stopping.")
            return {
                "messages": [msg],
                "current_iteration": current_iteration,
                "is_final_answer": True,
                "script": None,
                "syntax_error_count": 0,
            }

        # Guard: max iterations
        if current_iteration > max_iter:
            msg = AIMessage(content=f"Maximum iterations ({max_iter}) reached. Please simplify your request.")
            return {
                "messages": [msg],
                "current_iteration": current_iteration,
                "is_final_answer": True,
                "script": None,
            }

        messages = [{"role": "system", "content": system_prompt}] + state["messages"]

        response = model.invoke(messages)

        # Strip explanatory text from code responses to prevent echo loops
        if hasattr(response, "content") and isinstance(response.content, str) and "```" in response.content:
            stripped = strip_text_from_code_response(response.content)
            if stripped != response.content:
                response.content = stripped

        # Extract Python code
        raw_content = response.content if hasattr(response, "content") else str(response)
        # ChatAnthropic returns content as a list of blocks; convert to string
        if isinstance(raw_content, list):
            raw_content = "\n".join(
                block.get("text", "") if isinstance(block, dict) else str(block)
                for block in raw_content
            )
        code = extract_python_code(raw_content)

        # Fallback: model may use its native tool-call format (XML, JSON, bare call)
        if not code:
            tool_names = set(tools_context.keys())
            code = extract_tool_call_as_python(raw_content, known_tools=tool_names)

        if code:
            # Add synthetic tool_call for OpenAI message format compatibility.
            # Skip for Gemini: it requires thought_signature on function_call parts,
            # so we represent code execution as text + user message instead.
            if not use_gemini_compat:
                tool_call_id = f"code_exec_{uuid4().hex[:8]}"
                response.tool_calls = [{
                    "name": "code_execution",
                    "args": {},
                    "id": tool_call_id,
                }]
            return {
                "messages": [response],
                "script": code,
                "is_final_answer": False,
                "current_iteration": current_iteration,
            }
        else:
            return {
                "messages": [response],
                "script": None,
                "is_final_answer": True,
                "current_iteration": current_iteration,
            }

    # ── sandbox node ─────────────────────────────────────────────────
    def sandbox(state: AgentState):
        code = state.get("script", "")
        logger.info("sandbox_exec", code_preview=code[:500] if code else "(empty)")
        existing_context = state.get("context", {})
        exec_globals = {**existing_context, **tools_context}

        # Auto-capture: if the last statement is an expression (function call,
        # variable, etc.) that doesn't already use print(), wrap it so the
        # return value isn't silently discarded by exec().
        try:
            tree = ast.parse(code)
            if tree.body and isinstance(tree.body[-1], ast.Expr):
                # Last statement is a bare expression — wrap it to print result
                last_line = ast.get_source_segment(code, tree.body[-1])
                if last_line and "print(" not in last_line:
                    # Replace last expression with: _result_ = <expr>; print(_result_) if _result_ is not None
                    lines = code.rsplit(last_line, 1)
                    code = lines[0] + f"_result_ = {last_line}\nif _result_ is not None:\n    print(_result_)"
        except SyntaxError:
            pass  # Let the actual exec() handle syntax errors

        # Capture stdout
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                exec(code, exec_globals)
            output = buf.getvalue()
        except Exception:
            output = buf.getvalue() + "\n" + traceback.format_exc()

        # Limit output size
        if len(output) > 50_000:
            output = output[:50_000] + "\n[output truncated]"

        if not output.strip():
            output = "(no output)"

        # Track syntax errors
        syntax_error_count = state.get("syntax_error_count", 0)
        if "SyntaxError" in output:
            syntax_error_count += 1
        else:
            syntax_error_count = 0

        # Merge new variables into context (excluding tools, builtins,
        # and non-serializable types like modules, functions, classes)
        import types as _types
        _skip_types = (_types.ModuleType, _types.FunctionType, _types.BuiltinFunctionType, type)
        new_context = {k: v for k, v in exec_globals.items()
                       if k not in tools_context and not k.startswith("__")
                       and not isinstance(v, _skip_types)}

        # For Gemini we use a user message instead of ToolMessage so we never send
        # tool_call parts that lack thought_signature.
        if use_gemini_compat:
            return {
                "messages": [HumanMessage(content=f"Code execution result:\n\n{output.rstrip()}")],
                "context": {**existing_context, **new_context},
                "syntax_error_count": syntax_error_count,
            }

        # Build tool message (OpenAI/Anthropic path)
        tool_call_id = "fallback_code_exec"
        msgs = state.get("messages", [])
        if msgs:
            last = msgs[-1]
            tc = getattr(last, "tool_calls", [])
            if tc:
                tool_call_id = tc[0].get("id", tool_call_id) if isinstance(tc[0], dict) else getattr(tc[0], "id", tool_call_id)

        return {
            "messages": [ToolMessage(content=output.rstrip(), tool_call_id=tool_call_id, name="code_execution")],
            "context": {**existing_context, **new_context},
            "syntax_error_count": syntax_error_count,
        }

    # ── routing function ─────────────────────────────────────────────
    def should_continue(state: AgentState) -> str:
        if state.get("current_iteration", 0) >= state.get("max_iterations", max_iterations):
            return "END"
        if state.get("is_final_answer", False):
            return "END"
        if state.get("script"):
            return "EXECUTE"
        return "END"

    # ── build graph ──────────────────────────────────────────────────
    graph = StateGraph(AgentState)
    graph.add_node("call_model", call_model)
    graph.add_node("sandbox", sandbox)
    graph.add_edge(START, "call_model")
    graph.add_conditional_edges("call_model", should_continue, {
        "END": END,
        "EXECUTE": "sandbox",
    })
    graph.add_edge("sandbox", "call_model")

    return graph


# ---------------------------------------------------------------------------
# MCP Builder hybrid graph (native tool calls + CodeAct sandbox)
# ---------------------------------------------------------------------------

def _build_mcp_builder_graph(
    model: Any,
    tools: list[StructuredTool],
    system_prompt: str,
    max_iterations: int = 60,
    use_gemini_compat: bool = False,
) -> StateGraph:
    """Build the native-tool-calling LangGraph agent for MCP Builder.

    ALL tools are bound as native structured tools via model.bind_tools().
    No CodeAct sandbox — the LLM calls tools directly via JSON tool calls.
    This keeps agent chat untouched (uses _build_codeact_graph).
    """

    # ── ALL tools are native in MCP Builder (no CodeAct sandbox) ────
    native_tools: list[StructuredTool] = []
    for tool in tools:
        native_tools.append(tool)

    # Bind ALL tools to the model so the LLM calls them via structured JSON
    model_with_tools = model.bind_tools(native_tools) if native_tools else model

    # Map for executing native tool calls by name
    native_tools_by_name: dict[str, Any] = {}
    for tool in native_tools:
        fn = tool.func if tool.func is not None else tool.coroutine
        native_tools_by_name[tool.name] = fn

    # Empty sandbox context — not used in MCP Builder mode
    tools_context: dict[str, Any] = {}

    # ── call_model node ──────────────────────────────────────────────
    def call_model(state: AgentState):
        current_iteration = state.get("current_iteration", 0) + 1
        max_iter = state.get("max_iterations", max_iterations)
        syntax_error_count = state.get("syntax_error_count", 0)

        if syntax_error_count >= 3:
            msg = AIMessage(content="I encountered multiple syntax errors. Stopping.")
            return {
                "messages": [msg],
                "current_iteration": current_iteration,
                "is_final_answer": True,
                "script": None,
                "has_native_tool_calls": False,
                "syntax_error_count": 0,
            }

        if current_iteration > max_iter:
            msg = AIMessage(content=f"Maximum iterations ({max_iter}) reached.")
            return {
                "messages": [msg],
                "current_iteration": current_iteration,
                "is_final_answer": True,
                "script": None,
                "has_native_tool_calls": False,
            }

        messages = [{"role": "system", "content": system_prompt}] + state["messages"]
        response = model_with_tools.invoke(messages)

        # ── Log LLM response for debugging ─────────────────────────
        response_text = getattr(response, "content", "") or ""
        all_tc = getattr(response, "tool_calls", None) or []
        logger.info(
            "mcp_builder_llm_response",
            iteration=current_iteration,
            response_length=len(response_text),
            response_preview=response_text[:500] if response_text else "(empty)",
            tool_calls_count=len(all_tc),
            tool_calls=[{"name": tc.get("name"), "args_keys": list(tc.get("args", {}).keys())} for tc in all_tc[:10]],
        )

        # ── Check for native structured tool calls ─────────────────
        native_tc = getattr(response, "tool_calls", None) or []
        valid_native_tc = [tc for tc in native_tc if tc.get("name") in native_tools_by_name]

        if valid_native_tc:
            logger.info("mcp_builder_has_tool_calls", iteration=current_iteration, tools=[tc.get("name") for tc in valid_native_tc])
            return {
                "messages": [response],
                "script": None,
                "is_final_answer": False,
                "has_native_tool_calls": True,
                "current_iteration": current_iteration,
            }

        # ── No tool calls — treat as final answer ────────────────
        logger.info("mcp_builder_final_answer", iteration=current_iteration, answer_preview=response_text[:300] if response_text else "(empty)")
        return {
            "messages": [response],
            "script": None,
            "is_final_answer": True,
            "has_native_tool_calls": False,
            "current_iteration": current_iteration,
        }

    # ── execute_native_tools node ─────────────────────────────────────
    def execute_native_tools(state: AgentState):
        """Execute native structured tool calls (file operations) and return ToolMessages."""
        msgs = state.get("messages", [])
        if not msgs:
            return {"messages": [], "has_native_tool_calls": False}

        last_msg = msgs[-1]
        tool_calls = getattr(last_msg, "tool_calls", []) or []
        result_messages = []

        for tc in tool_calls:
            tc_name = tc.get("name", "")
            tc_args = tc.get("args", {})
            tc_id = tc.get("id", f"native_{uuid4().hex[:8]}")

            logger.info("mcp_builder_tool_exec", tool_name=tc_name, args_keys=list(tc_args.keys()), args_preview={k: str(v)[:100] for k, v in tc_args.items()})

            fn = native_tools_by_name.get(tc_name)
            if fn is None:
                result_messages.append(
                    ToolMessage(content=f"Error: unknown tool '{tc_name}'", tool_call_id=tc_id, name=tc_name)
                )
                continue

            try:
                if asyncio.iscoroutinefunction(fn):
                    # Async tool — run in event loop
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        import concurrent.futures
                        future = asyncio.run_coroutine_threadsafe(fn(**tc_args), loop)
                        result = future.result(timeout=120)
                    else:
                        result = asyncio.run(fn(**tc_args))
                else:
                    result = fn(**tc_args)
                output = str(result) if result is not None else "(no output)"
            except Exception:
                output = traceback.format_exc()

            if len(output) > 50_000:
                output = output[:50_000] + "\n[output truncated]"

            result_messages.append(
                ToolMessage(content=output.rstrip(), tool_call_id=tc_id, name=tc_name)
            )

        return {
            "messages": result_messages,
            "has_native_tool_calls": False,
        }

    # ── routing function ─────────────────────────────────────────────
    def should_continue(state: AgentState) -> str:
        if state.get("current_iteration", 0) >= state.get("max_iterations", max_iterations):
            return "END"
        if state.get("is_final_answer", False):
            return "END"
        if state.get("has_native_tool_calls", False):
            return "NATIVE_TOOLS"
        return "END"

    # ── build graph (no sandbox — all tools are native) ──────────────
    graph = StateGraph(AgentState)
    graph.add_node("call_model", call_model)
    graph.add_node("execute_native_tools", execute_native_tools)
    graph.add_edge(START, "call_model")
    graph.add_conditional_edges("call_model", should_continue, {
        "END": END,
        "NATIVE_TOOLS": "execute_native_tools",
    })
    graph.add_edge("execute_native_tools", "call_model")

    return graph


# ---------------------------------------------------------------------------
# Agent service (public API)
# ---------------------------------------------------------------------------

class AgentService:
    """Orchestrates LangGraph CodeAct agent execution."""

    async def execute_task(
        self,
        product_id: str,
        task: str,
        session: AsyncSession,
        max_iterations: int = 50,
        thread_id: Optional[str] = None,
        user_platform: Optional[str] = None,
        use_reasoning: bool = False,
        mcp_builder_config: Optional[dict] = None,
    ) -> AsyncIterator[str]:
        """Execute an agent task and yield SSE events.

        Yields lines in SSE format:  ``event: <type>\\ndata: <json>\\n\\n``
        """

        def _sse(event: str, data: Any) -> str:
            return f"event: {event}\ndata: {json.dumps(data)}\n\n"

        session_id = str(uuid4())
        if not thread_id:
            thread_id = str(uuid4())
        timings: dict[str, int] = {}
        t0 = time.time()

        try:
            # ── 1. Load settings and product in parallel ─────────────────
            yield _sse("agent_status", {"step": "init", "message": "Loading settings and product..."})
            from app.api.settings import get_active_llm_settings, llm_settings_blocking_message
            from app.db.database import async_session_maker
            from sqlalchemy import select
            from app.models.product import Product as ProductModel

            async def _fetch_product():
                if not product_id:
                    return ("General Assistant", None)
                async with async_session_maker() as db:
                    result = await db.execute(select(ProductModel).where(ProductModel.product_id == product_id))
                    product = result.scalar_one_or_none()
                    if not product:
                        return ("Unknown Product", None)
                    return (product.product_name, product.description)

            async def _fetch_kb_summary():
                if not product_id:
                    return None
                try:
                    from app.rag.kb_search import get_product_summary
                    return await get_product_summary(product_id)
                except Exception:
                    return None

            llm_settings, (product_name, product_description), kb_summary = await asyncio.gather(
                get_active_llm_settings(session),
                _fetch_product(),
                _fetch_kb_summary(),
            )

            block = llm_settings_blocking_message(llm_settings)
            if block:
                yield _sse("agent_error", {"detail": block})
                return

            # ── 2. Build LangChain model ──────────────────────────────
            yield _sse("agent_status", {"step": "init", "message": "Initializing model..."})
            chat_model = _build_langchain_model(llm_settings)

            # Also build an AsyncOpenAI client for web_research (needs async)
            import httpx as _httpx
            client_kwargs: dict[str, Any] = {
                "api_key": llm_settings["api_key"],
                "timeout": _httpx.Timeout(300.0, connect=30.0),
            }
            if llm_settings.get("api_url"):
                client_kwargs["base_url"] = llm_settings["api_url"]
            if llm_settings.get("default_headers"):
                client_kwargs["default_headers"] = llm_settings["default_headers"]
            async_llm_client = AsyncOpenAI(**client_kwargs)
            model_name = llm_settings.get("model_name", app_settings.REASONING_MODEL)

            # ── 3. Build tools (including knowledge base tool) ──────────
            yield _sse("agent_status", {"step": "init", "message": "Loading tools..."})
            from app.tools import get_all_tools, get_tool_descriptions

            # Configure web search (Serper API)
            from app.tools.web_search import configure_web_search
            configure_web_search(
                gateway_url=llm_settings.get("serper_gateway_url", ""),
                gateway_token=(
                    (llm_settings.get("serper_gateway_bearer") or llm_settings.get("serper_gateway_token") or "")
                    .strip()
                ),
                managed_bearer_key=(llm_settings.get("api_key") or "").strip(),
            )

            tools = get_all_tools(
                llm_client=async_llm_client,
                model=model_name,
                chat_model=chat_model,
                screenops_api_key=llm_settings.get("screenops_api_key", ""),
                screenops_model=llm_settings.get("screenops_model"),
                screenops_coord_fallback_model=llm_settings.get("screenops_coord_fallback_model"),
                screenops_api_url=llm_settings.get("screenops_api_url"),
                screenops_mouse_timeout=int(llm_settings.get("screenops_mouse_timeout", 30) or 30),
                screenops_image_scale=max(25, min(100, int(llm_settings.get("screenops_image_scale", 100) or 100))),
                product_id=product_id,
                product_description=product_description,
                api_key=llm_settings.get("api_key", ""),
                api_url=llm_settings.get("api_url"),
                conversation_id=thread_id,
            )
            # Filter by user-disabled tools (legacy KB names → disable knowledge_base)
            disabled = set((llm_settings.get("agent_tools_config") or {}).get("disabled") or [])
            if disabled & {"search_knowledge_base", "list_kb_entries", "read_kb_file", "browse_kb_structure"}:
                disabled = set(disabled) | {"knowledge_base"}
            tools = [t for t in tools if t.name not in disabled]

            # ── 3b. Load MCP tools from configured servers ────────────
            mcp_manager = None
            if not mcp_builder_config:  # skip for MCP builder itself
                try:
                    from app.services.mcp_client import get_mcp_tools_async
                    from app.models.mcp_tool_config import McpToolConfig
                    from app.db.database import async_session_maker
                    async with async_session_maker() as mcp_session:
                        result = await mcp_session.execute(
                            select(McpToolConfig).where(McpToolConfig.enabled == True)
                        )
                        mcp_configs = [c.to_dict() for c in result.scalars().all()]

                    if mcp_configs:
                        mcp_tools, mcp_manager = await get_mcp_tools_async(mcp_configs)
                        # Filter out disabled MCP tools
                        mcp_tools = [t for t in mcp_tools if t.name not in disabled]
                        tools.extend(mcp_tools)
                        logger.info("mcp_tools_loaded", count=len(mcp_tools))
                except Exception as e:
                    logger.warning("mcp_tools_load_failed", error=str(e))

            tool_desc = get_tool_descriptions(tools)
            tool_names = [t.name for t in tools]

            yield _sse("agent_tools", {"tools": tool_names, "count": len(tools)})
            timings["init_ms"] = int((time.time() - t0) * 1000)

            # ── 5. Build system prompt (includes KB summary and user platform) ─
            system_prompt = _build_system_prompt(
                product_name=product_name,
                tool_descriptions=tool_desc,
                product_description=product_description,
                kb_summary=kb_summary,
                max_iterations=max_iterations,
                available_tool_names=tool_names,
                user_platform=user_platform,
            )

            # ── 5b. MCP Builder mode — inject prompt supplement ──────────
            if mcp_builder_config:
                from app.skills.mcp_builder_prompt import build_mcp_builder_supplement_slim
                from app.services.mcp_builder_service import format_endpoints_as_brief, MCPBuilderConfig
                mcp_cfg = MCPBuilderConfig(**mcp_builder_config)
                mcp_output_dir = mcp_cfg.output_dir or f"~/mcp-servers/{product_name}"
                has_kb = bool(product_id and product_id.startswith("__mcp__"))
                is_external = bool(mcp_cfg.api_docs_url or mcp_cfg.api_docs_text)
                service_name = mcp_output_dir.rstrip("/").split("/")[-1]
                supplement = build_mcp_builder_supplement_slim(
                    output_dir=mcp_output_dir,
                    service_name=service_name,
                    is_external=is_external,
                    has_kb=has_kb,
                    api_docs_text=mcp_cfg.api_docs_text,
                    api_base_url=mcp_cfg.api_base_url,
                    auth_type=mcp_cfg.auth_type,
                    auth_details=mcp_cfg.auth_details,
                    selected_endpoints=mcp_cfg.selected_endpoints,
                )
                system_prompt += "\n\n" + supplement
                yield _sse("agent_status", {"step": "init", "message": "MCP Builder mode activated"})

            # ── 6. Build LangGraph agent (shared checkpointer for conversation memory) ─
            yield _sse("agent_status", {"step": "agent", "message": "Building agent graph..."})
            use_gemini_compat = _is_gemini_model(llm_settings)
            if mcp_builder_config:
                # MCP Builder: use hybrid graph (native tool calls for file ops)
                graph = _build_mcp_builder_graph(
                    chat_model, tools, system_prompt, max_iterations,
                    use_gemini_compat=use_gemini_compat,
                )
                agent = graph.compile()
            else:
                # Agent chat: use CodeAct-only graph
                graph = _build_codeact_graph(
                    chat_model, tools, system_prompt, max_iterations,
                    use_gemini_compat=use_gemini_compat,
                    main_event_loop=asyncio.get_running_loop(),
                )
                agent = graph.compile(checkpointer=_agent_checkpointer)

            # ── 7. Execute ────────────────────────────────────────────
            yield _sse("agent_status", {"step": "executing", "message": "Agent is working..."})
            t_exec = time.time()

            task_content = task
            if mcp_builder_config:
                from app.services.mcp_builder_service import format_endpoints_as_brief, MCPBuilderConfig
                mcp_cfg = MCPBuilderConfig(**mcp_builder_config)
                if mcp_cfg.selected_endpoints:
                    endpoints_brief = format_endpoints_as_brief(mcp_cfg, product_name)
                    task_content = endpoints_brief + "\n\n" + task_content
            if use_reasoning:
                task_content = "Think through this carefully step by step before giving your answer.\n\n" + task

            initial_state: AgentState = {
                "messages": [HumanMessage(content=task_content)],
                "script": None,
                "context": {},
                "current_iteration": 0,
                "max_iterations": max_iterations,
                "is_final_answer": False,
                "syntax_error_count": 0,
            }

            config = {
                "configurable": {"thread_id": thread_id},
                "recursion_limit": 150,
            }
            iteration = 0
            final_answer = ""

            # Run blocking agent.stream() in thread; yield chunks via queue
            chunk_queue: queue.Queue = queue.Queue()

            def run_stream():
                try:
                    for chunk in agent.stream(initial_state, config=config, stream_mode="updates"):
                        chunk_queue.put(chunk)
                except Exception as e:
                    err_msg = str(e)
                    # Replace internal framework errors with user-friendly messages
                    if "recursion" in err_msg.lower() and "limit" in err_msg.lower():
                        err_msg = (
                            f"Agent reached the maximum execution depth ({config.get('recursion_limit', 150)} steps). "
                            "The task may be too complex for a single request. "
                            "Try breaking it into smaller steps."
                        )
                    chunk_queue.put(("__error__", err_msg))
                chunk_queue.put(None)

            stream_thread = threading.Thread(target=run_stream, daemon=True)
            stream_thread.start()

            while True:
                chunk = await asyncio.get_event_loop().run_in_executor(None, chunk_queue.get)
                if chunk is None:
                    break
                if isinstance(chunk, tuple) and chunk[0] == "__error__":
                    raise RuntimeError(chunk[1])
                if not isinstance(chunk, dict):
                    continue

                for node_name, node_update in chunk.items():
                    if not isinstance(node_update, dict):
                        continue

                    # Track iteration count
                    ci = node_update.get("current_iteration")
                    if ci is not None:
                        iteration = ci

                    # Process complete messages emitted by this node
                    new_messages = node_update.get("messages", [])
                    for msg in new_messages:
                        msg_type = getattr(msg, "type", "unknown")
                        content = msg.content if hasattr(msg, "content") else str(msg)
                        # ChatAnthropic returns content as a list of blocks
                        if isinstance(content, list):
                            content = "\n".join(
                                block.get("text", "") if isinstance(block, dict) else str(block)
                                for block in content
                            )

                        if msg_type == "ai":
                            # Detect browser tool calls early to open workspace
                            ai_tool_calls = getattr(msg, "tool_calls", [])
                            for tc in ai_tool_calls:
                                tc_name = tc.get("name", "") if isinstance(tc, dict) else getattr(tc, "name", "")
                                if tc_name == "auto_browser":
                                    yield _sse("browser_navigate", {"url": "", "title": ""})
                                    break

                            # Complete AI response from call_model
                            code = extract_python_code(content)
                            if not code:
                                code = extract_tool_call_as_python(content, known_tools=set(tool_names))
                            if code:
                                yield _sse("agent_code", {
                                    "iteration": iteration,
                                    "code": code,
                                })
                            elif content and content.strip():
                                # Final text answer — stream word by word
                                final_answer = content
                                words = content.split(' ')
                                total = len(words)
                                chunk_size = 4
                                for wi in range(0, total, chunk_size):
                                    partial = ' '.join(words[:wi + chunk_size])
                                    yield _sse("agent_answer_chunk", {
                                        "chunk": partial,
                                        "done": False,
                                    })
                                    await asyncio.sleep(0.02)
                                yield _sse("agent_answer_chunk", {
                                    "chunk": content,
                                    "done": True,
                                })

                        elif msg_type == "tool":
                            tool_name = getattr(msg, "name", "") or ""
                            yield _sse("tool_output", {
                                "iteration": iteration,
                                "output": content[:5000],
                                "tool_name": tool_name,
                            })
                            # Auto-open browser workspace when browser tools run
                            if tool_name == "auto_browser":
                                try:
                                    import json as _json
                                    tool_data = _json.loads(content) if content else {}
                                    yield _sse("browser_navigate", {
                                        "url": tool_data.get("url", ""),
                                        "title": tool_data.get("title", ""),
                                    })
                                    # Emit rich events for analyze_page and screenshot_full_page
                                    tool_action = tool_data.get("action", "")
                                    if tool_action == "page_analysis":
                                        yield _sse("browser_analysis", {
                                            "iteration": iteration,
                                            "url": tool_data.get("url", ""),
                                            "page_height_px": tool_data.get("page_height_px", 0),
                                            "text_chars": tool_data.get("text_chars", 0),
                                            "extraction_options": tool_data.get("extraction_options", []),
                                            "next_steps": tool_data.get("next_steps", ""),
                                        })
                                    elif tool_action == "screenshot_full_page":
                                        yield _sse("browser_full_page_scan", {
                                            "iteration": iteration,
                                            "url": tool_data.get("url", ""),
                                            "num_tiles": tool_data.get("num_tiles", 0),
                                            "page_height_px": tool_data.get("page_height_px", 0),
                                            "hint": tool_data.get("hint", ""),
                                        })
                                except Exception:
                                    yield _sse("browser_navigate", {"url": "", "title": ""})

            timings["execution_ms"] = int((time.time() - t_exec) * 1000)
            timings["total_ms"] = int((time.time() - t0) * 1000)

            # ── 8. Cleanup MCP connections ─────────────────────────────
            if 'mcp_manager' in locals() and mcp_manager:
                await mcp_manager.cleanup()

            # ── 9. Done ───────────────────────────────────────────────
            yield _sse("agent_done", {
                "session_id": session_id,
                "thread_id": thread_id,
                "iterations": iteration,
                "timings": timings,
                "tools_used": tool_names,
            })

            # Persist session using a NEW short-lived DB session
            # (the request session may already be closed or locked)
            try:
                from app.db.database import async_session_maker
                from app.models.agent_session import AgentSession
                async with async_session_maker() as save_session:
                    save_session.add(AgentSession(
                        session_id=session_id,
                        product_id=product_id,
                        task=task,
                        status="completed",
                        thread_id=thread_id,
                        iterations=iteration,
                        final_answer=final_answer[:10_000] if final_answer else None,
                        token_usage_json=json.dumps(timings),
                        created_at=datetime.utcnow(),
                        completed_at=datetime.utcnow(),
                    ))
                    await save_session.commit()
            except Exception:
                logger.warning("agent_session_save_failed")

        except Exception as exc:
            # Cleanup MCP connections on error
            if 'mcp_manager' in locals() and mcp_manager:
                await mcp_manager.cleanup()
            logger.error("agent_execution_failed", error=str(exc), exc_info=True)
            yield _sse("agent_error", {"detail": str(exc)})

            # Persist failed session using a NEW short-lived DB session
            try:
                from app.db.database import async_session_maker
                from app.models.agent_session import AgentSession
                async with async_session_maker() as save_session:
                    save_session.add(AgentSession(
                        session_id=session_id,
                        product_id=product_id,
                        task=task,
                        status="failed",
                        thread_id=thread_id,
                        iterations=0,
                        error=str(exc),
                        created_at=datetime.utcnow(),
                        completed_at=datetime.utcnow(),
                    ))
                    await save_session.commit()
            except Exception:
                pass


# Shared checkpointer for conversation memory across requests
_agent_checkpointer = MemorySaver()


# Global instance
agent_service = AgentService()
