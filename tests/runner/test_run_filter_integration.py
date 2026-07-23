"""Integration test: Run class + post-download filter plumbing.

Uses fake_icloudpd in filter_demo mode to create real image files, then asserts
that the filter deletes the right ones.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from icloudpd_web.runner.run import Run
from icloudpd_web.store.models import Filters


def _argv(fake_icloudpd_cmd: list[str], target_dir: str) -> list[str]:
    return [
        *fake_icloudpd_cmd,
        "--username",
        "u@icloud.com",
        "--directory",
        target_dir,
        "--password-provider",
        "console",
    ]


@pytest.mark.asyncio
async def test_filter_demo_keeps_heic_apple_only(
    tmp_path: Path,
    fake_icloudpd_cmd: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """filter_demo creates three files; filter for .heic AND Apple.

    Expected:
      - img_apple.heic: kept (suffix matches, EXIF Make=Apple matches)
      - img_samsung.jpg: deleted (suffix .jpg not in [.heic])
      - other.png: deleted (suffix .png not in [.heic])
    """
    target_dir = tmp_path / "photos"
    target_dir.mkdir()

    monkeypatch.setenv("FAKE_ICLOUDPD_MODE", "filter_demo")
    monkeypatch.setenv("FAKE_ICLOUDPD_DIR", str(target_dir))

    filters = Filters(file_suffixes=[".heic"], device_makes=["Apple"])

    run = Run(
        run_id="test-filter-1",
        policy_name="test-policy",
        argv=_argv(fake_icloudpd_cmd, str(target_dir)),
        log_dir=tmp_path / "logs",
        password="pw",
        filters=filters,
        # Needed to resolve icloudpd's middle-truncated Downloaded paths
        # (pytest tmp paths routinely exceed the 96-char truncation limit).
        target_directory=target_dir,
    )
    await run.start()
    await run.wait()

    assert run.status == "success", f"Run failed: {run.exit_code}"

    apple_heic = target_dir / "img_apple.heic"
    samsung_jpg = target_dir / "img_samsung.jpg"
    other_png = target_dir / "other.png"

    assert apple_heic.exists(), "img_apple.heic should be kept"
    assert not samsung_jpg.exists(), "img_samsung.jpg should be deleted"
    assert not other_png.exists(), "other.png should be deleted"

    log_text = run.log_path.read_text()
    assert "Filter: kept" in log_text
    assert "Filter: deleted" in log_text
    assert "Filter summary: kept 1, deleted 2" in log_text


@pytest.mark.asyncio
async def test_filter_with_no_filters_keeps_all(
    tmp_path: Path,
    fake_icloudpd_cmd: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Empty Filters object → nothing deleted."""
    target_dir = tmp_path / "photos2"
    target_dir.mkdir()

    monkeypatch.setenv("FAKE_ICLOUDPD_MODE", "filter_demo")
    monkeypatch.setenv("FAKE_ICLOUDPD_DIR", str(target_dir))

    # No filters: Run gets filters=None → filter step skipped entirely.
    run = Run(
        run_id="test-filter-2",
        policy_name="test-policy",
        argv=_argv(fake_icloudpd_cmd, str(target_dir)),
        log_dir=tmp_path / "logs2",
        password="pw",
        filters=None,
    )
    await run.start()
    await run.wait()

    assert run.status == "success"

    # All three files should exist since no filter was applied.
    assert (target_dir / "img_apple.heic").exists()
    assert (target_dir / "img_samsung.jpg").exists()
    assert (target_dir / "other.png").exists()

    log_text = run.log_path.read_text()
    assert "Filter:" not in log_text


@pytest.mark.asyncio
async def test_filter_device_make_only(
    tmp_path: Path,
    fake_icloudpd_cmd: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Filter only by device_makes=["Apple"]; Samsung jpg deleted, png kept (non-image)."""
    target_dir = tmp_path / "photos3"
    target_dir.mkdir()

    monkeypatch.setenv("FAKE_ICLOUDPD_MODE", "filter_demo")
    monkeypatch.setenv("FAKE_ICLOUDPD_DIR", str(target_dir))

    filters = Filters(device_makes=["Apple"])

    run = Run(
        run_id="test-filter-3",
        policy_name="test-policy",
        argv=_argv(fake_icloudpd_cmd, str(target_dir)),
        log_dir=tmp_path / "logs3",
        password="pw",
        filters=filters,
        target_directory=target_dir,
    )
    await run.start()
    await run.wait()

    assert run.status == "success"

    # Apple HEIC: Make=Apple → kept
    assert (target_dir / "img_apple.heic").exists()
    # Samsung JPG: Make=Samsung → deleted
    assert not (target_dir / "img_samsung.jpg").exists()
    # PNG: .png IS in _image_suffixes so EXIF is checked, but it has no EXIF
    # Make → fail-open: kept, with a WARNING logged.
    assert (target_dir / "other.png").exists()
    log_text = run.log_path.read_text()
    assert "WARNING  Filter: kept" in log_text


def test_resolve_downloaded_path_truncated(tmp_path: Path) -> None:
    """icloudpd middle-truncates >96-char paths in Downloaded lines; the Run
    must map them back to the real file (or skip when ambiguous)."""
    nested = tmp_path / ("a" * 60) / ("b" * 40)
    nested.mkdir(parents=True)
    real = nested / "IMG_0001.heic"
    real.write_bytes(b"x")

    run = Run(
        run_id="t",
        policy_name="p",
        argv=["true"],
        log_dir=tmp_path / "logs",
        target_directory=tmp_path,
    )

    full = str(real)
    assert len(full) > 96
    truncated = f"{full[:40]}...{full[-40:]}"
    assert run._resolve_downloaded_path(truncated) == real
    # Untruncated paths pass through untouched.
    assert run._resolve_downloaded_path(full) == real
    # Ambiguous/unresolvable tails are skipped.
    assert run._resolve_downloaded_path("nope...zzz_does_not_exist.jpg") is None
