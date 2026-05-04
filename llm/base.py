"""LLM Provider 的抽象基类（ABC）"""

from abc import ABC, abstractmethod
from typing import AsyncGenerator


class LLMProvider(ABC):
    """对接任何 LLM API 的通用接口。"""

    @abstractmethod
    # * 是参数列表里的分隔符——它之后的参数只能用关键字传，不能按位置传
    async def generate(self, prompt: str, *, system: str = "") -> str:
        """非流式生成回复。"""
        ...

    @abstractmethod
    async def generate_stream(
        self, prompt: str, *, system: str = ""
    ) -> AsyncGenerator[str, None]:
        """流式生成回复，每次 yield 一个 token 片段。"""
        if False:
            yield ""

    @abstractmethod
    def cancel(self) -> None:
        """中断当前正在进行的生成。"""
        ...
