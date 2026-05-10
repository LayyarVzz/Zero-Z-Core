"""对话管理 — 角色卡上下文、长期记忆、对话历史。"""

from dialogue.character_card import CharacterCard
from dialogue.memory import MemoryProvider


class DialogueManager:
    """对话管理器，负责组装 LLM 输入所需的完整上下文。

    三项职责：
    1. 角色卡 — CharacterCard 生成 system + user prompt
    2. 对话历史 — 维护最近 N 轮 user/assistant 对话
    3. 长期记忆 — 委托 MemoryProvider 做语义检索和自动提取
    """

    def __init__(
        self,
        card_path: str,
        memory: MemoryProvider,
        max_history: int = 20,
    ) -> None:
        self.card = CharacterCard(card_path)
        self.memory = memory
        self.max_history = max_history
        self.history: list[dict[str, str]] = []

    def build_prompt(self, user_text: str) -> tuple[str, str]:
        """组装 (prompt, system) 元组。"""
        memories = self.memory.search(user_text)
        system = self.card.build_system(memories)
        prompt = self.card.build_prompt(user_text, self._recent_history())
        return prompt, system

    def _recent_history(self) -> list[dict[str, str]]:
        return self.history[-(self.max_history * 2):]

    def add_user(self, text: str) -> None:
        self.history.append({"role": "user", "content": text})

    def add_assistant(self, text: str) -> None:
        self.history.append({"role": "assistant", "content": text})

    def remember_last_exchange(self) -> None:
        """提取最近一轮对话的关键信息并存入长期记忆。"""
        if len(self.history) < 2:
            return
        last_user = None
        last_assistant = None
        for msg in reversed(self.history):
            if msg["role"] == "assistant" and last_assistant is None:
                last_assistant = msg["content"]
            elif msg["role"] == "user" and last_user is None:
                last_user = msg["content"]
            if last_user and last_assistant:
                break
        if last_user and last_assistant:
            self.memory.extract_and_store(last_user, last_assistant)

    def get_greeting(self) -> str:
        return self.card.first_mes
