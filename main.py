"""Zero-Z Virtual Digital Human — Application Entry Point."""

import os
import signal

from core.orchestrator import Orchestrator
from gui.app import run_gui


def main():
    orchestrator = Orchestrator()
    orchestrator.start()

    # Ctrl+C 优雅关闭
    def shutdown(signum, frame):
        print("\nShutting down...")
        orchestrator.stop()
        os._exit(0)

    signal.signal(signal.SIGINT, shutdown)

    try:
        run_gui(
            display_queue=orchestrator.display_queue,
            state_queue=orchestrator.state_queue,
        )
    finally:
        orchestrator.stop()


if __name__ == "__main__":
    main()
