"""maintenance 维护检查 + 原子写入/进程锁测试"""

import os
import time

import pytest

import _base
import add_memory as add_mod
from _base import write_memory_file, atomic_write_text, memory_lock


@pytest.fixture(autouse=True)
def force_keyword_mode(monkeypatch):
    monkeypatch.setattr(_base, "HAS_CHROMADB", False)


@pytest.fixture
def mem_dir(tmp_path):
    d = tmp_path / "memory"
    _base.ensure_memory_dir(d)
    return d


def _write_memory(mem_dir, cat_dir, name, entry_id, category, priority,
                   date, expires=None, last_modified=None):
    fm = {
        "entry_id": entry_id,
        "date": date,
        "category": category,
        "priority": priority,
        "tags": [],
        "summary": f"条目 {entry_id}",
        "expires": expires,
        "related_files": [],
        "last_modified": last_modified or date,
        "emphasis": False,
    }
    write_memory_file(mem_dir / cat_dir / name, fm, "正文")
    return fm


class TestMaintenance:
    def test_expired_listed(self, mem_dir):
        _write_memory(mem_dir, "habits", "a.md", "2020-01-01-00-00-001", "habit",
                      "medium", "2020-01-01T00:00:00+08:00", expires="2020-06-01")
        from rebuild_index import rebuild_index
        rebuild_index(memory_dir=mem_dir)
        from maintenance import maintenance
        result = maintenance(memory_dir=mem_dir)
        assert result["summary"]["expired"] == 1
        assert result["expired"][0]["entry_id"] == "2020-01-01-00-00-001"

    def test_archive_candidates_listed(self, mem_dir):
        _write_memory(mem_dir, "skills", "old_low.md", "2020-01-02-00-00-001", "skill",
                      "low", "2020-01-02T00:00:00+08:00")
        _write_memory(mem_dir, "skills", "new_low.md", "2026-10-01-00-00-002", "skill",
                      "low", "2026-10-01T00:00:00+08:00")
        from rebuild_index import rebuild_index
        rebuild_index(memory_dir=mem_dir)
        from maintenance import maintenance
        result = maintenance(memory_dir=mem_dir)
        ids = [c["entry_id"] for c in result["archive_candidates"]]
        assert "2020-01-02-00-00-001" in ids
        assert "2026-10-01-00-00-002" not in ids

    def test_stale_medium_listed(self, mem_dir):
        old = "2020-01-01T00:00:00+08:00"
        _write_memory(mem_dir, "habits", "stale.md", "2020-01-03-00-00-001", "habit",
                      "medium", old)
        from rebuild_index import rebuild_index
        rebuild_index(memory_dir=mem_dir)
        from maintenance import maintenance
        result = maintenance(memory_dir=mem_dir)
        assert result["summary"]["stale"] == 1

    def test_missing_files_detected_with_hint(self, mem_dir):
        _write_memory(mem_dir, "habits", "gone.md", "2026-01-01-00-00-001", "habit",
                      "high", "2026-01-01T00:00:00+08:00")
        from rebuild_index import rebuild_index
        rebuild_index(memory_dir=mem_dir)
        (mem_dir / "habits" / "gone.md").unlink()
        from maintenance import maintenance
        result = maintenance(memory_dir=mem_dir)
        assert result["summary"]["missing_files"] == 1
        assert result["hint"] and "rebuild" in result["hint"]

    def test_empty_library_no_hint(self, mem_dir):
        from maintenance import maintenance
        result = maintenance(memory_dir=mem_dir)
        assert result["success"] is True
        assert result["hint"] is None


class TestAtomicWrite:
    def test_no_tmp_file_left(self, tmp_path):
        target = tmp_path / "sub" / "file.md"
        atomic_write_text(target, "内容")
        assert target.read_text(encoding="utf-8") == "内容"
        assert list(tmp_path.rglob("*.tmp")) == []

    def test_lf_line_endings(self, tmp_path):
        target = tmp_path / "file.md"
        atomic_write_text(target, "line1\nline2\n")
        raw = target.read_bytes()
        assert b"\r" not in raw

    def test_globs_do_not_match_tmp_files(self, mem_dir):
        """写入中途的 .tmp 文件不会被 *.md 的 glob/rglob 命中"""
        atomic_write_text(mem_dir / "habits" / "x.md", "hi")
        # 模拟残留的 tmp 文件（正常情况下 os.replace 后即消失）
        (mem_dir / "habits" / "y.md.tmp").write_text("partial", encoding="utf-8")
        assert len(list((mem_dir / "habits").glob("*.md"))) == 1
        assert len(list((mem_dir / "habits").rglob("*.md"))) == 1


class TestMemoryLock:
    def test_lock_released_after_add(self, mem_dir):
        add_mod.add_memory(category="habit", content="锁测试", memory_dir=mem_dir)
        assert not (mem_dir / ".index.lock").exists()

    def test_lock_blocks_and_releases(self, mem_dir):
        with memory_lock(mem_dir) as acquired:
            assert acquired is True
            assert (mem_dir / ".index.lock").exists()
            # 第二次抢锁在超时后降级成功（不阻塞），返回 False
            t0 = time.time()
            with memory_lock(mem_dir, timeout=0.2) as acquired2:
                assert acquired2 is False
            assert time.time() - t0 < 2
        assert not (mem_dir / ".index.lock").exists()

    def test_stale_lock_is_broken(self, mem_dir):
        lock_path = mem_dir / ".index.lock"
        lock_path.write_text("dead-pid", encoding="utf-8")
        # 把锁文件的修改时间拨回 10 分钟前，模拟持有者崩溃后的残留锁
        old = time.time() - 600
        os.utime(lock_path, (old, old))
        with memory_lock(mem_dir, timeout=2) as acquired:
            assert acquired is True
        assert not lock_path.exists()

    def test_add_succeeds_with_stale_lock(self, mem_dir):
        lock_path = mem_dir / ".index.lock"
        lock_path.write_text("dead-pid", encoding="utf-8")
        old = time.time() - 600
        os.utime(lock_path, (old, old))
        r = add_mod.add_memory(category="habit", content="残留锁下写入", memory_dir=mem_dir)
        assert r["success"] is True
        assert not lock_path.exists()
