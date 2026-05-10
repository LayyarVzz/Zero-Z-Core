"""角色卡 — 加载 SillyTavern V3 兼容 JSON 角色卡，生成 system prompt。"""

import json
from pathlib import Path
from core.config import ROOT


class CharacterCard:
    """SillyTavern V3 角色卡加载器。

    加载 JSON 角色卡，对外提供 build_system() 和 build_prompt() 方法。
    忽略规范中未使用的字段（alternate_greetings、character_book、extensions 等）。
    """

    def __init__(self, path: str) -> None:
        filepath = Path(path)
        if not filepath.is_absolute():
            filepath = ROOT / filepath
        if not filepath.exists():
            raise FileNotFoundError(f"角色卡文件不存在: {filepath}")
        with open(filepath, "r", encoding="utf-8") as f:
            raw = json.load(f)

        if raw.get("spec") != "chara_card_v3":
            raise ValueError(
                f"不支持的角色卡规格: {raw.get('spec')}，需要 chara_card_v3"
            )

        self._data = raw["data"]

    @property
    def name(self) -> str:
        return self._data.get("name", "")

    @property
    def first_mes(self) -> str:
        return self._data.get("first_mes", "")

    @property
    def _system_prompt(self) -> str:
        return self._data.get("system_prompt", "")

    @property
    def _post_history_instructions(self) -> str:
        return self._data.get("post_history_instructions", "")

    @property
    def _description(self) -> str:
        return self._data.get("description", "")

    @property
    def _personality(self) -> str:
        return self._data.get("personality", "")

    @property
    def _scenario(self) -> str:
        return self._data.get("scenario", "")

    @property
    def _mes_example(self) -> str:
        return self._data.get("mes_example", "")

    def build_system(self, memories: list[dict] | None = None) -> str:
        """组装 system prompt（不含 post_history_instructions）。"""
        parts = []

        if self._system_prompt:
            parts.append(self._system_prompt)

        identity = f"你是{self.name}。{self._description}"
        if self._personality:
            identity += f"\n性格：{self._personality}"
        parts.append(identity)

        if self._scenario:
            parts.append(f"对话场景：{self._scenario}")

        if self._mes_example:
            parts.append(f"对话示例：\n{self._mes_example}")

        if memories:
            formatted = "\n".join(f"- {m['key']}: {m['value']}" for m in memories)
            parts.append(f"相关记忆：\n{formatted}")

        parts.append("回复要求：不要使用括号标注动作、表情或心理活动。")

        return "\n\n".join(parts)

    def build_prompt(self, user_text: str, history: list[dict[str, str]]) -> str:
        """组装 user prompt：历史 + 当前输入 + 尾部指令。"""
        lines: list[str] = []
        for msg in history:
            role_tag = "用户" if msg["role"] == "user" else "助手"
            lines.append(f"{role_tag}: {msg['content']}")
        lines.append(f"用户: {user_text}")
        lines.append("助手:")
        prompt = "\n".join(lines)

        if self._post_history_instructions:
            prompt += f"\n{self._post_history_instructions}"

        return prompt
