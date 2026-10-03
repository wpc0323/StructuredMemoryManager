#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
StructuredMemoryManager - 共享基础模块
========================================
提供 YAML 解析、文件管理、时间工具、配置常量等所有方法文件共用的基础设施。
所有工具文件都从此模块导入，避免代码重复。
"""

import os
import re
import time
import random
import contextlib
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path

# 尝试导入PyYAML，失败时使用简单解析器
try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

# 尝试检测 chromadb（不在此导入，仅检测可用性，避免强依赖）
# 注意: find_spec 对未安装的顶层模块返回 None 而不是抛出 ImportError，
# 必须显式判断 None，否则未安装 chromadb 时也会被误判为可用，
# 导致 search 走向量模式且永不降级、结果恒为空。
import importlib.util
HAS_CHROMADB = importlib.util.find_spec("chromadb") is not None

# 环境变量 SMM_NO_VECTOR=1 可全局禁用向量检索（强制关键字模式），
# 优先级高于 chromadb 是否可用；也用于测试与离线环境。
if os.environ.get("SMM_NO_VECTOR", "").strip().lower() in ("1", "true", "yes"):
    HAS_CHROMADB = False


def is_vector_available() -> bool:
    """检查向量检索是否可用（chromadb 是否已安装）"""
    return HAS_CHROMADB


# ============================================================
# 配置常量
# ============================================================

SKILL_ROOT = Path(__file__).parent.parent  # StructuredMemoryManager/ 根目录
TEMPLATES_DIR = SKILL_ROOT / "templates"
ARCHIVE_THRESHOLD = 50       # 触发归档的条目数阈值
ARCHIVE_AGE_DAYS = 90        # 归档年龄阈值（天）
ARCHIVE_AGE_DAYS_FALLBACK = 60  # 第二轮归档年龄阈值
STALE_DAYS = 180             # medium 优先级条目超过该天数未更新时建议确认
DEDUP_SIMILARITY = 0.95      # 向量去重阈值：新记忆与已有记忆相似度达到该值时合并（1-余弦距离）
LOCK_TIMEOUT_SECONDS = 10.0  # 进程锁等待超时
LOCK_STALE_SECONDS = 30.0    # 锁文件超过该时长视为残留锁，自动清理

# 检索热度与时间衰减（v3.3）
RECENCY_HALF_LIFE_DAYS = 30  # recency 子权重指数衰减的半衰期（天）
ACCESS_BONUS_MAX = 10        # 检索热度加成上限
ACCESS_BONUS_STEP = 2        # 每被检索命中一次增加的热度分

# 自动互链（v3.3）
AUTO_LINK_MIN_SHARED_TAGS = 2  # 标签重叠达到该数量时自动建立 related_files 关联
AUTO_LINK_MAX_LINKS = 5        # 单条新记忆最多自动建立的关联数
RELATED_EXPANSION_LIMIT = 3    # 检索结果中每条最多展开的关联记忆数

# 类别对应的子目录名
CATEGORY_DIR_MAP = {
    "habit": "habits",
    "skill": "skills",
    "project": "projects",
}

TIMEZONE_CN = timezone(timedelta(hours=8))  # 中国标准时间


# ============================================================
# 记忆读取加权检索规范
# ============================================================
# 三类记忆分别分配差异化权重，检索排序、上下文引用均按优先级执行

# 分类间基础权重（越高分类整体越优先）
CATEGORY_WEIGHT = {
    "project": 30,   # 分类1：项目任务相关记忆
    "habit": 20,     # 分类2：用户个人偏好相关记忆
    "skill": 10,     # 分类3：已学习掌握的技能记忆
}

# 分类1（project）内部权重排序：
#   时间时效性（近期任务优先）> 用户主动强调/标记重点任务 > 其他常规任务记录
PROJECT_SUB_WEIGHTS = {
    "recency": 25,       # 时间时效性（近期优先）
    "emphasis": 15,      # 用户主动强调/标记重点
    "normal": 0,         # 其他常规任务记录
}

# 分类2（habit）内部权重排序：
#   用户主动强调/明确要求的偏好 > 时间时效性（最新偏好优先）> 其他次要偏好
HABIT_SUB_WEIGHTS = {
    "emphasis": 25,      # 用户主动强调/明确要求
    "recency": 15,       # 时间时效性（最新优先）
    "normal": 0,         # 其他次要偏好
}

# 分类3（skill）内部权重排序：
#   用户主动强调、反复提及的技能 > 其余全部技能信息
SKILL_SUB_WEIGHTS = {
    "emphasis": 30,      # 用户主动强调、反复提及
    "normal": 0,         # 其余全部技能信息
}

# 优先级映射权重
PRIORITY_WEIGHT_MAP = {
    "high": 20,
    "medium": 10,
    "low": 0,
}

# 强调标记（emphasis）在 front matter 中用字段 "emphasis" 标识
# emphasis=true 表示用户主动强调/标记重点
# 对于 skill，还通过 mention_count 字段记录提及次数，mention_count >= 3 视为"反复提及"

# 记忆冲突解决规则：高权重记忆覆盖低权重记忆
# 权重总分 = 分类基础权重 + 分类内子权重 + 优先级权重 + 关键词匹配分


def recency_factor(date_str: str = None) -> float:
    """
    时间衰减因子（0~1）：半衰期 30 天的指数衰减。
    当天 = 1.0，30 天前 = 0.5，90 天前 = 0.125，一年后趋近 0。
    替代旧版"30 天内视为近期"的二元判断，使新旧记忆平滑过渡。
    """
    if not date_str:
        return 0.0
    days = days_since(date_str)
    if days < 0:
        days = 0
    return 0.5 ** (days / float(RECENCY_HALF_LIFE_DAYS))


def compute_weight(
    category: str,
    priority: str,
    emphasis: bool = False,
    mention_count: int = 0,
    date_str: str = None,
    keyword_score: float = 0,
    expires_str: str = None,
    access_count: int = 0,
    superseded: bool = False,
) -> float:
    """
    计算单条记忆的综合权重分数。

    权重公式（v3.3）：
        总分 = 分类基础权重 + 分类内子权重 + 优先级权重
               + 关键词/语义匹配分 + 检索热度加成 - 过期惩罚

    相比旧版的变化：
      - recency 子权重由"30 天内全额、超期归零"改为按半衰期 30 天指数衰减连续计分
      - 新增检索热度加成：条目每次被 search 命中 access_count +1，
        加成 = min(ACCESS_BONUS_MAX, access_count * ACCESS_BONUS_STEP)
      - superseded=True（已被新记忆取代）直接返回极低分（检索层会先过滤，此处兜底）

    参数:
        category: 记忆分类 (habit/skill/project)
        priority: 优先级 (high/medium/low)
        emphasis: 是否被用户主动强调/标记重点
        mention_count: 被提及的次数（skill类别使用）
        date_str: 条目日期(ISO)，用于计算时效性
        keyword_score: 关键词匹配得分
        expires_str: 过期日期，用于过期惩罚
        access_count: 被检索命中的累计次数
        superseded: 是否已被更新的记忆取代
    """
    # 1. 分类基础权重
    base = CATEGORY_WEIGHT.get(category, 0)

    # 2. 分类内子权重
    sub = 0
    recency = recency_factor(date_str)

    if category == "project":
        sub += PROJECT_SUB_WEIGHTS["recency"] * recency
        if emphasis:
            sub += PROJECT_SUB_WEIGHTS["emphasis"]

    elif category == "habit":
        if emphasis:
            sub += HABIT_SUB_WEIGHTS["emphasis"]
        else:
            sub += HABIT_SUB_WEIGHTS["recency"] * recency

    elif category == "skill":
        # 反复提及：mention_count >= 3 视为 emphasis
        if emphasis or mention_count >= 3:
            sub += SKILL_SUB_WEIGHTS["emphasis"]

    # 3. 优先级权重
    prio = PRIORITY_WEIGHT_MAP.get(priority, 0)

    # 4. 检索热度加成
    access_bonus = min(ACCESS_BONUS_MAX, int(access_count or 0) * ACCESS_BONUS_STEP)

    # 5. 过期惩罚
    expire_penalty = 0
    if expires_str and is_expired(expires_str):
        expire_penalty = 5

    if superseded:
        return -100.0

    # 总分
    total = base + sub + prio + keyword_score + access_bonus - expire_penalty
    return total


def resolve_conflict(memories: list) -> list:
    """
    记忆冲突解决：当多条记忆内容矛盾时，直接采信权重更高的信息。

    参数:
        memories: 已按权重排序的记忆列表，每项为 dict 含 weight 字段

    返回:
        去冲突后的记忆列表（低权重冲突项被移除）
    """
    if len(memories) <= 1:
        return memories

    # 简单策略：同分类同主题的低权重记忆如果与高权重记忆矛盾，
    # 低权重记忆不可覆盖/抵消高权重记忆内容
    # 此处仅确保排序后高权重在前，冲突时由调用方按权重采纳
    return sorted(memories, key=lambda m: m.get("weight", 0), reverse=True)


# ============================================================
# Agent 环境检测与记忆目录定位
# ============================================================

def _detect_agent_memory_dir() -> Optional[Path]:
    """
    自动检测当前 agent 环境并返回对应的记忆目录。
    所有项目、所有对话共享同一个记忆目录，确保记忆跨项目、跨会话一致。

    优先级：
      1. Trae 环境: ~/.trae-cn/memory/StructuredMemoryManager/
      2. Cursor 环境: ~/.cursor/memory/StructuredMemoryManager/
      3. 默认: ~/.agent-memory/StructuredMemoryManager/
    """
    home = Path.home()

    # 检测 Trae 环境
    trae_root = home / ".trae-cn" / "memory"
    if trae_root.exists():
        return trae_root / "StructuredMemoryManager"

    # 检测 Cursor 环境
    cursor_root = home / ".cursor" / "memory"
    if cursor_root.exists():
        return cursor_root / "StructuredMemoryManager"

    # 未检测到已知 agent
    return None


def _get_default_memory_dir() -> Path:
    """获取默认记忆目录（跨项目共享）"""
    home = Path.home()
    return home / ".agent-memory" / "StructuredMemoryManager"


# 自动设置记忆目录（全局共享，不随项目路径变化）
# 可通过环境变量 SMM_MEMORY_DIR 显式指定记忆目录（便于测试和多套记忆隔离），
# 优先级高于自动检测。
_detected = _detect_agent_memory_dir()
MEMORY_DIR = _detected if _detected else _get_default_memory_dir()
_env_memory_dir = os.environ.get("SMM_MEMORY_DIR")
if _env_memory_dir:
    MEMORY_DIR = Path(_env_memory_dir).expanduser()


# ============================================================
# YAML 处理工具
# ============================================================

class YAMLParser:
    """YAML解析器，支持PyYAML和回退模式"""

    @staticmethod
    def load(text: str) -> Dict[str, Any]:
        """解析YAML文本为字典"""
        if HAS_YAML:
            try:
                return yaml.safe_load(text) or {}
            except yaml.YAMLError as e:
                raise ValueError(f"YAML解析错误: {e}")
        else:
            return YAMLParser._fallback_parse(text)

    @staticmethod
    def _parse_scalar(value: str) -> Any:
        """解析单个标量值或 flow 风格列表（回退模式）"""
        value = value.strip()
        if value.startswith('[') and value.endswith(']'):
            inner = value[1:-1].strip()
            if not inner:
                return []
            items = [v.strip() for v in inner.split(',')]
            return [YAMLParser._parse_scalar(v) for v in items if v]
        if value.lower() in ('true', 'false'):
            return value.lower() == 'true'
        if value in ('null', '~', ''):
            return None
        if re.match(r'^-?\d+$', value):
            return int(value)
        if re.match(r'^-?\d+\.\d+$', value):
            return float(value)
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            body = value[1:-1]
            if value[0] == '"':
                body = body.replace('\\"', '"').replace('\\\\', '\\')
            else:
                body = body.replace("''", "'")
            return body
        return value

    @staticmethod
    def _parse_block_list(lines: List[str], start: int) -> Tuple[List[Any], int]:
        """
        解析 "- ..." 形式的块风格列表，返回 (items, 停止行索引)。
        支持两种形态：
          1. 列表套扁平字典（如 memory_index.md 的 entries）
          2. 纯标量列表（如 PyYAML dump 出的 tags / related_files 块列表）
        """
        n = len(lines)
        first_body = lines[start].strip()[2:].strip()

        # 纯标量列表：首个条目不含 "key:" 结构
        if ':' not in first_body:
            items: List[Any] = []
            i = start
            while i < n:
                stripped = lines[i].strip()
                if not stripped:
                    i += 1
                    continue
                if not stripped.startswith('- '):
                    break
                items.append(YAMLParser._parse_scalar(stripped[2:]))
                i += 1
            return items, i

        items = []
        i = start
        while i < n:
            line = lines[i]
            stripped = line.strip()
            if not stripped:
                i += 1
                continue
            if not stripped.startswith('- '):
                break
            item_indent = len(line) - len(line.lstrip(' '))
            item: Dict[str, Any] = {}
            body = stripped[2:].strip()
            last_key = None
            if ':' in body:
                k, _, v = body.partition(':')
                last_key = k.strip()
                item[last_key] = YAMLParser._parse_scalar(v)
            i += 1
            # 同一条目的后续内容：缩进比 "- " 行更深的行
            while i < n:
                cont = lines[i]
                cont_stripped = cont.strip()
                cont_indent = len(cont) - len(cont.lstrip(' '))
                if not cont_stripped:
                    i += 1
                    continue
                if cont_indent <= item_indent:
                    break
                if cont_stripped.startswith('- '):
                    # 嵌套的块风格标量列表（PyYAML dump 的 tags 等字段）
                    if last_key is not None:
                        if not isinstance(item.get(last_key), list):
                            item[last_key] = []
                        item[last_key].append(YAMLParser._parse_scalar(cont_stripped[2:]))
                    i += 1
                    continue
                if ':' in cont_stripped:
                    k, _, v = cont_stripped.partition(':')
                    last_key = k.strip()
                    item[last_key] = YAMLParser._parse_scalar(v)
                i += 1
            items.append(item)
        return items, i

    @staticmethod
    def _fallback_parse(text: str) -> Dict[str, Any]:
        """
        无PyYAML时的简易解析器。
        支持本 Skill 实际使用的全部结构：顶层键值对、flow 风格列表 [a, b]、
        以及 memory_index.md 中 entries 这类「列表套扁平字典」的块结构。
        """
        result: Dict[str, Any] = {}
        cleaned = []
        for raw in text.split('\n'):
            stripped = raw.strip()
            if not stripped or stripped == '---':
                continue
            cleaned.append(raw.rstrip())

        i = 0
        n = len(cleaned)
        while i < n:
            line = cleaned[i]
            stripped = line.strip()
            if stripped.startswith('- ') or ':' not in stripped:
                i += 1
                continue
            key, _, value = stripped.partition(':')
            key = key.strip()
            value = value.strip()
            if value == '':
                # 空值：向后看，若下一行以 "- " 开头则按字典列表解析
                j = i + 1
                while j < n and cleaned[j].strip() == '':
                    j += 1
                if j < n and cleaned[j].strip().startswith('- '):
                    items, i = YAMLParser._parse_block_list(cleaned, j)
                    result[key] = items
                    continue
                result[key] = None
                i += 1
            else:
                result[key] = YAMLParser._parse_scalar(value)
                i += 1
        return result

    @staticmethod
    def dump(data: Dict[str, Any]) -> str:
        """将字典序列化为YAML文本"""
        if HAS_YAML:
            return yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False)
        else:
            return YAMLParser._fallback_dump(data)

    @staticmethod
    def _format_scalar(value: Any) -> str:
        """将标量或 flow 列表格式化为 YAML 值文本（回退模式，与 _parse_scalar 配套）"""
        if isinstance(value, bool):
            return 'true' if value else 'false'
        if value is None:
            return 'null'
        if isinstance(value, (int, float)):
            return str(value)
        if isinstance(value, list):
            return '[' + ', '.join(YAMLParser._format_scalar(v) for v in value) + ']'
        text = str(value)
        needs_quote = (
            text == ''
            or text.lower() in ('true', 'false', 'null', '~')
            or bool(re.match(r'^-?[\d.]+$', text))
            or any(c in text for c in [':', '[', ']', '{', '}', '#', ',', '\n', '"', "'"])
        )
        if needs_quote:
            return '"' + text.replace('\\', '\\\\').replace('"', '\\"') + '"'
        return text

    @staticmethod
    def _fallback_dump(data: Dict[str, Any], indent: int = 0) -> str:
        """简易YAML生成（块风格，与 _fallback_parse 保持双向兼容）"""
        lines = []
        prefix = "  " * indent
        for key, value in data.items():
            if isinstance(value, dict):
                lines.append(f"{prefix}{key}:")
                lines.append(YAMLParser._fallback_dump(value, indent + 1))
            elif isinstance(value, list) and value and all(isinstance(v, dict) for v in value):
                # 字典列表输出为块风格（entries 结构），保证可被 _fallback_parse 读回
                lines.append(f"{prefix}{key}:")
                for item in value:
                    item_lines = []
                    for j, (k, v) in enumerate(item.items()):
                        item_prefix = f"{prefix}  - " if j == 0 else f"{prefix}    "
                        item_lines.append(f"{item_prefix}{k}: {YAMLParser._format_scalar(v)}")
                    if item_lines:
                        lines.extend(item_lines)
                    else:
                        lines.append(f"{prefix}  - {{}}")
            else:
                lines.append(f"{prefix}{key}: {YAMLParser._format_scalar(value)}")
        return '\n'.join(lines)


def extract_front_matter(file_content: str) -> Tuple[Dict[str, Any], str]:
    """
    从文件内容中提取YAML front matter和正文
    返回: (front_matter_dict, body_text)
    """
    if not file_content:
        return {}, ""
    # 统一换行符，避免 Windows CRLF 影响解析
    content = file_content.replace('\r\n', '\n').replace('\r', '\n')
    pattern = r'^---\s*\n(.*?)\n---\s*\n(.*)$'
    match = re.match(pattern, content, re.DOTALL)
    if not match:
        # 兼容历史遗留格式：闭合 --- 与末行内容粘连（如 "emphasis: true---"）
        match = re.match(r'^---\s*\n(.*?)---\s*\n(.*)$', content, re.DOTALL)
    if match:
        fm_text = match.group(1)
        body = match.group(2)
        return YAMLParser.load(fm_text), body
    return {}, file_content


def build_front_matter(fm_dict: Dict[str, Any]) -> str:
    """构建完整的front matter字符串"""
    yaml_text = YAMLParser.dump(fm_dict)
    # 内置简易 dump 不带末尾换行，必须补上，否则闭合 --- 会与内容粘连，
    # 导致 extract_front_matter 无法识别边界（索引读写整体失效）
    if yaml_text and not yaml_text.endswith('\n'):
        yaml_text += '\n'
    return f"---\n{yaml_text}---\n\n"


# ============================================================
# 时间工具
# ============================================================

def now_iso() -> str:
    """返回当前时间的ISO 8601格式字符串"""
    return datetime.now(TIMEZONE_CN).strftime("%Y-%m-%dT%H:%M:%S%z")


def now_date_str() -> str:
    """返回当前日期时间字符串，用于标题"""
    return datetime.now(TIMEZONE_CN).strftime("%Y-%m-%d %H:%M")


def generate_entry_id(existing_ids: List[str] = None) -> str:
    """
    生成唯一的条目ID
    格式: YYYY-MM-DD-HH-MM-NNN
    在序号部分加入随机微调，降低并发冲突概率
    """
    base = datetime.now(TIMEZONE_CN).strftime("%Y-%m-%d-%H-%M-")
    seq = random.randint(1, 50)  # 随机起始序号，降低并发冲突
    if existing_ids:
        matching = [id_ for id_ in existing_ids if id_.startswith(base)]
        if matching:
            try:
                max_seq = max(int(id_.rsplit('-', 1)[-1]) for id_ in matching)
                seq = max_seq + 1
            except (ValueError, IndexError):
                seq = 1
    # 确保不与已有ID冲突
    while existing_ids and f"{base}{seq:03d}" in existing_ids:
        seq += 1
    return f"{base}{seq:03d}"


def days_since(date_str: str) -> int:
    """计算距离今天的天数"""
    try:
        dt = datetime.fromisoformat(date_str)
        delta = datetime.now(TIMEZONE_CN) - dt
        return delta.days
    except (ValueError, TypeError):
        return 999


def is_expired(expires_str: Optional[str]) -> bool:
    """检查是否已过保鲜期"""
    if not expires_str:
        return False
    return days_since(expires_str) > 0


# ============================================================
# 原子写入与并发保护
# ============================================================

def atomic_write_text(path: Path, text: str):
    """
    原子写入：先写同目录临时文件，再 os.replace 替换目标文件。
    避免写入中途崩溃留下半截文件损坏索引；临时文件统一 LF 换行，跨平台可同步。
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(path.name + ".tmp")
    with open(tmp_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    os.replace(tmp_path, path)


@contextlib.contextmanager
def memory_lock(mem_dir: Path = None, timeout: float = LOCK_TIMEOUT_SECONDS,
                stale_seconds: float = LOCK_STALE_SECONDS):
    """
    跨进程尽力而为的互斥锁（O_CREAT|O_EXCL 抢占锁文件）。
    用于保护「读索引 → 修改 → 写回」这类非原子操作，避免多会话并发写坏索引。
    超时未获取到锁时降级继续执行（yield False），不阻塞主流程；
    锁文件超过 stale_seconds 未更新视为残留锁，自动清理。
    """
    mem_dir = mem_dir or MEMORY_DIR
    mem_dir.mkdir(parents=True, exist_ok=True)
    lock_path = mem_dir / ".index.lock"
    acquired = False
    fd = None
    start = time.time()
    while True:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            acquired = True
            break
        except FileExistsError:
            try:
                if time.time() - lock_path.stat().st_mtime > stale_seconds:
                    lock_path.unlink()
                    continue
            except OSError:
                pass
            if time.time() - start > timeout:
                break
            time.sleep(0.05)
        except OSError:
            break
    try:
        if acquired and fd is not None:
            try:
                os.write(fd, str(os.getpid()).encode())
            except OSError:
                pass
        yield acquired
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        if acquired:
            try:
                lock_path.unlink()
            except OSError:
                pass


def relpath_posix(path: Path, base: Path = None) -> str:
    """返回 path 相对 base 的 POSIX 风格相对路径（统一正斜杠，跨平台索引可移植）"""
    base = Path(base) if base else MEMORY_DIR
    return str(Path(path).relative_to(Path(base))).replace("\\", "/")


def same_relpath(a: str, b: str) -> bool:
    """比较两个索引相对路径是否相同（忽略路径分隔符差异）"""
    return str(a).replace("\\", "/") == str(b).replace("\\", "/")


def normalize_text_key(text: str) -> str:
    """文本归一化（去空白、小写），用于重复记忆的精确匹配"""
    return re.sub(r"\s+", "", (text or "")).lower()


def days_since_or_none(date_str: Optional[str]) -> Optional[int]:
    """计算距今天数，日期无效时返回 None（区别于 days_since 的 999 兜底）"""
    if not date_str:
        return None
    try:
        dt = datetime.fromisoformat(date_str)
        return (datetime.now(TIMEZONE_CN) - dt).days
    except (ValueError, TypeError):
        return None


# ============================================================
# 文件管理工具
# ============================================================

def ensure_memory_dir(memory_dir: Path = None):
    """确保记忆目录和类别子目录存在"""
    mem_dir = memory_dir or MEMORY_DIR
    mem_dir.mkdir(parents=True, exist_ok=True)
    for dir_name in CATEGORY_DIR_MAP.values():
        (mem_dir / dir_name).mkdir(parents=True, exist_ok=True)


def _sanitize_filename(text: str, max_len: int = 40) -> str:
    """将摘要文本转换为安全的文件名"""
    # 移除不安全字符
    safe = re.sub(r'[\\/:*?"<>|\n\r\t]', '', text)
    # 将空格和连字符转为下划线
    safe = re.sub(r'[\s\-]+', '_', safe.strip())
    # 截断
    if len(safe) > max_len:
        safe = safe[:max_len]
    # 去掉首尾的下划线
    safe = safe.strip('_')
    return safe or "memory"


def get_entry_file_path(category: str, entry_id: str, summary: str, project_name: str = None, memory_dir: Path = None) -> Path:
    """
    根据类别、entry_id 和摘要生成独立文件路径
    文件名格式: {摘要简写}_{entry_id后6位}.md
    """
    mem_dir = memory_dir or MEMORY_DIR
    ensure_memory_dir(mem_dir)
    if category == "project":
        if not project_name:
            raise ValueError("category为project时必须提供project_name")
        proj_dir = mem_dir / "projects"
        proj_dir.mkdir(exist_ok=True)
        return proj_dir / f"{_sanitize_filename(project_name)}.md"
    elif category in CATEGORY_DIR_MAP:
        cat_dir = mem_dir / CATEGORY_DIR_MAP[category]
        cat_dir.mkdir(exist_ok=True)
        # 用摘要做文件名，加上 entry_id 后缀避免重名
        safe_name = _sanitize_filename(summary)
        id_suffix = entry_id.rsplit('-', 1)[-1]  # 取序号部分
        return cat_dir / f"{safe_name}_{id_suffix}.md"
    else:
        raise ValueError(f"未知分类: {category}，有效值为: habit, skill, project")


def read_memory_file(file_path: Path) -> Tuple[Dict[str, Any], str]:
    """读取记忆文件，返回(front_matter, body)"""
    if not file_path.exists():
        return {}, ""
    content = file_path.read_text(encoding='utf-8')
    return extract_front_matter(content)


def write_memory_file(file_path: Path, front_matter: Dict[str, Any], body: str):
    """写入记忆文件（front matter + body，原子写入）"""
    fm_text = build_front_matter(front_matter)
    full_content = fm_text + body
    atomic_write_text(file_path, full_content)


def read_memory_index(memory_dir: Path = None) -> Dict[str, Any]:
    """读取总目录文件"""
    mem_dir = memory_dir or MEMORY_DIR
    index_path = mem_dir / "memory_index.md"
    if not index_path.exists():
        return _init_memory_index()
    fm, _ = read_memory_file(index_path)
    return fm


def write_memory_index(fm: Dict[str, Any], memory_dir: Path = None):
    """写入总目录文件"""
    mem_dir = memory_dir or MEMORY_DIR
    index_path = mem_dir / "memory_index.md"
    if index_path.exists():
        _, old_body = read_memory_file(index_path)
    else:
        old_body = "# 记忆总目录\n\n本文件由 StructuredMemoryManager 自动维护。\n"
    write_memory_file(index_path, fm, old_body)


def _init_memory_index() -> Dict[str, Any]:
    """初始化空的总目录"""
    return {
        "last_modified": now_iso(),
        "entries": []
    }


# ============================================================
# 路径安全与状态统计
# ============================================================

def resolve_within_memory_dir(file_path: str, memory_dir: Path = None) -> Optional[Path]:
    """
    将相对路径解析到记忆目录内，防止路径越界（如 ../../ 等）。
    返回解析后的绝对路径；路径越界时返回 None。
    """
    mem_dir = (memory_dir or MEMORY_DIR).resolve()
    target = (mem_dir / file_path).resolve()
    try:
        target.relative_to(mem_dir)
    except ValueError:
        return None
    return target


def get_memory_stats(memory_dir: Path = None) -> dict:
    """收集记忆库统计信息（供 cli.py stats 使用）"""
    mem_dir = memory_dir or MEMORY_DIR
    ensure_memory_dir(mem_dir)
    stats = {
        "memory_dir": str(mem_dir),
        "categories": {},
        "index_entries": 0,
    }
    for category, dir_name in CATEGORY_DIR_MAP.items():
        cat_dir = mem_dir / dir_name
        archive_dir = cat_dir / "archive"
        deleted_dir = cat_dir / "deleted"
        stats["categories"][category] = {
            "active_files": len(list(cat_dir.glob("*.md"))) if cat_dir.exists() else 0,
            "archived_files": len(list(archive_dir.glob("*.md"))) if archive_dir.exists() else 0,
            "deleted_files": len(list(deleted_dir.glob("*.md"))) if deleted_dir.exists() else 0,
        }
    index_fm = read_memory_index(memory_dir=mem_dir)
    stats["index_entries"] = len(index_fm.get("entries", []))
    stats["pyyaml"] = HAS_YAML
    stats["chromadb"] = HAS_CHROMADB
    return stats
