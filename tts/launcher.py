"""GPT-SoVITS 服务端启动器 — 管理子进程生命周期。"""

import os
import subprocess
import time
import httpx


class TTSLauncher:
    """以子进程方式启动和停止 GPT-SoVITS API 服务端。"""

    def __init__(self, server_dir: str, server_cmd: str, api_url: str) -> None:
        self.server_dir = server_dir  # 服务端工作目录（包含 runtime/ 和模型文件）
        # 启动命令，如 "runtime/python.exe api_v2.py -a 127.0.0.1 -p 9880"
        args = server_cmd.split()
        # 如果命令中的可执行文件不是绝对路径，拼接 server_dir 补全
        if not os.path.isabs(args[0]):
            args[0] = os.path.join(server_dir, args[0])
        self.server_args = args  # 不直接修改 server_cmd 的解析结果
        self.api_url = api_url.rstrip("/")  # API 根地址，如 http://127.0.0.1:9880
        self._process: subprocess.Popen | None = None

    def start(self, wait_timeout: float = 120.0) -> None:
        """启动子进程并等待服务就绪。

        wait_timeout: 最长等待时间（秒），模型加载可能较慢，
        超时仍未就绪则抛 TimeoutError。
        """
        if self.is_ready():
            print("[TTSLauncher] Server already running")
            return
        print(f"[TTSLauncher] Starting GPT-SoVITS: {' '.join(self.server_args)}")
        print(f"[TTSLauncher] Working dir: {self.server_dir}")
        self._process = subprocess.Popen(
            self.server_args,
            cwd=self.server_dir,
            stdout=subprocess.DEVNULL,  # 不捕获输出，避免缓冲区满导致子进程卡死
            stderr=subprocess.DEVNULL,
        )

        # 轮询等待服务就绪
        deadline = time.time() + wait_timeout
        last_msg = 0
        while time.time() < deadline:
            if self.is_ready():
                print("[TTSLauncher] Server ready")
                return
            # 子进程提前退出了 -> 说明启动失败
            if self._process.poll() is not None:
                raise RuntimeError(
                    f"GPT-SoVITS exited with code {self._process.returncode}"
                )
            # 每 15 秒打印一次等待状态，避免日志沉默
            elapsed = int(time.time() - (deadline - wait_timeout))
            if elapsed > 0 and elapsed % 15 == 0 and elapsed != last_msg:
                print(f"[TTSLauncher] Still waiting... ({elapsed}s)")
                last_msg = elapsed
            time.sleep(0.5)

        raise TimeoutError("GPT-SoVITS server did not become ready in time")

    def is_ready(self) -> bool:
        """通过访问根路径判断服务是否就绪。"""
        try:
            r = httpx.get(f"{self.api_url}/", timeout=2.0)
            return r.status_code < 500
        except Exception:
            return False

    def stop(self) -> None:
        """优雅关闭服务端：发送 exit 命令 -> 等待进程退出 -> 超时则强杀。"""
        if self._process is None:
            return
        print("[TTSLauncher] Stopping GPT-SoVITS server...")
        # 发送 /control?command=exit，通知服务端正常退出
        try:
            httpx.get(
                f"{self.api_url}/control", params={"command": "exit"}, timeout=5.0
            )
        except httpx.RequestError:
            # 连接被拒绝或超时——服务端可能已经挂了，忽略，后面还有硬杀兜底
            pass
        # 等待子进程自行退出
        try:
            self._process.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            # 超时没退则强杀，避免僵尸进程
            self._process.kill()
            self._process.wait()
        self._process = None
        print("[TTSLauncher] Server stopped")
