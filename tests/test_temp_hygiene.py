import os
import time

from app.pipeline.temp_hygiene import STAGING_DIR_PREFIX, cleanup_stale_staging_dirs


def _make_staging_dir(base, name, age_hours):
    d = base / name
    d.mkdir()
    (d / "wynik.docx").write_text("dummy")
    old_time = time.time() - age_hours * 3600
    os.utime(d, (old_time, old_time))
    return d


def test_removes_only_stale_staging_dirs(tmp_path):
    stale = _make_staging_dir(tmp_path, f"{STAGING_DIR_PREFIX}old", age_hours=48)
    fresh = _make_staging_dir(tmp_path, f"{STAGING_DIR_PREFIX}new", age_hours=1)

    removed = cleanup_stale_staging_dirs(max_age_hours=24, base_dir=tmp_path)

    assert removed == 1
    assert not stale.exists()
    assert fresh.exists()


def test_ignores_unrelated_directories(tmp_path):
    unrelated = tmp_path / "some_other_dir"
    unrelated.mkdir()
    old_time = time.time() - 48 * 3600
    os.utime(unrelated, (old_time, old_time))

    removed = cleanup_stale_staging_dirs(max_age_hours=24, base_dir=tmp_path)

    assert removed == 0
    assert unrelated.exists()


def test_no_staging_dirs_present_returns_zero(tmp_path):
    assert cleanup_stale_staging_dirs(max_age_hours=24, base_dir=tmp_path) == 0


def test_missing_base_dir_returns_zero(tmp_path):
    missing = tmp_path / "does_not_exist"
    assert cleanup_stale_staging_dirs(max_age_hours=24, base_dir=missing) == 0
