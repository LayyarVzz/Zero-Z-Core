"""Paraformer ASR Provider — funasr paraformer-zh + fsmn-vad + ct-punc。"""
import numpy as np
from funasr import AutoModel

from asr.base import ASRProvider


class ParaformerProvider(ASRProvider):
    """本地 Paraformer-zh 识别."""

    def __init__(
        self,
        model: str = "paraformer-zh",
        vad_model: str = "fsmn-vad",
        punc_model: str = "ct-punc",
    ) -> None:
        self._model_name = model
        self._vad_model = vad_model
        self._punc_model = punc_model
        self._model: AutoModel | None = None

    @property
    def sample_rate(self) -> int:
        return 16000

    def setup(self) -> None:
        self._model = AutoModel(
            model=self._model_name,
            vad_model=self._vad_model,
            punc_model=self._punc_model,
            disable_update=True,
        )

    def transcribe(self, audio: np.ndarray) -> str:
        if self._model is None:
            raise RuntimeError("ParaformerProvider not set up")
        result = self._model.generate(input=audio, batch_size_s=300)
        if result and result[0]["text"].strip():
            return result[0]["text"].strip()
        return ""
