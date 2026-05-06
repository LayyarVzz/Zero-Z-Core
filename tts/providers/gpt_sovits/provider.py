"""GPT-SoVITS HTTP API provider。

通过 HTTP API 调用本地 GPT-SoVITS 服务进行语音合成。
使用前需启动 GPT-SoVITS 的 api_v2.py 服务端。
"""

import io
from typing import Generator

import httpx
import numpy as np
import soundfile as sf

from tts.base import TTSProvider


class GPTSovitsProvider(TTSProvider):
    """TTS 提供商：通过本地 GPT-SoVITS 的 HTTP API 进行语音合成。

    合成流程：
    1. setup() → 加载模型权重 -> 预加载参考音频音色
    2. synthesize_stream() / synthesize() → 发送文本，接收音频
    """

    def __init__(
        self,
        api_url: str,
        ref_audio_path: str,
        prompt_text: str,
        prompt_lang: str,
        text_lang: str,
        timeout: float = 60.0,
        gpt_weights_path: str | None = None,
        sovits_weights_path: str | None = None,
    ) -> None:
        self.api_url = api_url.rstrip("/")
        self.ref_audio_path = ref_audio_path
        self.prompt_text = prompt_text
        self.prompt_lang = prompt_lang  # 参考音频语种
        self.text_lang = text_lang  # 合成文本语种
        self.timeout = timeout
        self.gpt_weights_path = gpt_weights_path
        self.sovits_weights_path = sovits_weights_path
        # 复用 httpx.Client，避免每次请求重新建立 TCP 连接
        self._client = httpx.Client(timeout=self.timeout)

    @property
    def sample_rate(self) -> int:
        """v2ProPlus 模型固定输出 32000 Hz。"""
        return 32000

    def setup(self) -> None:
        """加载模型权重并预加载参考音频音色。

        先切换模型再设参考音频——参考音频的音色提取依赖模型已就绪。
        """
        self._set_model_weights()
        # /set_refer_audio 预设接口实测不生效，服务端仍要求每次 /tts 带 ref_audio_path，
        # 因此不再调用 _set_refer_audio()，改为在 _build_payload 中直接传。
        # if self.ref_audio_path:
        #     self._set_refer_audio()

    def is_ready(self) -> bool:
        """检查 GPT-SoVITS 服务是否可达。"""
        try:
            r = self._client.get(f"{self.api_url}/", timeout=2.0)
            return r.status_code < 500
        except Exception:
            return False

    def synthesize_stream(self, text: str) -> Generator[np.ndarray, None, None]:
        """流式合成：使用 streaming_mode=1（片段模式）+ media_type=raw。

        服务端按文本标点切句，每合成完一段立即返回原始 PCM int16 数据，
        客户端收到多少就立即 yield 多少。

        使用独立 httpx.Client——cancel() 可跨线程关闭连接以立即中断 iter_bytes()。
        """
        self._cancel_flag = False
        payload = self._build_payload(text, streaming_mode=1)
        payload["media_type"] = "raw"  # 原始 PCM，无需解析 WAV 头

        leftover = b""  # 跨 chunk 对齐缓冲：chunk 边界可能切在采样中间
        with self._client.stream(
            "POST", f"{self.api_url}/tts", json=payload
        ) as response:
            self._handle_response_errors(response)
            for chunk in response.iter_bytes():
                if self._cancel_flag:
                    break
                if chunk:
                    data = leftover + chunk
                    aligned = len(data) // 2 * 2
                    leftover = data[aligned:]
                    if aligned > 0:
                        yield np.frombuffer(data[:aligned], dtype=np.int16).copy()

    def cancel(self) -> None:
        """取消当前合成：设标志位。实际的舍弃由 TTSEngine 的代际 ID 机制保证。"""
        self._cancel_flag = True

    def synthesize(self, text: str) -> np.ndarray:
        """非流式合成：发送整段文本 -> 接收完整 WAV -> 返回完整 PCM int16 数组。"""
        payload = self._build_payload(text, streaming_mode=0)

        response = self._client.post(f"{self.api_url}/tts", json=payload)
        self._handle_response_errors(response)
        return self._decode_wav(response.content)

    def _set_model_weights(self) -> None:
        """切换 GPT 和 SoVITS 模型权重到指定文件。"""
        if self.gpt_weights_path:
            print(f"[GPTSovitsProvider] Setting GPT weights: {self.gpt_weights_path}")
            self._call_set_endpoint(
                "set_gpt_weights",
                "GPT weights",
                {"weights_path": self.gpt_weights_path},
            )
        else:
            print("[GPTSovitsProvider] GPT weights path not set, using server default")
        if self.sovits_weights_path:
            print(
                f"[GPTSovitsProvider] Setting SoVITS weights: {self.sovits_weights_path}"
            )
            self._call_set_endpoint(
                "set_sovits_weights",
                "SoVITS weights",
                {"weights_path": self.sovits_weights_path},
            )
        else:
            print(
                "[GPTSovitsProvider] SoVITS weights path not set, using server default"
            )

    def _call_set_endpoint(self, endpoint: str, label: str, params: dict) -> None:
        """通用 GET 请求模板，处理 /set_gpt_weights、/set_sovits_weights、/set_refer_audio 等端点。"""
        url = f"{self.api_url}/{endpoint}"
        try:
            r = self._client.get(url, params=params, timeout=5.0)
            if r.status_code == 200:
                print(f"[GPTSovitsProvider] {label} set successfully")
            else:
                print(
                    f"[GPTSovitsProvider] [WARN] Set {label} failed (HTTP {r.status_code})"
                )
                print(f"  Request: GET {url}?{list(params.items())}")
                print(f"  Response: {r.text}")
        except Exception as e:
            print(f"[GPTSovitsProvider] [WARN] Set {label} error: {e}")
            print(f"  Request: GET {url}?{list(params.items())}")

    def _set_refer_audio(self) -> None:
        """调用 API 预加载参考音频，提取说话人音色 Embedding。

        预加载后后续合成不需要重复传参考音频，降低延迟。
        """
        self._call_set_endpoint(
            "set_refer_audio",
            "refer audio",
            {"refer_audio_path": self.ref_audio_path},
        )

    def _build_payload(self, text: str, streaming_mode: int) -> dict:
        """构造 /tts 请求体，合成参数在两个方法间共享。"""
        payload = {
            "text": text,
            "text_lang": self.text_lang,
            "ref_audio_path": self.ref_audio_path,
            "prompt_lang": self.prompt_lang,
            "streaming_mode": streaming_mode,
        }
        if self.prompt_text:
            payload["prompt_text"] = self.prompt_text
        return payload

    def _handle_response_errors(self, response: httpx.Response) -> None:
        """统一处理 /tts 的错误响应。400 打印日志后抛异常中断流式迭代。"""
        if response.status_code == 400:
            try:
                response.read()  # 流式响应需先 read 再解析 body
                err = response.json()
                print(f"[GPTSovitsProvider] API error: {err}")
            except Exception:
                print(f"[GPTSovitsProvider] API error: {response.text}")
            raise RuntimeError(f"TTS API error: {response.text}")
        response.raise_for_status()

    def _decode_wav(self, wav_bytes: bytes) -> np.ndarray:
        """将 WAV 字节解码为 PCM int16 数组。"""
        if not wav_bytes:
            return np.array([], dtype=np.int16)
        audio, _ = sf.read(io.BytesIO(wav_bytes), dtype="int16")
        return audio
