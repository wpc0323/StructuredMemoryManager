# 典型场景使用案例

> 本文档展示 StructuredMemoryManager 在实际使用中的典型操作流程。所有操作通过 `cli.py` 执行。

---

## 场景一：记录用户偏好

用户在对话中明确表示不喜欢某种交互方式。

```bash
python cli.py add -c habit \
  --content "用户偏好简洁的代码注释风格，不需要过多解释性文字。函数文档只写参数和返回值。" \
  -p high -t "代码风格,注释偏好" --emphasis --json
```

执行结果：
1. `habits/` 目录下创建新的 `.md` 文件
2. YAML front matter 中 priority=high, emphasis=true
3. `memory_index.md` 同步新增条目记录

---

## 场景二：记录学到的技能方法

Agent 在完成某任务后总结出可复用的模式。

```bash
python cli.py add -c skill \
  --content "React Hooks性能优化：1) useMemo缓存计算结果 2) useCallback稳定回调引用 3) 拆分组件粒度" \
  -p medium -t "React,性能优化,Hooks" \
  --mention-count 2 --json
```

执行结果：
1. `skills/` 目录下创建新的 `.md` 文件
2. mention_count=2，再次提及（>=3）时检索权重将显著提升

---

## 场景三：记录项目决策

项目开发过程中做出重要技术决策。

```bash
python cli.py add -c project \
  --content "选择PostgreSQL替代MySQL，原因：需要JSONB字段、团队有运维经验、需要全文搜索功能" \
  -p high -t "技术选型,数据库,PostgreSQL" \
  --project-name "data_platform" --emphasis --json
```

执行结果：
1. 创建或更新 `projects/data_platform.md`
2. 若文件已存在，在正文顶部追加新条目块，更新 decision_log
3. 标记为 emphasis=true（用户强调）

---

## 场景四：检索记忆

新对话开始时需要回忆用户之前的偏好。

```bash
# 模糊查询
python cli.py search "代码风格" --json

# 类别过滤
python cli.py search "代码风格" --category habit --json

# 高优过滤（启动时推荐）
python cli.py search "偏好 习惯 规范" --high-priority --json

# 标签精确过滤
python cli.py search "代码" -t "代码风格" --high-priority --json
```

返回值示例：

```json
[
  {
    "file_path": "habits/用户偏好简洁的代码注释风格_012.md",
    "entry_id": "2026-07-19-15-30-012",
    "category": "habit",
    "summary": "用户偏好简洁的代码注释风格",
    "content_snippet": "用户偏好简洁的代码注释风格，不需要过多解释性文字...",
    "score": 5,
    "weight": 65,
    "priority": "high",
    "tags": ["代码风格", "注释偏好"],
    "emphasis": true,
    "mention_count": 0
  }
]
```

---

## 场景五：读取单条记忆完整内容

search 返回的 content_snippet 被截断时，用 read 获取完整正文。

```bash
python cli.py read "habits/用户偏好简洁的代码注释风格_012.md" --json
```

返回值包含完整的 front matter 字段和未截断的正文内容。

---

## 场景六：确认与维护记忆

### 确认记忆仍有效

```bash
python cli.py confirm "habits/xxx.md" "2026-07-19-12-00-001" confirm --json
# 结果: expires 设为 null（永不过期）
```

### 延长有效期

```bash
python cli.py confirm "skills/xxx.md" "2026-07-19-12-00-005" extend -e "2028-03-15" --json
```

### 提升优先级

```bash
python cli.py confirm "skills/xxx.md" "2026-07-19-12-00-012" upgrade -p high --json
# 结果: priority 变为 high，检索权重 +20
```

### 标记强调

```bash
python cli.py confirm "habits/xxx.md" "2026-07-19-12-00-002" emphasize --json
# 结果: emphasis 变为 true，检索权重 +25(habit)
```

### 增加提及次数

```bash
python cli.py confirm "skills/xxx.md" "2026-07-19-12-00-003" bump_mention --json
# 结果: mention_count +1，>=3 时检索权重显著提升
```

---

## 场景七：索引修复

意外编辑导致索引与文件不同步时：

```bash
python cli.py rebuild --json
```

重建过程：
1. 遍历所有类别目录（含 archive/ 子目录）
2. 读取每个 `.md` 文件的 front matter
3. 重建 `memory_index.md` 的 entries 列表
4. 按 last_modified 倒序排列

---

## 场景八：归档触发

当某类别目录下 `.md` 文件数超过50时自动触发：

1. 第51条记忆写入后，`_check_archiving()` 自动执行
2. 筛选 priority=low 且超过90天的文件 → 移入 `archive/` 子目录
3. `memory_index.md` 中对应条目的 path 更新为 archive 路径
4. 返回通知："已归档 N 条旧记忆"
5. 归档文件仍可被检索到
