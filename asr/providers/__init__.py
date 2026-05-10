"""ASR Provider 工厂 — 根据配置创建对应的 Provider 实例。"""
from asr.providers.paraformer.provider import ParaformerProvider

_PROVIDERS: dict[str, type] = {
    "paraformer": ParaformerProvider,
}


def create_provider(config: dict):
    """从配置创建 ASR Provider。"""
    name = config["provider"]
    cls = _PROVIDERS.get(name)
    if cls is None:
        raise ValueError(f"Unknown ASR provider: {name!r}. Available: {list(_PROVIDERS)}")
    return cls(**config.get(name, {}))
