# Zero-Z

AI 语音助手，Live2D 桌面宠物应用。

## 功能

- 麦克风语音输入 + 实时语音识别（ASR）
- 本地 / 云端 TTS 语音合成，支持流式打断
- LLM 对话，支持角色卡切换和长期记忆
- Electron 桌面悬浮窗 + Live2D 角色渲染 + 流式字幕

## 环境

- Python 3.12+
- Node.js 20.19+
- CUDA 12.8（本地 ASR / TTS 模型需要）
- Docker（长期记忆 Qdrant 需要，可选）

## 快速开始

### 1. 前端（Electron + Vue3）

```bash
cd frontend
npm install
```

将 Live2D 模型放入 `frontend/public/models/` 目录（`.model3.json`、`.moc3` 及贴图文件）。

### 2. 后端（Python）

```bash
uv sync

cp .env.example .env
# 编辑 .env 填写 API Key：
#   DEEPSEEK_API_KEY=...
#   MINIMAX_API_KEY=...
#   DASHSCOPE_API_KEY=...

cp data/config.example.yaml data/config.yaml
# 编辑 data/config.yaml 按需调整配置

# 启动长期记忆（可选，不启动则自动降级）
docker compose up -d
```

### 3. 启动

**终端 1 — Python 后端：**

```bash
uv run python main.py
```

后端启动后输出：`[WsServer] Listening on ws://127.0.0.1:9527/ws`

**终端 2 — Electron 前端：**

```bash
cd frontend
npm run dev
```

桌面右下角出现 Live2D 悬浮窗，托盘图标出现，即可开始对话。

## 架构

```
Electron 前端                      Python 后端
(electron-vite + Vue3)             (WebSocket 服务)

🎤 getUserMedia ─┐                ┌── VAD → ASR → LLM → TTS
                 │                │
   AudioContext ←┼── WebSocket ───┼── Orchestrator
   Live2D 渲染   │   /ws          │
   流式字幕       │                │
   系统托盘 ─────┘                └── 配置 + 长期记忆
```

前端负责所有 I/O（麦克风采集 + 音频播放 + Live2D 渲染），后端通过 WebSocket 双向通信，保持现有 ASR/LLM/TTS 管道不变。

## 配置

`data/config.yaml`：

- `llm` — DeepSeek API（兼容 OpenAI）
- `tts.provider` — `minimax` / `gpt_sovits`
- `asr.provider` — `paraformer`
- `asr.interrupt_mode` — `true` 打断 / `false` 非打断
- `character.name` — 切换角色（对应 `data/characters/{name}/card.json`）
- `character.memory.enabled` — 开启 / 关闭长期记忆
- `server.ws_port` — WebSocket 端口

## 主要依赖

- PyTorch 2.11 + CUDA 12.8
- funasr（Paraformer-zh ASR）
- websockets（WebSocket 服务端）
- Qdrant（向量库，长期记忆）
- DeepSeek / MiniMax / DashScope API
- Electron + Vue3 + PIXI.js 6 + pixi-live2d-display（前端）
