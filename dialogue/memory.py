"""长期记忆 — LLM 自动提取 + Qwen text-embedding-v4 向量化 + Qdrant 语义检索。"""

import json
import uuid
import datetime
from abc import ABC, abstractmethod
from pathlib import Path

from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue

from core.config import ROOT, load_config


class MemoryProvider(ABC):
    """记忆提供者抽象基类 — LongTermMemory 和 NoopMemory 的共同接口。"""

    @abstractmethod
    def extract_and_store(self, user_text: str, assistant_text: str) -> None:
        ...

    @abstractmethod
    def search(self, query: str, limit: int = 5, score_threshold: float = 0.5) -> list[dict]:
        ...

_EXTRACTION_PROMPT = """从以下对话中提取值得长期记住的关键信息。只提取事实性信息，不提取临时话题或闲聊。

应提取的类型：
- 用户个人信息（姓名、年龄、职业、所在地等）
- 用户的喜好与厌恶
- 用户的重要经历和事件
- 用户明确要求记住的内容

不提取的内容：
- 当次对话的临时话题
- 日常寒暄
- 没有信息量的闲聊

输出 JSON 数组，无新事实时输出空数组 []：
[{"key": "简短描述", "value": "具体内容"}, ...]

对话：
{dialogue}

JSON 输出："""


class LongTermMemory(MemoryProvider):
    """长期记忆管理器。

    三项职责：
    1. extract() — 调 LLM 从对话中提取关键事实
    2. search() — Qwen embedding → Qdrant 语义检索
    3. 自动去重 — 同名 key 覆盖旧值
    """

    def __init__(
        self,
        llm_base_url: str,
        llm_api_key: str,
        llm_model: str,
        embedding_api_key: str,
        embedding_base_url: str,
        embedding_model: str = "text-embedding-v4",
        qdrant_url: str = "http://localhost:6333",
        collection_name: str = "zero_memories",
        max_entries: int = 100,
    ) -> None:
        # LLM 提取用
        self._llm_client = OpenAI(base_url=llm_base_url, api_key=llm_api_key)
        self._llm_model = llm_model

        # Embedding
        self._emb_client = OpenAI(base_url=embedding_base_url, api_key=embedding_api_key)
        self._emb_model = embedding_model

        # Qdrant
        self._qdrant = QdrantClient(url=qdrant_url)
        self._collection = collection_name
        self._max_entries = max_entries
        self._ensure_collection()

    def _ensure_collection(self) -> None:
        """创建 collection（如不存在），向量维度 1024，Cosine 距离。"""
        if not self._qdrant.collection_exists(self._collection):
            self._qdrant.create_collection(
                collection_name=self._collection,
                vectors_config=VectorParams(size=1024, distance=Distance.COSINE),
            )

    def extract_and_store(self, user_text: str, assistant_text: str) -> None:
        """从一轮对话中提取关键事实，去重后写入 Qdrant。"""
        dialogue = f"用户: {user_text}\n助手: {assistant_text}"
        facts = self._extract(dialogue)
        if not facts:
            return

        for fact in facts:
            key = fact.get("key", "").strip()
            value = fact.get("value", "").strip()
            if not key or not value:
                continue

            # 去重：同名 key → 先删旧再插入
            self._qdrant.delete(
                collection_name=self._collection,
                points_selector=Filter(
                    must=[FieldCondition(key="key", match=MatchValue(value=key))]
                ),
            )

            # 向量化
            embedding = self._embed(f"{key}: {value}")

            # 写入
            self._qdrant.upsert(
                collection_name=self._collection,
                points=[
                    PointStruct(
                        id=str(uuid.uuid4()),
                        vector=embedding,
                        payload={
                            "key": key,
                            "value": value,
                            "timestamp": datetime.datetime.now().isoformat(),
                        },
                    )
                ],
            )

        # 维持上限
        count = self._qdrant.count(self._collection).count
        if count > self._max_entries:
            # 滚动淘汰最旧的条目
            excess = count - self._max_entries
            records, _ = self._qdrant.scroll(
                collection_name=self._collection,
                limit=excess,
                with_payload=True,
                with_vectors=False,
            )
            old_ids = [r.id for r in records if r.payload]
            if old_ids:
                self._qdrant.delete(
                    collection_name=self._collection,
                    points_selector=old_ids,
                )

    def search(self, query: str, limit: int = 5, score_threshold: float = 0.5) -> list[dict]:
        """语义检索 top-N 相关记忆。"""
        if self._qdrant.count(self._collection).count == 0:
            return []

        embedding = self._embed(query)
        results = self._qdrant.search(
            collection_name=self._collection,
            query_vector=embedding,
            limit=limit,
            score_threshold=score_threshold,
        )

        return [
            {"key": r.payload["key"], "value": r.payload["value"]}
            for r in results
            if r.payload
        ]

    def _extract(self, dialogue: str) -> list[dict]:
        """调 LLM 提取关键事实，返回 [{key, value}, ...] 或空列表。"""
        try:
            response = self._llm_client.chat.completions.create(
                model=self._llm_model,
                messages=[
                    {"role": "system", "content": "你是一个信息提取助手。只输出 JSON 数组，不要输出其他内容。"},
                    {"role": "user", "content": _EXTRACTION_PROMPT.replace("{dialogue}", dialogue)},
                ],
                temperature=0.1,
                max_tokens=512,
            )
            text = response.choices[0].message.content.strip()
            # 清理可能的 markdown 代码块包裹
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            facts = json.loads(text)
            if isinstance(facts, list):
                return facts
        except Exception as e:
            print(f"[Memory] 信息提取失败: {e}")
        return []

    def _embed(self, text: str) -> list[float]:
        """调 Qwen embedding API 返回 1024 维向量。"""
        response = self._emb_client.embeddings.create(
            model=self._emb_model,
            input=text,
            dimensions=1024,
            encoding_format="float",
        )
        return response.data[0].embedding


class NoopMemory(MemoryProvider):
    """空操作记忆管理器 — 关闭长期记忆功能时使用，所有方法直接返回。"""

    def extract_and_store(self, user_text: str, assistant_text: str) -> None:
        pass

    def search(self, query: str, limit: int = 5, score_threshold: float = 0.5) -> list[dict]:
        return []
