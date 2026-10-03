#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
StructuredMemoryManager - SessionStart hook 脚本
================================================
供 ZCode / Claude Code 等 agent 的 SessionStart hook 调用：
会话启动时自动预加载全部高优先级记忆，并以 hook 兼容的 JSON
（additionalContext 字段）输出，由客户端注入会话上下文。

设计约束：
  - 强制关键字模式检索（不触碰 chromadb / 嵌入模型），启动零网络、零下载
  - 任何异常都吞掉并 exit 0：hook 失败绝不能阻塞会话
  - 无记忆时输出为空，注入空内容

配置方法见 integrations/README.md。
"""

import sys
import json
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


def _format_context(results) -> str:
    lines = ["[StructuredMemoryManager] 高优先级记忆预加载："]
    for i, r in enumerate(results, 1):
        emp = " [用户强调]" if r.get("emphasis") else ""
        mc = f" [提及{r.get('mention_count', 0)}次]" if r.get("mention_count", 0) > 0 else ""
        lines.append(f"{i}. ({r.get('priority')}) {r.get('summary')}{emp}{mc}"
                     f" — 文件: {r.get('file_path')}")
    lines.append("以上为用户历史偏好与硬性约束，回复时必须遵守；"
                 "需要详情可执行 cli.py read 查看对应文件。")
    return "\n".join(lines)


def main() -> int:
    try:
        for stream in (sys.stdout, sys.stderr):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (AttributeError, ValueError, OSError):
                pass

        try:
            from search_memory import search_memory
        except Exception:
            return 0

        results = search_memory("", high_priority_only=True, use_vector=False)
        if results:
            print(json.dumps({"additionalContext": _format_context(results)},
                             ensure_ascii=False))
    except Exception:
        # 吞掉一切异常：记忆加载失败不应影响会话正常启动
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
