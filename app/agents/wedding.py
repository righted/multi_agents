"""婚礼多智能体：主协调员 + 航班 / 场地 / 音乐三个子 agent"""

import asyncio
import os
import sys

from dotenv import load_dotenv
from langchain.agents import AgentState, create_agent
from langchain.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage
from langchain.tools import ToolRuntime, tool
from langchain_community.utilities import SQLDatabase
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_openai import ChatOpenAI
from langchain_tavily import TavilySearch
from langgraph.types import Command

from app.agents.llm import ReasoningChatOpenAI
from app.common.logger import logger, setup_logging
from app.db import cache_store

load_dotenv()
setup_logging()

CHINOOK_DB = os.getenv("CHINOOK_DB", r"D:\Learn\LangChain\my_learning\Chinook.db")
MATH_MCP = os.getenv("MATH_MCP", r"D:\Learn\LangChain\Learn\0303_02_MCP_自定义.py")
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL", "43200"))   # 航班等查询结果缓存 12 小时

# 单次对话里网页搜索连续失败的次数（按 thread_id 记），用来及时止损
_search_fail: dict[str, int] = {}

model = ReasoningChatOpenAI(
    model=os.getenv("LLM_MODEL_ID"),
    api_key=os.getenv("LLM_API_KEY"),
    base_url=os.getenv("LLM_BASE_URL"),
)

mcp_client = MultiServerMCPClient(
    {
        "time": {
            "transport": "stdio",
            "command": "uvx",
            "args": ["mcp-server-time", "--local-timezone=Asia/Shanghai"],
        },
        "soar-flight-booking-mcp": {
            "transport": "http",
            "url": "https://mcp.soar.flights",
        },
        "Tavily_Hikari": {
            "transport": "http",
            "url": os.getenv("TAVILY_MCP_URL", "https://tavily.ivanli.cc/mcp"),
            "headers": {"Authorization": f"Bearer {os.getenv('Tavily_Hikari_Token', '')}"},
        },
        "math": {
            "transport": "stdio",
            "command": sys.executable,
            "args": [MATH_MCP],
        },
    }
)

web_search = TavilySearch(max_results=5, topic="general")
db = SQLDatabase.from_uri(f"sqlite:///{CHINOOK_DB}")


class WeddingState(AgentState):
    origin: str        # 起点
    destination: str   # 目的地
    number: str        # 人数
    type: str          # 音乐风格
    date: str          # 婚期


async def _load_mcp_tools():
    """取 MCP 工具列表；连不上就降级，不让整个服务起不来。"""
    try:
        return await asyncio.wait_for(mcp_client.get_tools(), timeout=60)
    except Exception as exc:
        logger.warning(f"[MCP] 工具加载失败，本次只带内置工具: {exc}")
        return []


async def _load_server_tools(server_name: str, owner: str):
    """按服务名取工具，顺带把工具名登记到归属表里，界面上才能显示对专家名。"""
    try:
        tools = await asyncio.wait_for(mcp_client.get_tools(server_name=server_name), timeout=60)
    except Exception as exc:
        logger.warning(f"[MCP] {server_name} 加载失败: {exc}")
        return []

    for t in tools:
        _TOOL_OWNER.setdefault(t.name, owner)
    logger.info(f"[MCP] {server_name} 工具: {[t.name for t in tools]}")
    return tools


