# 典型场景使用案例

> 本文档展示 StructuredMemoryManager 在实际使用中的典型操作流程。

---

## 场景一：记录用户偏好

**背景**: 用户在对话中明确表示不喜欢某种交互方式。

### 操作步骤

```python
# 调用 add_memory 工具
add_memory(
    category="habit",
    content="用户偏好简洁的代码注释风格，不需要过多解释性文字。函数文档只写参数和返回值。",
    priority="high",
    tags=["代码风格", "注释偏好"],
    expires=None  # 永不过期，这是硬性约束
)
```

### 执行结果

1. `habits_preferences.md` 的 YAML `internal_index` 顶部新增条目
2. 正文顶部新增 `### 2026-06-24 XX:XX` 内容块
3. `priority_tags` 自动合并 `["代码风格", "注释偏好"]`
4. `memory_index.md` 同步更新时间戳和标签

---

## 场景二：记录学到的技能方法

**背景**: Agent 在完成某任务后总结出可复用的模式。

### 操作步骤

```python
add_memory(
    category="skill",
    content="""## React Hooks 性能优化模式

当组件存在频繁重渲染问题时，采用以下策略：

1. **useMemo 缓存计算结果**
   ```js
   const filtered = useMemo(() => data.filter(fn), [data, fn]);
   ```

2. **useCallback 稳定回调引用**
   ```js
   const handleClick = useCallback(() => { ... }, [dep]);
   ```

3. **拆分组件粒度**：将不常变化的部分提取为独立组件
""",
    priority="medium",
    tags=["React", "性能优化", "Hooks"],
    expires="2027-06-24"  # 一年后确认是否仍有效
)
```

### 执行结果

1. `skills_methods.md` 新增条目
2. 设置了保鲜期，一年后 Agent 会主动确认此模式是否过时
3. 可通过标签 `React` 或 `性能优化` 快速检索

---

## 场景三：记录项目决策

**背景**: 项目开发过程中做出重要技术决策。

### 操作步骤

```python
add_memory(
    category="project",
    content="## 技术选型决策：数据库方案\n\n**决策**: 选择 PostgreSQL 替代 MySQL\n**原因**:\n- 需要JSONB字段支持灵活的数据结构\n- 团队有PostgreSQL运维经验\n- 需要使用其全文搜索功能\n**影响范围**: 数据访问层需要重构，预计3天工作量",
    priority="high",
    tags=["技术选型", "数据库", "PostgreSQL"],
    project_name="data_platform"
)
```

### 执行结果

1. 创建/更新 `projects/data_platform.md`
2. 条目被标记为 high 优先级（重要决策）
3. 若之前记录了相关技能（如SQL优化），自动建立关联

---

## 场景四：检索记忆

**背景**: 新对话开始时需要回忆用户之前的偏好。

### 操作步骤

```python
# 方式一：模糊查询
results = search_memory(
    query="用户喜欢什么代码风格",
    category_filter="habit"
)

# 方式二：标签精确过滤
results = search_memory(
    query="代码",
    tag_filter=["代码风格"],
    high_priority_only=True
)
```

### 返回值示例

```json
[
  {
    "file_path": "habits_preferences.md",
    "entry_id": "2026-06-24-15-30-001",
    "anchor": "#2026-06-24-15-30-001",
    "content_snippet": "用户偏好简洁的代码注释风格...",
    "score": 8,
    "priority": "high",
    "tags": ["代码风格", "注释偏好"],
    "date": "2026-06-24T15:30:00+08:00"
  }
]
```

### 三级检索过程说明

1. **第一级**: 读 `memory_index.md`，发现 `habits_preferences.md` 有高优标签包含"代码风格"相关 → 候选中
2. **第二级**: 打开该文件，仅解析 YAML `internal_index`，找到匹配摘要的条目 entry_id
3. **第三级**: 根据 entry_id 定位正文中的 `###` 标题块，精确返回内容片段

---

## 场景五：确认与维护记忆

**背景**: 定期检查或用户主动更新偏好。

### 确认记忆仍有效

```python
confirm_memory(
    file_path="habits_preferences.md",
    entry_id="2026-06-20-09-00-001",
    action="confirm"
)
# 结果: 该条目的 expires 被设为 null（永不过期）
```

### 延长有效期

```python
confirm_memory(
    file_path="skills_methods.md",
    entry_id="2026-03-15-10-00-005",
    action="extend",
    new_expires="2028-03-15"
)
```

### 提升优先级

```python
confirm_memory(
    file_path="skills_methods.md",
    entry_id="2026-05-01-14-00-012",
    action="upgrade"
)
# 结果: priority 变为 high，标签加入全局 priority_tags
```

---

## 场景六：索引修复

**背景**: 意外编辑导致 YAML 索引与正文不同步。

### 重建索引

```python
result = rebuild_index(file_path="habits_preferences.md")

# 返回:
# {
#   "success": true,
#   "message": "索引已重建，共 23 条条目",
#   "entries_count": 23
# }
```

重建过程：
1. 读取文件全部正文
2. 用正则解析所有 `### YYYY-MM-DD HH:MM` 标题块
3. 从每个块中提取 ID、优先级、标签、过期日期
4. 重新生成完整的 `internal_index` 数组
5. 重算 `priority_tags`
6. 写回文件并同步总目录

---

## 场景七：归档触发

**背景**: 文件条目数超过50条阈值。

### 自动归档过程

当第51条记忆写入后：

1. `_check_archiving()` 自动执行
2. 筛选条件：`priority == low` 且 `date` 距今超过90天
3. 匹配的条目移入 `habits_archive.md` 或 `skills_archive.md`
4. 原文件的 `archive` 字段指向归档文件
5. `memory_index.md` 中标记 `archived: true`
6. 返回通知："已归档 N 条旧记忆"

### 归档后的检索

检索时会检查 `archive` 字段，如果主文件未命中则自动查询归档文件。
