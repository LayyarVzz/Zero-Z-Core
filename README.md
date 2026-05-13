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

Live2D 模型放入 `data/models/` 目录，切换角色修改 `config.yaml` 中 `character.name` 和 `gui.model_name`。

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

所有运行配置在 `data/config.yaml`，密钥在 `.env`。

### .env — API 密钥

```bash
cp .env.example .env
```

| 变量 | 用途 | 必需 |
|------|------|------|
| `DEEPSEEK_API_KEY` | LLM（DeepSeek） | 是 |
| `MINIMAX_API_KEY` | TTS（MiniMax 云端，仅 provider=minimax 时） | 按需 |
| `DASHSCOPE_API_KEY` | 长期记忆向量嵌入（仅 memory.enabled=true 时） | 按需 |

### LLM

```yaml
llm:
  provider: "openai_compatible"
  api_key: "${DEEPSEEK_API_KEY}"    # 从 .env 读取
  model: "deepseek-v4-flash"
  base_url: "https://api.deepseek.com"
  stream_mode: True                  # 流式输出
```

兼容 OpenAI 接口，可换成任何兼容 API（如 DashScope、vLLM 等），修改 `base_url` 和 `model` 即可。

### ASR

```yaml
asr:
  provider: "paraformer"             # FunASR Paraformer-zh 本地模型
  sample_rate: 16000
  interrupt_mode: True               # True=可打断 False=等播放完才能说话
  energy_threshold: 0.006            # RMS 能量阈值（触发语音检测）
  silence_duration: 0.8              # 静音 N 秒视为一句话结束
  pre_speech_duration: 0.3           # 保留语音开始前 N 秒音频
  min_utterance_duration: 0.5        # 短于 N 秒的语音视为无效
  paraformer:
    model: "paraformer-zh"
    vad_model: "fsmn-vad"
    punc_model: "ct-punc"
```

本地模型，首次运行自动从 ModelScope 下载，不需要 API Key。

### TTS

支持两种 Provider，用 `tts.provider` 切换：

**MiniMax（云端）**：

```yaml
tts:
  provider: "minimax"
  stream_mode: True
  minimax:
    api_key: "${MINIMAX_API_KEY}"
    model: "speech-2.8-hd"
    voice_id: "female-shaonv"        # 音色ID
    speed: 1.1
    vol: 1.0
    sample_rate: 32000
```

**GPT-SoVITS（本地）**：

```yaml
tts:
  provider: "gpt_sovits"
  stream_mode: True
  gpt_sovits:
    api_url: "http://localhost:9880"
    text_lang: "zh"
    ref_audio_path: "voice/gpt_sovits/ref.wav"  # 参考音频路径
    prompt_text: "参考音频对应的文本"
    prompt_lang: "zh"
```

需本地启动 GPT-SoVITS 推理服务（`GPT-SoVITS-v2`），默认端口 9880。

### Live2D 角色与模型

```yaml
gui:
  model_name: "hiyori"                # Live2D 模型名，对应 data/models/{model_name}/ 目录
  width: 400
  height: 600
  always_on_top: true
  mouse_penetration: false           # 全局鼠标穿透（托盘菜单可切换）

character:
  name: "zero"                       # 对应 data/characters/{name}/card.json
  max_history: 20
  memory:
    enabled: false                   # 长期记忆（需 docker compose up -d）
    embedding_model: "text-embedding-v3"
    embedding_api_key: "${DASHSCOPE_API_KEY}"
    qdrant_url: "http://localhost:6333"
    max_entries: 100
```

模型放在 `data/models/{角色名}/` 下，需包含 `.model3.json`、`.moc3`、`.motion3.json` 等文件。切换角色改 `character.name` 和 `gui.model_name` 两项。

角色卡使用 SillyTavern V3 格式，放在 `data/characters/{角色名}/card.json`。

## 主要依赖

- PySide6 + live2d-py + PyOpenGL（GUI + Live2D 渲染）
- funasr（Paraformer-zh ASR）
- Qdrant（向量库，长期记忆）
- DeepSeek / MiniMax / DashScope API