async def build_agent(checkpointer):
    """组装主 agent 和三个子 agent，checkpointer 从外面传进来。"""
    mcp_tools = await _load_mcp_tools()
    search_tools = await _load_server_tools("Tavily_Hikari", "场地专家")
    # 只用搜索这一个工具，extract / crawl / map / research 用不上，留着只会让模型乱选
    search_tools = [t for t in search_tools if t.name == "tavily_search"] or search_tools
    logger.info(f"[Agent] MCP 工具 {len(mcp_tools)} 个，搜索工具 {len(search_tools)} 个")

    @tool
    def query_with_db(query: str) -> str:
        """在 Chinook 音乐库里执行 SQL 查询"""
        try:
            return str(db.run(query))
        except Exception as exc:
            return f"查询数据库报错:{exc}"

    agent_with_flight = create_agent(
        model=model, tools=mcp_tools, system_prompt="你是一个航班助手,单次搜索不超过12次"
    )
    agent_with_search = create_agent(
        model=model,
        tools=search_tools or [web_search],       # 中转站连不上时退回自带的 Tavily 搜索
        system_prompt="你是场地专家,你在指定的位置搜索满足要求的场地。单次搜索不超过12次",
    )
    agent_with_music = create_agent(
        model=model,
        tools=[query_with_db],
        system_prompt="你是一个音乐大师,擅长为别人定制音乐歌单",
    )

    @tool
    def update_info(
        origin: str,
        destination: str,
        number: str,
        type: str,
        date: str,
        runtime: ToolRuntime,
    ):
        """根据对话信息更新婚礼状态，date 是婚期，写成 YYYY-MM-DD 或自然日期都行"""
        return Command(
            update={
                "origin": origin,
                "destination": destination,
                "number": number,
                "type": type,
                "date": date,
                "messages": [ToolMessage("信息更新已经成功", tool_call_id=runtime.tool_call_id)],
            }
        )

    @tool
    async def flight(runtime: ToolRuntime):
        """查询航班"""
        origin = runtime.state.get("origin")
        destination = runtime.state.get("destination")
        date = runtime.state.get("date") or ""
        if not origin or not destination:
            return "还没拿到出发地和目的地，请先用 update_info 记录信息再委派。"

        key = f"flight:{origin}->{destination}:{date}"
        cached = cache_store.get(key, CACHE_TTL_SECONDS)
        if cached:
            logger.info(f"[缓存] 命中 {key}")
            return cached

        ask = f"查询{date + ' ' if date else ''}从{origin}到{destination}的航班"
        logger.info(f"[航班] {ask}")
        try:
            response = await agent_with_flight.ainvoke({"messages": [HumanMessage(ask)]})
            text = response["messages"][-1].content
            cache_store.put(key, text)
            return text
        except Exception as exc:
            logger.warning(f"[航班专家] 失败: {exc}")
            return f"航班查询暂时不可用（{type(exc).__name__}），可以先跳过航班部分。"

    @tool
    async def search(runtime: ToolRuntime):
        """搜索婚礼场地"""
        destination = runtime.state.get("destination")
        number = runtime.state.get("number")
        date = runtime.state.get("date") or ""
        if not destination or not number:
            return "还没拿到目的地或人数，请先用 update_info 记录信息再委派。"
        tid = ((runtime.config or {}).get("configurable") or {}).get("thread_id", "")
        fails = _search_fail.get(tid, 0)
        if fails >= 2:
            return "网页搜索额度已用完，不要再调用搜索，直接根据已有信息给出建议并说明数据可能不完整。"

        last_exc = None
        for attempt in range(2):                 # 中转站的 SSE 连接偶尔会断，失败重试一次
            try:
                response = await agent_with_search.ainvoke(
                    {
                        "messages": [
                            HumanMessage(
                                f"对{destination}进行适合{number}人{date + '、' if date else ''}婚礼场地的搜索"
                            )
                        ]
                    }
                )
                text = response["messages"][-1].content
                if "Error 432" in text or "quota" in text.lower():
                    _search_fail[tid] = fails + 1
                return text
            except Exception as exc:
                last_exc = exc
                logger.warning(f"[场地专家] 第 {attempt + 1} 次失败: {exc}")

        _search_fail[tid] = fails + 1
        return f"场地搜索暂时不可用（{type(last_exc).__name__}），可以先跳过场地部分。"

    @tool
    async def music(runtime: ToolRuntime):
        """安排音乐歌单"""
        style = runtime.state.get("type")
        if not style:
            return "还没拿到音乐风格，请先用 update_info 记录信息再委派。"
        try:
            response = await agent_with_music.ainvoke(
                {"messages": [HumanMessage(f"安排{style}的音乐歌单")]}
            )
            return response["messages"][-1].content
        except Exception as exc:
            logger.warning(f"[音乐专家] 失败: {exc}")
            return f"歌单挑选暂时不可用（{type(exc).__name__}），可以先跳过音乐部分。"

    return create_agent(
        model=model,
        tools=[flight, search, music, update_info],
        state_schema=WeddingState,
        checkpointer=checkpointer,
        system_prompt=(
            "你是婚礼协调员。你负责与用户沟通,找到更新状态所需的所有信息,并更新到state。"
            "需要问清出发地、目的地、人数、婚礼风格和婚期,问清后用 update_info 一次性记录,婚期放进 date。"
            "一旦完成,你就可以委派任务了。将查找航班、搜索场地和策划播放列表的任务委派给您的专家Agent。"
            "当你收到他们的答案，为我设计一场完美的婚礼方案。"
        ),
    )


_NAMES = {"flight": "航班专家", "search": "场地专家", "music": "音乐专家", "tools": "工具"}

# 子 agent 内部调用的工具，按工具名反推属于哪位专家
_TOOL_OWNER = {
    "soar_search_flights": "航班专家",
    "search_flights": "航班专家",
    "cheapest_dates": "航班专家",
    "analyze_layovers": "航班专家",
    "rank_options": "航班专家",
    "find_optimal_path": "航班专家",
    "compare_offers": "航班专家",
    "search_airports": "航班专家",
    "tavily_search": "场地专家",
    "tavily_search_results_json": "场地专家",
    "query_with_db": "音乐专家",
    "list_tables": "音乐专家",
}


def _owner(tool_name: str, fallback: str) -> str:
    return _NAMES.get(tool_name) or _TOOL_OWNER.get(tool_name) or fallback


def _event(payload: dict) -> str:
    import json

    return json.dumps(payload, ensure_ascii=False) + "\n"


def _who(namespace) -> str:
    if not namespace:
        return "协调员"
    first = str(namespace[0]).split(":")[0]
    return _NAMES.get(first, first)


def _shorten(value, limit: int = 1500) -> str:
    text = str(value).replace("\r", " ").strip()
    return text if len(text) <= limit else text[:limit] + "…"


