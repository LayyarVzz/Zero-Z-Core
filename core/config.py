"""配置管理 加载环境变量"""

import os
from functools import lru_cache

import yaml
from dotenv import load_dotenv
from pathlib import Path
from string import Template

# 项目根目录
ROOT = Path(__file__).resolve().parent.parent


@lru_cache(maxsize=1)
def load_config(path: str = "data/config.yaml") -> dict:
    """加载 YAML 配置文件，处理环境变量替换（结果缓存，避免重复解析）。"""
    load_dotenv(ROOT / ".env")  # 加载 .env 中的环境变量（已存在的不会被覆盖）
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    with open(config_path, "r", encoding="utf-8") as f:
        text = f.read()
    config = _subst_env(text)
    return yaml.safe_load(config)


def _subst_env(text: str) -> str:
    return Template(text).safe_substitute(os.environ)
