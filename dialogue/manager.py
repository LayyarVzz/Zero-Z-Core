"""对话管理 — 会话上下文、人物性格、长期记忆。"""

from dialogue.personality import load_personality
from dialogue.memory import LongTermMemory


class DialogueManager:
    """对话管理器，负责组装 LLM 输入所需的完整上下文。

    三项职责：
    1. 人物性格 — 从 YAML 加载 system prompt（说话风格、角色设定）
    2. 对话历史 — 维护最近 N 轮 user/assistant 对话
    3. 长期记忆 — 关键词检索历史记忆，注入到 prompt 中
    """

    def __init__(
        self,
        personality_path: str = "data/characters/default.yaml",
        memory_path: str = "data/memory.json",
        max_history: int = 20,  # 保留最近 N 轮对话（每轮含 user + assistant 两条）
    ) -> None:
        self.persona = load_personality(personality_path)  # 角色设定 dict
        self.memory = LongTermMemory(memory_path)           # 长期记忆存储
        self.max_history = max_history
        self.history: list[dict[str, str]] = []             # 对话历史，每条 {"role": "user"/"assistant", "content": "..."}

    def build_prompt(self, user_text: str) -> tuple[str, str]:
        """组装完整的 LLM 输入，返回 (prompt, system) 元组。

        system = 人物性格 + 相关记忆 + TTS 指令
        prompt = 最近对话历史 + 当前用户输入 + "助手"（引导模型开始生成回复）
        """
        # system：人物性格作为基础上下文
        context = self.persona.get("personality", "")

        # 检索长期记忆中与当前输入相关的条目，追加到 system
        memories = self.memory.search(user_text)
        if memories:
            context += "\n\n相关记忆：\n" + "\n".join(f"- {m}" for m in memories)

        # 输出格式约束：不在 system 末尾追加长指令，改为一行简短提醒
        context += "\n\n回复时不要使用括号标注动作、表情或心理活动。"

        # prompt：截取最近 2N 条历史（因为每轮 2 条），保证不超 token 上限
        recent = self.history[-(self.max_history * 2) :]
        system = context
        prompt_parts = []
        for msg in recent:
            role_tag = "用户" if msg["role"] == "user" else "助手"
            prompt_parts.append(f"{role_tag}: {msg['content']}")
        prompt_parts.append(f"用户: {user_text}")
        prompt_parts.append("助手:")  # 引导模型以助手身份开始回复
        prompt = "\n".join(prompt_parts)

        return prompt, system

    def add_user(self, text: str) -> None:
        """记录用户消息到对话历史。"""
        self.history.append({"role": "user", "content": text})

    def add_assistant(self, text: str) -> None:
        """记录助手回复到对话历史。"""
        self.history.append({"role": "assistant", "content": text})

    def remember(self, key: str, value: str) -> None:
        """将重要信息存入长期记忆。"""
        self.memory.add(key, value)

    def get_greeting(self) -> str:
        """获取角色开场白（来自性格设置）。"""
        return self.persona.get("greeting", "")
