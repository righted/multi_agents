"""把较早的对话压成一份纪要，供后续继续对话时使用"""

from langchain.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.common.logger import logger

PROMPT = """你在整理一段婚礼策划对话的纪要，之后会用它代替原文继续对话。
要求：
1. 只写已经发生的事实和结论，不要编造。
2. 按四块写：已确定、已否决（附原因）、未决问题、已产出物。
3. 总长不超过 600 字，用简洁的中文短句。
4. 下面这些字段以系统记录为准，与对话冲突时以它为准：{facts}
5. 用户希望重点保留：{focus}
"""


async def summarize(model: ChatOpenAI, transcript: str, facts: dict, focus: str = "") -> str:
    messages = [
        SystemMessage(content=PROMPT.format(facts=facts or "无", focus=focus or "无")),
        HumanMessage(content=transcript[:20000]),
    ]
    try:
        resp = await model.ainvoke(messages)
        return str(resp.content).strip()
    except Exception as exc:
        logger.warning(f"[压缩] 生成纪要失败: {exc}")
        return ""
