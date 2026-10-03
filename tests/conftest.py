import sys
from pathlib import Path

# 将 scripts 目录加入 sys.path，使测试可以按顶层模块导入各工具脚本
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "StructuredMemoryManager" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
