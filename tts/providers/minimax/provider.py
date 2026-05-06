"""MiniMax 云端 TTS Provider。

通过 MiniMax 同步 TTS HTTP API (t2a_v2) 进行语音合成。
支持流式（SSE）和非流式两种模式。
"""

import base64
import io
import json
from typing import Generator

import httpx
import numpy as np
import soundfile as sf

from tts.base import TTSProvider


class MinimaxProvider(TTSProvider):
    """TTS 提供商：MiniMax 云端同步 TTS API (t2a_v2)。

    合成流程：
    1. setup() → 验证 API key 有效性
    2. synthesize_stream() / synthesize() → 发送文本，接收音频
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str = "speech-2.8-hd",
        voice_id: str = "male-qn-qingse",
        speed: float = 1.0,
        vol: float = 1.0,
        pitch: int = 0,
        sample_rate: int = 32000,
        format: str = "pcm",
        timeout: float = 60.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._voice_id = voice_id
        self._speed = speed
        self._vol = vol
        self._pitch = pitch
        self._sample_rate = sample_rate
        self._format = format
        self._timeout = timeout
        self._cancel_flag = False
        self._client = httpx.Client(
            timeout=self._timeout,
            headers={"Authorization": f"Bearer {self._api_key}"},
        )

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    def setup(self) -> None:
        """验证 API key：发送一个简单请求确认可达。"""
        try:
            self._client.head(f"{self._base_url}/", timeout=5.0)
        except Exception as e:
            print(f"[MinimaxProvider] API connection check failed: {e}")

    def is_ready(self) -> bool:
        """检查 MiniMax API 是否可达。"""
        try:
            r = self._client.head(f"{self._base_url}/", timeout=2.0)
            return r.status_code < 500
        except Exception:
            return False

    def synthesize_stream(self, text: str) -> Generator[np.ndarray, None, None]:
        """流式合成：POST stream=True → 逐行解析 SSE → yield PCM int16。

        MiniMax SSE 返回累积音频（每次 data 事件含完整音频），需切出增量部分。
        """
        self._cancel_flag = False
        payload = self._build_payload(text, stream=True)
        yielded_samples = 0  # 已产出的采样点数，用于从累积音频中切增量

        with httpx.Client(
            timeout=self._timeout,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Accept": "text/event-stream",
            },
        ) as client:
            with client.stream(
                "POST", f"{self._base_url}/v1/t2a_v2", json=payload
            ) as response:
                if response.status_code != 200:
                    self._handle_error(response)
                for line in response.iter_lines():
                    if self._cancel_flag:
                        break
                    if not line or not line.startswith("data:"):
                        continue
                    json_str = line[5:].strip()
                    if not json_str:
                        continue
                    try:
                        data = json.loads(json_str)
                    except Exception:
                        continue
                    audio_b64 = data.get("data", {}).get("audio", "")
                    if audio_b64:
                        full_audio = self._decode_audio(audio_b64)
                        if len(full_audio) > yielded_samples:
                            chunk = full_audio[yielded_samples:]
                            yielded_samples = len(full_audio)
                            yield chunk

    def synthesize(self, text: str) -> np.ndarray:
        """非流式合成：POST stream=False → JSON 响应 → 返回完整 PCM int16。"""
        payload = self._build_payload(text, stream=False)

        response = self._client.post(
            f"{self._base_url}/v1/t2a_v2", json=payload
        )
        if response.status_code != 200:
            self._handle_error(response)

        data = response.json()
        audio_hex_or_b64 = data.get("data", {}).get("audio", "")
        if not audio_hex_or_b64:
            return np.array([], dtype=np.int16)
        return self._decode_audio(audio_hex_or_b64)

    def cancel(self) -> None:
        self._cancel_flag = True

    def _build_payload(self, text: str, *, stream: bool) -> dict:
        payload = {
            "model": self._model,
            "text": text,
            "stream": stream,
            "voice_setting": {
                "voice_id": self._voice_id,
                "speed": self._speed,
                "vol": self._vol,
                "pitch": self._pitch,
            },
            "audio_setting": {
                "sample_rate": self._sample_rate,
                "format": self._format,
                "channel": 1,
            },
        }
        if not stream:
            payload["output_format"] = "hex"
        return payload

    def _decode_audio(self, data: str) -> np.ndarray:
        """将 hex 或 base64 编码的音频数据解码为 PCM int16 数组。

        流式 SSE 返回 base64，非流式 output_format=hex 返回 hex。
        先尝试 hex 解码，失败则尝试 base64。
        """
        try:
            raw = bytes.fromhex(data)
        except ValueError:
            raw = base64.b64decode(data)

        if self._format == "pcm":
            return np.frombuffer(raw, dtype=np.int16).copy()
        else:
            # mp3 / wav / flac 格式 → soundfile 解码
            samples, _ = sf.read(io.BytesIO(raw), dtype="int16")
            return samples

    def _handle_error(self, response: httpx.Response) -> None:
        try:
            response.read()
            err = response.json()
            print(f"[MinimaxProvider] API error: {err}")
        except Exception:
            print(f"[MinimaxProvider] API error: {response.text}")
        raise RuntimeError(f"MiniMax TTS API error (HTTP {response.status_code})")
