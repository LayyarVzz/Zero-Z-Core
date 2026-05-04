"""LLM 客户端 — 把 provider 包装进独立线程，通过队列与外部通信。"""

import asyncio
import queue
import threading

from core.events import SENTINEL
from core.config import load_config
from llm.base import LLMProvider
from llm.providers.openai_compatible import OpenAICompatibleProvider


class LLMClient:
    """LLM 客户端，运行在独立线程中。

    从 llm_queue 消费 (prompt, system) 元组，
    调用 provider 生成回复后放入 response_queue。
    """

    def __init__(
        self,
        llm_queue: queue.Queue,
        response_queue: queue.Queue,
        provider: LLMProvider,
        *,
        stream_mode: bool = False,
    ) -> None:
        self.llm_queue = llm_queue
        self.response_queue = response_queue
        self.provider = provider
        # 流式模式：逐个 token 推入队列；非流式：攒完整文本再推入
        self.stream_mode = stream_mode
        self._thread: threading.Thread | None = None
        self._running = False

    @classmethod
    def from_config(
        cls, llm_queue: queue.Queue, response_queue: queue.Queue
    ) -> "LLMClient":
        """工厂方法：从 config.yaml 读取 LLM 配置 -> 构造 Provider -> 构造本客户端。"""
        config = load_config()["llm"]
        provider = OpenAICompatibleProvider(
            base_url=config["base_url"],
            api_key=config["api_key"],
            model=config["model"],
            max_tokens=config.get("max_tokens", 512),
            temperature=config.get("temperature", 0.8),
        )
        return cls(
            llm_queue,
            response_queue,
            provider,
            stream_mode=config.get("stream_mode", False),
        )

    def cancel(self) -> None:
        """取消当前正在进行的 LLM 请求。"""
        self.provider.cancel()

    def start(self) -> None:
        """启动后台线程，在线程内创建事件循环并运行 _process。"""
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """协作式关闭：设标志位 -> 发 SENTINEL 唤醒阻塞的 get -> 等待线程退出。

        join(timeout=5.0) 防止无限等待，超时后线程会被 daemon 机制回收。
        """
        self._running = False
        self.provider.cancel()
        self.llm_queue.put(SENTINEL)
        if self._thread is not None:
            self._thread.join(timeout=5.0)

    def _run(self) -> None:
        """线程入口：创建独立 event loop -> 运行异步主循环 -> 结束后关闭 loop。

        每个线程不能复用主线程的 event loop，必须 new_event_loop。
        """
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._process())
        finally:
            try:
                pending = asyncio.all_tasks(loop)
                for task in pending:
                    task.cancel()
                if pending:
                    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            except Exception:
                pass
            loop.close()

    async def _process(self) -> None:
        """异步主循环：从 llm_queue 取 prompt -> 调 provider 生成 -> 结果放入 response_queue。

        流式模式下逐个 token 推入队列，token 之间下游可即时消费；
        非流式模式攒完整文本再一次性推入。
        收到 SENTINEL 哨兵或 _running=False 时退出。
        """
        while self._running:
            try:
                item = self.llm_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            if item is SENTINEL:
                break
            try:
                prompt, system = item
            except (ValueError, TypeError):
                print(f"[LLMClient] 收到格式错误的队列项: {item}")
                continue
            try:
                if self.stream_mode:
                    async for token in self.provider.generate_stream(
                        prompt, system=system
                    ):
                        self.response_queue.put(token)
                    # 流式结束发送 SENTINEL，下游据此判断一句话结束
                    self.response_queue.put(SENTINEL)
                else:
                    text = await self.provider.generate(prompt, system=system)
                    self.response_queue.put(text)
                    self.response_queue.put(SENTINEL)
                    # SENTINEL 放在流式和非流式末尾都有，下游用统一逻辑收
            except Exception as e:
                # 不同 Provider 可能抛出不同类型的异常，
                # 用前缀区分错误消息，便于 UI 层识别并走兜底文案
                self.response_queue.put(f"[LLM_ERROR] {e}")
                self.response_queue.put(SENTINEL)
