from langchain.messages import HumanMessage, ToolMessage
from langchain.agents import create_agent
from langchain.agents import AgentState
from langchain_openai import ChatOpenAI
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_tavily import TavilySearch
from langchain_community.utilities import SQLDatabase
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langchain.tools import tool
from langchain.tools import ToolRuntime
from langgraph.types import Command
from langgraph.checkpoint.memory import InMemorySaver
import sys, asyncio
import uuid
from dotenv import load_dotenv
import os

load_dotenv()


model =ChatOpenAI(
    model = os.getenv("LLM_MODEL_ID"),
    api_key = os.getenv("LLM_API_KEY"),
    base_url = os.getenv("LLM_BASE_URL")
)

client = MultiServerMCPClient(
 {
    "time": {
      "transport":"stdio",
      "command": "uvx",
      "args": [
        "mcp-server-time",
        "--local-timezone=Asia/Shanghai"
      ]
    },
    "soar-flight-booking-mcp": {
            "transport": "http",
            "url": "https://mcp.soar.flights"
    },
    "Tavily_Hikari": {
      "transport":"http",
      "url": "https://tavily.ivanli.cc/mcp",
      "headers": {
          "Authorization": f"Bearer {os.getenv("Tavily_Hikari_Token")}"
       }
    },
    "math": {
          "transport":"stdio",
          "command": sys.executable,
          "args": [
            r"D:\Learn\LangChain\my_learning\0303_02_MCP_自定义.py"
          ]
    }
 }
)



async def main():
    tools = await client.get_tools()
    Tavily_Hikari = await client.get_tools(server_name="Tavily_Hikari")

    thread_id = str(uuid.uuid4())

    config = {"configurable":{"thread_id": thread_id}}

    web_search = TavilySearch(
        max_results = 5,
        topic = "general"
    )

    db = SQLDatabase.from_uri(r"sqlite:///D:\Learn\LangChain\my_learning\Chinook.db")

    @tool
    def query_with_db(query: str):
        """根据用户提问查询数据库"""
        try:
            return db.run(query)
        except Exception as e:
            return f"查询数据库报错:{e}"

    agent_with_flight = create_agent(
        model = model,
        tools = tools,
        system_prompt = "你是一个航班助手,单次搜索不超过12次"
    )

    agent_with_search = create_agent(
        model = model,
        tools = Tavily_Hikari,
        system_prompt = "你是场地专家,你在指定的位置搜索满足要求的场地。单次搜索不超过12次"
    )

    agent_with_music =create_agent(
        model = model,
        tools = [query_with_db],
        system_prompt = "你是一个音乐大师,擅长为别人定制音乐歌单"
    )

    class WeddingState(AgentState):
        origin: str        #起点
        destination: str   #目的地
        number: str        #人数
        type: str          #音乐风格


    @tool
    def update_info(origin: str, destination: str, number: str, type: str, runtime: ToolRuntime):
        """根据对话信息更新状态"""
        return Command(
            update = {
                "origin": origin,
                "destination": destination,
                "number": number,
                "type": type,
                "messages": [ToolMessage("信息更新已经成功",tool_call_id = runtime.tool_call_id)]
            }
        )


    #把子agent变成工具
    @tool
    async def flight(runtime: ToolRuntime):
        """查询航班"""
        origin = runtime.state["origin"]
        destination = runtime.state["destination"]
        
        response = await agent_with_flight.ainvoke(
            {"messages": [HumanMessage(f"查询从{origin}到{destination}的航班")]}
        )

        return response["messages"][-1].content

    @tool
    def search(runtime: ToolRuntime):
        """"使用Tavily进行搜索"""
        destination = runtime.state["destination"]
        number = runtime.state["number"]

        response = agent_with_search.invoke(
            {"messages":[HumanMessage(f"对{destination}进行适合{number}婚礼场地的搜索")]})
        
        return response["messages"][-1].content

    @tool
    def music(runtime: ToolRuntime):
        """"在数据库中进行音乐歌单的筛选"""
        type = runtime.state["type"]
        
        response = agent_with_music.invoke(
            {"messages":[HumanMessage(f"安排{type}的音乐歌单")]})
        
        return response["messages"][-1].content

    async with AsyncSqliteSaver.from_conn_string("checkpoint.db") as checkpointer:
        await checkpointer.setup()   


        agent_main = create_agent(
            model = model,
            tools = [flight, search, music, update_info],
            state_schema= WeddingState,
            checkpointer = checkpointer,
            system_prompt = "你是婚礼协调员。你负责与用户沟通,找到更新状态所需的所有信息,并更新到state。一旦完成,你就可以委派任务了。将查找航班、搜索场地和策划播放列表的任务委派给您的专家Agent。当你收到他们的答案，为我设计一场完美的婚礼方案。"
        )

        response = await agent_main.ainvoke(
            {"messages": [HumanMessage("从成都出发,计划十二月中旬在云南香格里拉举办66人的婚礼,歌单得是pop和rnb")]},
            config = config
        )

        for message in response['messages']:
            message.pretty_print()

asyncio.run(main())

