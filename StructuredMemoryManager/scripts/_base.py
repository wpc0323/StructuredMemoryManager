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
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path

# 尝试导入PyYAML，失败时使用简单解析器
try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


# ============================================================
# 配置常量
# ============================================================

SKILL_ROOT = Path(__file__).parent.parent  # StructuredMemoryManager/ 根目录
MEMORY_DIR = SKILL_ROOT / "memory"
TEMPLATES_DIR = SKILL_ROOT / "templates"
ARCHIVE_THRESHOLD = 50       # 触发归档的条目数阈值
ARCHIVE_AGE_DAYS = 90        # 归档年龄阈值（天）
ARCHIVE_AGE_DAYS_FALLBACK = 60  # 第二轮归档年龄阈值

CATEGORY_FILE_MAP = {
    "habit": "habits_preferences.md",
    "skill": "skills_methods.md",
}

TIMEZONE_CN = timezone(timedelta(hours=8))  # 中国标准时间


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
    def _fallback_parse(text: str) -> Dict[str, Any]:
        """无PyYAML时的简易解析器（支持基础结构）"""
        result = {}
        in_front_matter = False
        lines = text.split('\n')
        for line in lines:
            line = line.strip()
            if line == '---':
                in_front_matter = not in_front_matter
                continue
            if in_front_matter and ':' in line:
                key, _, value = line.partition(':')
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if value.startswith('['):
                    items = re.findall(r'[\w\u4e00-\u9fff\-/.#]+', value)
                    result[key] = items
                elif value.lower() in ('true', 'false'):
                    result[key] = value.lower() == 'true'
                elif value == 'null' or value == '':
                    result[key] = None
                else:
                    result[key] = value
        return result

    @staticmethod
    def dump(data: Dict[str, Any]) -> str:
        """将字典序列化为YAML文本"""
        if HAS_YAML:
            return yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False)
        else:
            return YAMLParser._fallback_dump(data)

    @staticmethod
    def _fallback_dump(data: Dict[str, Any], indent: int = 0) -> str:
        """简易YAML生成"""
        lines = []
        prefix = "  " * indent
        for key, value in data.items():
            if isinstance(value, dict):
                lines.append(f"{prefix}{key}:")
                lines.append(YAMLParser._fallback_dump(value, indent + 1))
            elif isinstance(value, list):
                formatted_items = []
                for item in value:
                    if isinstance(item, dict):
                        item_str = "{ " + ", ".join(f"{k}: {v}" for k, v in item.items()) + " }"
                        formatted_items.append(item_str)
                    else:
                        formatted_items.append(f'"{item}"')
                lines.append(f"{prefix}{key}: [{', '.join(formatted_items)}]")
            elif isinstance(value, bool):
                lines.append(f"{prefix}{key}: {'true' if value else 'false'}")
            elif value is None:
                lines.append(f"{prefix}{key}: null")
            elif isinstance(value, str) and any(c in value for c in [':', '[', '{', '#', '\n']):
                lines.append(f'{prefix}{key}: "{value}"')
            else:
                lines.append(f"{prefix}{key}: {value}")
        return '\n'.join(lines)


def extract_front_matter(file_content: str) -> Tuple[Dict[str, Any], str]:
    """
    从文件内容中提取YAML front matter和正文
    返回: (front_matter_dict, body_text)
    """
    pattern = r'^---\s*\n(.*?)\n---\s*\n(.*)$'
    match = re.match(pattern, file_content, re.DOTALL)
    if match:
        fm_text = match.group(1)
        body = match.group(2)
        return YAMLParser.load(fm_text), body
    return {}, file_content


def build_front_matter(fm_dict: Dict[str, Any]) -> str:
    """构建完整的front matter字符串"""
    yaml_text = YAMLParser.dump(fm_dict)
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
    """
    base = datetime.now(TIMEZONE_CN).strftime("%Y-%m-%d-%H-%M-")
    seq = 1
    if existing_ids:
        prefix = base.replace('-', '', 3)
        matching = [id_ for id_ in existing_ids if id_.startswith(base)]
        if matching:
            seq = max(int(id_.rsplit('-', 1)[-1]) for id_ in matching) + 1
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
# 文件管理工具
# ============================================================

def ensure_memory_dir():
    """确保记忆目录存在"""
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)


def get_file_path(category: str, project_name: str = None) -> Path:
    """根据类别获取目标文件路径"""
    ensure_memory_dir()
    if category == "project":
        if not project_name:
            raise ValueError("category为project时必须提供project_name")
        proj_dir = MEMORY_DIR / "projects"
        proj_dir.mkdir(exist_ok=True)
        return proj_dir / f"{project_name}.md"
    elif category in CATEGORY_FILE_MAP:
        return MEMORY_DIR / CATEGORY_FILE_MAP[category]
    else:
        raise ValueError(f"未知分类: {category}，有效值为: habit, skill, project")


def read_memory_file(file_path: Path) -> Tuple[Dict[str, Any], str]:
    """读取记忆文件，返回(front_matter, body)"""
    if not file_path.exists():
        return {}, ""
    content = file_path.read_text(encoding='utf-8')
    return extract_front_matter(content)


def write_memory_file(file_path: Path, front_matter: Dict[str, Any], body: str):
    """写入记忆文件（front matter + body）"""
    fm_text = build_front_matter(front_matter)
    full_content = fm_text + body
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(full_content, encoding='utf-8')


def init_from_template(category: str, project_name: str = None) -> Path:
    """从模板初始化新文件"""
    target = get_file_path(category, project_name)

    if category == "habit":
        template_name = "habits_template.md"
    elif category == "skill":
        template_name = "skills_template.md"
    elif category == "project":
        template_name = "project_template.md"
    else:
        raise ValueError(f"未知分类: {category}")

    template_path = TEMPLATES_DIR / template_name
    if template_path.exists():
        template_content = template_path.read_text(encoding='utf-8')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(template_content, encoding='utf-8')

    return target


def read_memory_index() -> Dict[str, Any]:
    """读取总目录文件"""
    index_path = MEMORY_DIR / "memory_index.md"
    if not index_path.exists():
        return _init_memory_index()
    fm, _ = read_memory_file(index_path)
    return fm


def write_memory_index(fm: Dict[str, Any]):
    """写入总目录文件"""
    index_path = MEMORY_DIR / "memory_index.md"
    if index_path.exists():
        _, old_body = read_memory_file(index_path)
    else:
        old_body = "# 记忆总目录\n\n本文件由 StructuredMemoryManager 自动维护。\n"
    write_memory_file(index_path, fm, old_body)


def _init_memory_index() -> Dict[str, Any]:
    """初始化空的总目录"""
    return {
        "last_modified": now_iso(),
        "files": []
    }
