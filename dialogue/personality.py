"""加载人物性格"""

from pathlib import Path
from typing import Any
from core.config import ROOT

import yaml


def load_personality(path: str) -> dict[str, Any]:
    """从 YAML 文件加载角色性格设定。"""
    filepath = Path(path)
    # 相对路径基于项目根目录 ROOT 补全
    if not filepath.is_absolute():
        filepath = ROOT / filepath
    if not filepath.exists():
        raise FileNotFoundError(f"Personality file not found: {filepath}")
    with open(filepath, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)
