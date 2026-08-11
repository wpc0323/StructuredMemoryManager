---
entry_id: "2026-01-01-00-00-001"
date: "2026-01-01T00:00:00+08:00"
category: skill
priority: medium
tags: [自动化, 脚本, Python]
summary: "批量重命名文件的Python脚本模式"
expires: "2027-01-01"
related_files: []
last_modified: "2026-01-01T00:00:00+08:00"
---

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
