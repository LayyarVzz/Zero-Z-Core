# Zero-Z

AI 语音助手，Live2D 桌面宠物应用。

## 功能

- 麦克风语音输入 + 实时语音识别（ASR）
- 云端 TTS 语音合成，支持流式打断
- LLM 对话，支持角色卡切换和长期记忆
- PySide6 桌面悬浮窗 + Live2D 角色渲染

## 环境

- Python 3.12
- CUDA 12.8（本地 ASR 模型需要）
- Docker（长期记忆 Qdrant 需要，可选）

## 快速开始

```bash
uv sync

cp .env.example .env
# 编辑 .env 填写 API Key

cp data/config.example.yaml data/config.yaml
# 编辑 data/config.yaml 按需调整配置

# 长期记忆（可选）
docker compose up -d

# 启动
uv run python main.py
```

Live2D 模型放入 `data/models/` 目录，切换角色修改 `config.yaml` 中 `character.name` 和 `gui.model_path`。

## 架构

```
Python 单进程
+----------------------------------------+
|  PySide6 GUI（主线程）                   |
|  Live2D 渲染 / 音频播放 / 字幕 / 托盘    |
|         ^ 信号                           |
|         |                                |
|  StateBridge（QTimer 轮询 → Qt 信号）    |
|         ^                                |
|  Pipeline 线程（ASR -> LLM -> TTS）      |
+----------------------------------------+
```

## 配置

`data/config.yaml`：

- `llm` — DeepSeek API（兼容 OpenAI）
- `tts.provider` — `minimax` / `gpt_sovits`
- `asr.provider` — `paraformer`
- `asr.interrupt_mode` — `true` 打断 / `false` 非打断
- `character.name` — 切换角色（对应 `data/characters/{name}/card.json`）
- `character.memory.enabled` — 开启 / 关闭长期记忆

## 主要依赖

- PySide6 + live2d-py + PyOpenGL（GUI + Live2D 渲染）
- funasr（Paraformer-zh ASR）
- Qdrant（向量库，长期记忆）
- DeepSeek / MiniMax / DashScope API
