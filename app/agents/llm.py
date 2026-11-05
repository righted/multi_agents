"""给 ChatOpenAI 补一个 reasoning_content 字段，用来展示模型的思考过程"""

from langchain_openai import ChatOpenAI


class ReasoningChatOpenAI(ChatOpenAI):
    def _convert_chunk_to_generation_chunk(self, chunk, default_chunk_class, base_generation_info):
        generation = super()._convert_chunk_to_generation_chunk(
            chunk, default_chunk_class, base_generation_info
        )
        if generation is None:
            return generation
        try:
            delta = (chunk.get("choices") or [{}])[0].get("delta") or {}
            reasoning = delta.get("reasoning_content")
            if reasoning:
                generation.message.additional_kwargs["reasoning_content"] = reasoning
        except Exception:
            pass
        return generation
