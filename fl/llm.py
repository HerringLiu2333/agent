import os
from typing import Optional, Dict, Any

import dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

# Cached LLM instance and its configuration signature
_LLM_INSTANCE: Optional[ChatOpenAI] = None
_LLM_CONFIG: Optional[Dict[str, Any]] = None
DEFAULT_MODEL = "gpt-5-mini"


def _load_env() -> None:
    """Load environment variables from .env if present."""
    # Only load once; dotenv.load_dotenv is idempotent but we keep it explicit
    dotenv.load_dotenv(override=False)

    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL")

    if not api_key:
        raise EnvironmentError("OPENAI_API_KEY 未在环境变量或 .env 中找到")
    if not base_url:
        # 允许使用默认的官方端点；如果用户未提供，给出提示而不是强制失败
        # 也可以改为 raise 看需求
        pass


def _get_llm(**model_kwargs) -> ChatOpenAI:
    """Return a cached ChatOpenAI instance; rebuild when config changes.

    Config keys considered: model, temperature, (plus sorted extra kwargs).
    """
    global _LLM_INSTANCE, _LLM_CONFIG
    _load_env()

    model = model_kwargs.pop("model", DEFAULT_MODEL)
    temperature = model_kwargs.pop("temperature", 0)

    # Build a normalized config signature
    cfg = {"model": model, "temperature": temperature, **model_kwargs}
    # Ensure deterministic ordering for comparison
    cfg_signature = {k: cfg[k] for k in sorted(cfg.keys())}

    if _LLM_INSTANCE is None or _LLM_CONFIG != cfg_signature:
        _LLM_INSTANCE = ChatOpenAI(model=model, temperature=temperature, **model_kwargs)
        _LLM_CONFIG = cfg_signature
    return _LLM_INSTANCE


def send_message(message: str, system_prompt: Optional[str] = None, **model_kwargs) -> str:
    """发送用户消息到大模型并返回字符串回复。

    参数:
        message: 用户要发送的内容。
        system_prompt: 可选，上下文/角色设定。
        model_kwargs: 传给 ChatOpenAI 构造函数的额外参数（例如 temperature=0.7）。

    返回:
        模型的文本回复（str）。
    """
    llm = _get_llm(**model_kwargs)

    chat_messages = []
    if system_prompt:
        chat_messages.append(SystemMessage(content=system_prompt))
    chat_messages.append(HumanMessage(content=message))

    resp = llm.invoke(chat_messages)
    # resp 可能是 BaseMessage / AIMessage，取其 content
    return getattr(resp, "content", str(resp))


def send_message_from_file(file_path: str, system_prompt: Optional[str] = None, encoding: str = "utf-8", **model_kwargs) -> str:
    """读取指定文本文件内容并发送给模型。

    参数:
        file_path: 文本文件路径。
        system_prompt: 可选系统提示。
        encoding: 文件编码，默认 utf-8。
        model_kwargs: 传递给底层模型的参数。
    """
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"prompt 文件不存在: {file_path}")
    with open(file_path, 'r', encoding=encoding, errors='ignore') as f:
        content = f.read()
    return send_message(content, system_prompt=system_prompt, **model_kwargs)


__all__ = ["send_message", "send_message_from_file", "DEFAULT_MODEL"]
