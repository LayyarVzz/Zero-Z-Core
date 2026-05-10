# Zero-Z

AI 语音助手，Live2D 数字人桌面应用。

## 功能

- 麦克风语音输入 + 实时语音识别（ASR）
- 本地 / 云端 TTS 语音合成，支持流式打断
- LLM 对话，支持角色卡切换和长期记忆
- PySide6 桌面 GUI + Live2D 角色展示

## 环境

- Python 3.12+
- CUDA 12.8（本地 ASR / TTS 模型需要）
- Docker（长期记忆 Qdrant 需要，可选）

## 快速开始

```bash
# 安装依赖
uv sync

# 配置
cp .env.example .env
cp data/config.example.yaml data/config.yaml

# 填写 API Key（编辑 .env）
# DEEPSEEK_API_KEY=...
# MINIMAX_API_KEY=...

# 启动长期记忆（可选，不启动则自动降级）
docker compose up -d

# 运行
uv run python main.py
```

## 配置

`data/config.yaml`：

- `llm` — DeepSeek API（兼容 OpenAI）
- `tts.provider` — `minimax` / `gpt_sovits`
- `asr.provider` — `paraformer`
- `character.name` — 切换角色
- `character.memory.enabled` — 开启 / 关闭长期记忆

## 主要依赖

- PyTorch 2.11 + CUDA 12.8
- funasr（Paraformer-zh ASR）
- sounddevice（音频采集 / 播放）
- PySide6（GUI）
- Qdrant（向量库，长期记忆）
- DeepSeek / MiniMax / DashScope API
