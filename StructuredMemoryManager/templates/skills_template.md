---
last_modified: "2026-01-01T00:00:00+08:00"
category: skill
priority_tags: []
internal_index: []
related_files: []
archive: null
---

# 技能与方法记录 (skills_methods.md)

> 本文件存储 Agent 学习到的技能用法、工具工作流、代码模式、最佳实践等。
> 所有条目按时间倒序排列，最新的在顶部。

## 记忆条目区域

*(通过 add_memory 工具添加的条目将出现在此处)*

<!-- 条目格式示例：
### 2026-06-23 14:00

**ID**: `2026-06-23-14-00-001`
**优先级**: medium
**标签**: [自动化, 脚本, Python]
**过期**: 2027-06-23

## 批量重命名文件的Python脚本模式

```python
import os
from pathlib import Path

def batch_rename(directory, pattern, replacement):
    for f in Path(directory).glob(pattern):
        new_name = f.name.replace(old_str, new_str)
        f.rename(f.parent / new_name)
```

关键点：
1. 始终使用 pathlib 而非 os.path
2. 先打印预览再执行实际操作
3. 支持 dry_run 模式

---
-->
