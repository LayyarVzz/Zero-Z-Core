"""
此实现兼容所有 OpenAI 接口。
这里默认使用的是DeepSeek-v4-flash模型
"""

from typing import AsyncGenerator

from openai import AsyncOpenAI
from openai.types.chat import (
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)
from llm.base import LLMProvider


class OpenAICompatibleProvider(LLMProvider):
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        max_tokens: int = 512,
        temperature: float = 0.8,
        timeout: float = 30.0,
    ) -> None:
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        # AsyncOpenAI 自动管理连接池、重试、SSE 解析，无需手写 httpx
        self._client = AsyncOpenAI(
            base_url=base_url.rstrip("/"),
            api_key=api_key,
            timeout=timeout,
        )
        # 协作式取消，设置后流式生成在下次迭代时退出
        self._cancel_flag = False

    async def generate(self, prompt: str, *, system: str = "") -> str:
        """非流式生成：发送完整请求 -> 等待全部响应 -> 返回完整文本。

        非流式请求无法在中途中断 HTTP 连接，但会在请求前后检查取消标志。
        """
        if self._cancel_flag:
            raise RuntimeError("生成已被取消")
        self._cancel_flag = False
        messages = self._build_messages(prompt, system)
        response = await self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            stream=False,
        )
        if self._cancel_flag:
            raise RuntimeError("生成已被取消")
        # SDK 保证结构正确，但类型标注为 str|None，做防御性检查
        if not response.choices:
            raise ValueError("API 返回了空的 choices")
        content = response.choices[0].message.content
        if content is None:
            raise ValueError("API 返回了空内容")
        return content.strip()

    async def generate_stream(
        self, prompt: str, *, system: str = ""
    ) -> AsyncGenerator[str, None]:
        """流式生成：SDK 内部处理 SSE 解析，每次迭代拿到已解析的 delta.content。

        cancel() 设标志位后，下一次迭代时 close 流并退出，
        底层 HTTP 连接由 SDK 自动回收。
        """
        self._cancel_flag = False
        messages = self._build_messages(prompt, system)
        # SDK 的 stream=True 返回 Stream 对象，内部已完成 SSE -> chunk 转换
        stream = await self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            stream=True,
        )
        async for chunk in stream:
            if self._cancel_flag:
                await stream.close()
                break
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta

    def cancel(self) -> None:
        """协作式取消：设标志位，流式循环在下次迭代时 close 并退出。"""
        self._cancel_flag = True

    def _build_messages(
        self, prompt: str, system: str
    ) -> list[ChatCompletionMessageParam]:
        """将 prompt 和 system 组装为 OpenAI 标准消息列表。"""
        messages: list[ChatCompletionMessageParam] = []
        if system:
            system_msg: ChatCompletionSystemMessageParam = {
                "role": "system",
                "content": system,
            }
            messages.append(system_msg)
        user_msg: ChatCompletionUserMessageParam = {
            "role": "user",
            "content": prompt,
        }
        messages.append(user_msg)
        return messages
