from pathlib import Path

from atforge.config import Settings


def test_settings_defaults(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ATFORGE_DB_PATH", str(tmp_path / "x.db"))
    monkeypatch.setenv("ATFORGE_CACHE_DIR", str(tmp_path / "cache"))
    s = Settings()
    assert s.db_path == tmp_path / "x.db"
    assert s.cache_dir == tmp_path / "cache"


def test_ensure_dirs_creates_paths(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ATFORGE_DB_PATH", str(tmp_path / "nested" / "atforge.db"))
    monkeypatch.setenv("ATFORGE_CACHE_DIR", str(tmp_path / "cache"))
    s = Settings()
    s.ensure_dirs()
    assert (tmp_path / "nested").exists()
    assert (tmp_path / "cache").exists()
