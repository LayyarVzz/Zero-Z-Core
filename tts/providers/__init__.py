"""TTS Provider 工厂 — 唯一入口，根据配置创建对应的 Provider 实例。"""

from tts.providers.gpt_sovits.provider import GPTSovitsProvider
from tts.providers.minimax.provider import MinimaxProvider

_PROVIDERS: dict[str, type] = {
    "gpt_sovits": GPTSovitsProvider,
    "minimax": MinimaxProvider,
}


def create_provider(config: dict):
    """从 tts 配置段创建 Provider 实例。

    config["provider"] 决定类型（如 "gpt_sovits"），
    对应的同名子段（如 config["gpt_sovits"]）作为 **kwargs 传入。
    """
    name = config["provider"]
    cls = _PROVIDERS.get(name)
    if cls is None:
        raise ValueError(
            f"Unknown TTS provider: {name!r}. Available: {list(_PROVIDERS)}"
        )
    return cls(**config.get(name, {}))
