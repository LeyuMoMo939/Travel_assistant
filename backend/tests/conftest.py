"""pytest 公共配置:让 tests 不依赖 langchain,也不依赖当前工作目录。"""
import sys
import types
from pathlib import Path

# 1) 让 `import app` 在任意工作目录下都能用(config.py 里的 .env 已经是绝对路径)
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# 2) nodes.py 顶部 import 了 langchain 的 get_llm,但下面的单测只跑纯逻辑节点
#    (校验/路由/预算)。没装 langchain 时打个桩,省掉一整条重依赖。
try:
    import langchain_openai  # noqa: F401
except ImportError:
    _fake = types.ModuleType("app.services.llm")
    _fake.get_llm = lambda *a, **k: None  # type: ignore[attr-defined]
    sys.modules["app.services.llm"] = _fake