def _summarize(value) -> str:
    """把工具返回压成一句人话，避免把整段 JSON 摊在界面上。"""
    import ast
    import json

    text = str(value).strip()
    if "Error 432" in text:
        return "搜索额度不足"
    if text.startswith("{'error'") or text.startswith('{"error"'):
        return "工具报错"
    data = None
    try:
        data = json.loads(text)
    except Exception:
        try:
            data = ast.literal_eval(text)      # 有些工具返回的是 Python repr，比如 [(1, 'Rock'), ...]
        except Exception:
            return text.replace("\n", " ")[:60] or "（空）"

    if isinstance(data, list):
        return f"返回 {len(data)} 条"
    if isinstance(data, dict):
        for key in ("results", "data", "items", "records"):
            if isinstance(data.get(key), list):
                return f"返回 {len(data[key])} 条"
        keys = list(data.keys())[:4]
        return "返回 " + "、".join(keys) if keys else "返回空对象"
    return str(data)[:40]


async def chat_stream(agent, message: str, thread_id: str):
    """流式输出：文本 + 思考 + 工具调用事件，按 NDJSON 一行一个事件推给前端。"""
    import time

    config = {"configurable": {"thread_id": thread_id}}
    started: dict[str, float] = {}
    current_tool = {"name": ""}          # 主图当前在跑哪个工具，用来给子 agent 归属
    buf: dict[str, list[str]] = {}       # 子 agent 的思考先攒着，攒够一段再发
    _search_fail.pop(thread_id, None)

    def label(namespace) -> str:
        if not namespace:
            return "协调员"
        name = current_tool["name"]
        if name in _NAMES:
            return _NAMES[name]
        return "工具"

    try:
        async for item in agent.astream(
            {"messages": [HumanMessage(message)]},
            config,
            stream_mode="messages",
            subgraphs=True,          # 子 agent 的事件也一起冒出来
        ):
            namespace, payload = item if len(item) == 2 else ((), item)
            chunk, _metadata = payload
            who = label(namespace)

            if isinstance(chunk, AIMessageChunk):
                reasoning = (chunk.additional_kwargs or {}).get("reasoning_content")
                if reasoning:
                    if not namespace:
                        yield _event({"type": "think", "who": "协调员", "text": reasoning})
                    else:
                        parts = buf.setdefault(who, [])
                        parts.append(reasoning)
                        if sum(len(p) for p in parts) >= 120:      # 攒够 120 字再发，省事件数
                            yield _event({"type": "think", "who": who, "text": "".join(parts)})
                            parts.clear()

                for call in chunk.tool_call_chunks or []:
                    if call.get("name"):
                        key = call.get("id") or call["name"]
                        started.setdefault(key, time.monotonic())
                        if not namespace:
                            current_tool["name"] = call["name"]
                        yield _event(
                            {"type": "tool", "who": _owner(call["name"], who), "name": call["name"]}
                        )
                    if call.get("args"):
                        yield _event({"type": "args", "frag": call["args"]})

                if chunk.content and not namespace:      # 只留主 agent 的正文，子 agent 的杂音滤掉
                    text = chunk.content if isinstance(chunk.content, str) else str(chunk.content)
                    yield _event({"type": "text", "text": text})

            elif isinstance(chunk, ToolMessage):
                name = chunk.name or ""
                key = chunk.tool_call_id or name
                elapsed = time.monotonic() - started.pop(key, time.monotonic())
                logger.info(f"[工具] {name} 耗时 {elapsed:.2f}s")
                if not namespace:
                    current_tool["name"] = ""
                for who_left, parts in buf.items():        # 把子 agent 没发完的思考补上
                    if parts:
                        yield _event({"type": "think", "who": who_left, "text": "".join(parts)})
                        parts.clear()
                yield _event(
                    {
                        "type": "result",
                        "who": _owner(name, who),
                        "name": name,
                        "summary": _summarize(chunk.content),
                        "detail": _shorten(chunk.content),
                        "ms": int(elapsed * 1000),
                    }
                )
    except Exception as exc:                              # 出错也别把连接掐断，给前端一条提示
        logger.exception("对话流中断")
        yield _event({"type": "text", "text": f"\n[执行出错] {type(exc).__name__}: {exc}"})


async def get_messages(checkpointer, thread_id: str) -> list[dict[str, str]]:
    """按 thread_id 取回历史消息。"""
    snapshot = await checkpointer.aget_tuple({"configurable": {"thread_id": thread_id}})
    if not snapshot:
        return []

    channel_values = snapshot.checkpoint.get("channel_values") or {}
    messages = channel_values.get("messages") or []

    result: list[dict[str, str]] = []
    for msg in messages:
        if not msg.content:
            continue
        if isinstance(msg, HumanMessage):
            result.append({"role": "user", "content": msg.content})
        elif isinstance(msg, AIMessage):
            result.append({"role": "assistant", "content": msg.content})
    return result


async def clear_messages(checkpointer, thread_id: str):
    """删掉这个会话的全部检查点。"""
    await checkpointer.adelete_thread(thread_id)
