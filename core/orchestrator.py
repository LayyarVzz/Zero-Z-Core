"""Pipeline 编排器 — 连接所有模块，管理启动/停止生命周期。"""

import queue
import threading
import time

import sounddevice as sd

from asr.audio_capture import AudioCapture
from asr.paraformer.recognizer import ASR
from core.config import load_config
from core.events import SENTINEL, PLAYBACK_DONE, State
from dialogue.manager import DialogueManager
from llm.client import LLMClient
from tts.engine import TTSEngine
from tts.launcher import TTSLauncher


class Orchestrator:
    """Pipeline 总控制器，负责：构建模块 -> 启动 -> 协调 -> 停止。"""

    def __init__(self) -> None:
        config = load_config()
        asr_cfg = config["asr"]

        self.audio_queue: queue.Queue = queue.Queue(maxsize=100)
        self.text_queue: queue.Queue = queue.Queue()
        self.llm_queue: queue.Queue = queue.Queue()
        self.response_queue: queue.Queue = queue.Queue()
        self.tts_queue: queue.Queue = queue.Queue(maxsize=10)
        self.audio_out_queue: queue.Queue = queue.Queue()
        self.state_queue: queue.Queue = queue.Queue()
        self.display_queue: queue.Queue = queue.Queue()

        self.audio_capture = AudioCapture(self.audio_queue, sample_rate=asr_cfg["sample_rate"])
        self.asr = ASR(
            self.audio_queue, self.text_queue,
            sample_rate=asr_cfg["sample_rate"],
            energy_threshold=asr_cfg["energy_threshold"],
            silence_duration=asr_cfg["silence_duration"],
            pre_speech_duration=asr_cfg["pre_speech_duration"],
            min_utterance_duration=asr_cfg["min_utterance_duration"],
        )
        self.llm = LLMClient.from_config(self.llm_queue, self.response_queue)
        self.tts = TTSEngine.from_config(self.tts_queue, self.audio_out_queue)

        self.tts_launcher: TTSLauncher | None = None
        tts_cfg = config.get("tts", {}).get("gpt_sovits", {})
        if tts_cfg.get("server_dir") and tts_cfg.get("server_cmd"):
            self.tts_launcher = TTSLauncher(
                server_dir=tts_cfg["server_dir"],
                server_cmd=tts_cfg["server_cmd"],
                api_url=tts_cfg.get("api_url", "http://localhost:9880"),
            )

        self.dialogue = DialogueManager(
            personality_path=config["character"].get("personality_file", "data/characters/default.yaml"),
            memory_path=config["character"].get("memory_file", "data/memory.json"),
            max_history=config["character"].get("max_history", 20),
        )

        self.asr.on_speech_start = lambda: self.state_queue.put(State.LISTENING)
        self.asr.on_speech_end = lambda: self.state_queue.put(State.THINKING)

        self._interrupt_mode = asr_cfg.get("interrupt_mode", True)
        self._sample_rate = self.tts.sample_rate

        self._playback_thread: threading.Thread | None = None
        self._dispatch_thread: threading.Thread | None = None
        self._running = False

        # 非打断模式：播放完毕信号 + 是否需恢复麦克风
        self._playback_done = threading.Event()
        self._greeting_done = threading.Event()  # 开场白专用，不与 dispatch 的 _playback_done 混淆
        self._mic_paused = False

    def start(self) -> None:
        self._running = True

        if self.tts_launcher is not None:
            try:
                self.tts_launcher.start()
            except (RuntimeError, TimeoutError) as e:
                print(f"[Orchestrator] TTS server failed to start: {e}")
        self.tts.setup()

        self.asr.start()
        self.audio_capture.start()
        self.llm.start()
        self.tts.start()

        self._playback_thread = threading.Thread(target=self._playback_loop, daemon=True)
        self._playback_thread.start()

        self._dispatch_thread = threading.Thread(target=self._dispatch_loop, daemon=True)
        self._dispatch_thread.start()

        greeting = self.dialogue.get_greeting()
        if greeting:
            self.dialogue.add_assistant(greeting)
            self.display_queue.put(("ai", greeting))
            self._put_tts(greeting)

        print("[Orchestrator] All modules started")

    def stop(self) -> None:
        if not self._running:
            return
        print("[Orchestrator] Stopping...")
        self._running = False
        self._playback_done.set()
        self._greeting_done.set()

        self.audio_capture.stop()
        self.asr.stop()
        self.llm.stop()
        self.tts.stop()

        if self.tts_launcher is not None:
            self.tts_launcher.stop()

        for q in [self.audio_queue, self.text_queue, self.llm_queue,
                   self.response_queue, self.tts_queue, self.audio_out_queue]:
            try:
                q.put_nowait(SENTINEL)
            except queue.Full:
                pass

        if self._playback_thread is not None:
            self._playback_thread.join(timeout=3.0)
        if self._dispatch_thread is not None:
            self._dispatch_thread.join(timeout=3.0)

        print("[Orchestrator] Stopped")

    def _playback_loop(self) -> None:
        stream = None
        try:
            stream = sd.OutputStream(samplerate=self._sample_rate, channels=1, dtype="int16")
            stream.start()
            speaking = False
            while self._running:
                try:
                    chunk = self.audio_out_queue.get(timeout=0.1)
                except queue.Empty:
                    continue
                if chunk is SENTINEL:
                    break
                if chunk is PLAYBACK_DONE:
                    speaking = False
                    self._on_playback_done()
                    continue
                if not speaking:
                    speaking = True
                    self.state_queue.put(State.SPEAKING)
                stream.write(chunk)
        except Exception as e:
            print(f"[Orchestrator] Playback error: {e}")
        finally:
            if stream is not None:
                try:
                    stream.stop()
                except Exception:
                    pass
                try:
                    stream.close()
                except Exception:
                    pass

    def _dispatch_loop(self) -> None:
        # 非打断模式：等开场白播完再处理用户语音，避免时序冲突
        if not self._interrupt_mode:
            self._greeting_done.wait(timeout=30.0)

        while self._running:
            try:
                text = self.text_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            if text is SENTINEL:
                break

            if self._interrupt_mode:
                self._interrupt_current_turn()
            else:
                self._pause_mic_for_turn()

            self.display_queue.put(("user", text))
            self.dialogue.add_user(text)
            prompt, system = self.dialogue.build_prompt(text)
            self.llm_queue.put((prompt, system))

            self._drain_response_queue()
            collected: list[str] = []
            received_sentinel = False
            deadline = time.time() + 30.0
            while time.time() < deadline and self._running:
                try:
                    response = self.response_queue.get(timeout=0.1)
                except queue.Empty:
                    continue
                if response is SENTINEL:
                    received_sentinel = True
                    break
                if not isinstance(response, str):
                    continue
                if response.startswith("[LLM_ERROR]"):
                    print(f"LLM error: {response}")
                    break
                collected.append(response)

            if collected:
                full_response = "".join(collected)
            elif self._running:
                full_response = "抱歉，我现在回答不了，请稍后再试。"
            else:
                continue

            self.dialogue.add_assistant(full_response)
            self.display_queue.put(("ai", full_response))
            print(f"[LLM] {full_response}")
            self._put_tts(full_response)

            if not received_sentinel:
                self.llm.cancel()
                self._drain_response_queue()

            self._wait_for_playback_if_needed()

    def _interrupt_current_turn(self) -> None:
        """打断模式：取消旧 TTS 和 LLM，排空残留数据。"""
        self.tts.cancel()
        self.llm.cancel()
        self._drain_audio_out_queue()
        self._drain_response_queue()

    def _pause_mic_for_turn(self) -> None:
        """非打断模式：停麦、排空队列、重置 VAD，防止新旧语音混合。"""
        self.audio_capture.stop()
        self._mic_paused = True
        self._drain_audio_queue()
        self.asr.reset_vad()
        self._drain_text_queue()

    def _wait_for_playback_if_needed(self) -> None:
        """非打断模式：等待本轮 TTS 播放完毕。"""
        if not self._interrupt_mode:
            self._playback_done.clear()
            self._playback_done.wait(timeout=60.0)

    def _on_playback_done(self) -> None:
        """播放完毕：切 IDLE，非打断模式下通知 dispatch 并恢复麦克风。"""
        self.state_queue.put(State.IDLE)
        if not self._interrupt_mode:
            time.sleep(0.5)
            self._playback_done.set()
            self._greeting_done.set()
            if self._mic_paused:
                try:
                    self.audio_capture.start()
                    self._mic_paused = False
                except Exception as e:
                    print(f"[Orchestrator] 麦克风重启失败: {e}")

    def _put_tts(self, text: str) -> None:
        try:
            self.tts_queue.put(text, timeout=5.0)
        except queue.Full:
            print("[Orchestrator] TTS queue full, dropping utterance")

    def _drain_audio_out_queue(self) -> None:
        while True:
            try:
                chunk = self.audio_out_queue.get_nowait()
                if chunk is SENTINEL:
                    break
            except queue.Empty:
                break

    def _drain_audio_queue(self) -> None:
        while True:
            try:
                item = self.audio_queue.get_nowait()
                if item is SENTINEL:
                    break
            except queue.Empty:
                break

    def _drain_text_queue(self) -> None:
        while True:
            try:
                item = self.text_queue.get_nowait()
                if item is SENTINEL:
                    break
            except queue.Empty:
                break

    def _drain_response_queue(self) -> None:
        deadline = time.time() + 2.0
        while time.time() < deadline:
            try:
                item = self.response_queue.get(timeout=0.1)
                if item is SENTINEL:
                    return
            except queue.Empty:
                return
