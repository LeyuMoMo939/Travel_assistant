"""LLM 客户端"""
from functools import lru_cache
from langchain_openai import ChatOpenAI
from app.config import get_settings

@lru_cache
def get_llm(temperature: float = 0.3) -> ChatOpenAI:
    """获取 LLM 客户端"""
    s = get_settings()
    if not s.llm_api_key:
        raise ValueError("LLM_API_KEY 未配置,请在 .env 中填写")

    # thinking 是 DeepSeek 专有参数。发给 OpenAI / 智谱 等端点会被判为
    # 未知参数直接 400,所以只在 base_url 确实指向 DeepSeek 时才附带。
    # 思考型模型(如 deepseek-v4-pro)默认开启思考,而思考模式不支持
    # 强制 tool_choice(结构化输出依赖它),所以要显式关掉。想开推理就在
    # .env 里设 LLM_THINKING=true(代价见 .env.example 的说明)。
    extra_body = {}
    if not s.llm_thinking and "deepseek" in (s.llm_base_url or "").lower():
        extra_body = {"thinking": {"type": "disabled"}}

    return ChatOpenAI(
        api_key=s.llm_api_key,
        base_url=s.llm_base_url,
        model=s.llm_model,
        temperature=temperature,
        timeout=120,      # 规划节点要生成大 JSON,给足时间但不无限等
        max_retries=2,    # 限流/网络抖动时 SDK 自动重试
        extra_body=extra_body,
    )
