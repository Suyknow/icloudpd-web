from __future__ import annotations

from pathlib import Path

import pytest

from icloudpd_web.runner.runner import Runner, _check_mounted
from icloudpd_web.store.models import Policy


def test_disabled_by_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("REQUIRE_MOUNTED_FILE", raising=False)
    _check_mounted(tmp_path / "photos")


@pytest.mark.parametrize("value", ["false", "0", "no", "off", "FALSE"])
def test_explicitly_disabled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("REQUIRE_MOUNTED_FILE", value)
    _check_mounted(tmp_path / "photos")


@pytest.mark.parametrize("value", ["1", "true", "yes", "on", "TRUE"])
def test_enabled_requires_sentinel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("REQUIRE_MOUNTED_FILE", value)
    with pytest.raises(RuntimeError, match="no .mounted sentinel"):
        _check_mounted(tmp_path / "photos")


def test_sentinel_in_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REQUIRE_MOUNTED_FILE", "true")
    target = tmp_path / "photos"
    target.mkdir()
    (target / ".mounted").touch()
    _check_mounted(target)


def test_sentinel_in_parent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REQUIRE_MOUNTED_FILE", "true")
    (tmp_path / ".mounted").touch()
    target = tmp_path / "photos" / "2026"
    target.mkdir(parents=True)
    _check_mounted(target)


@pytest.mark.asyncio
async def test_runner_start_refuses_without_sentinel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("REQUIRE_MOUNTED_FILE", "true")
    commands: list[list[str]] = []

    def fake_argv(argv_tail: list[str]) -> list[str]:
        commands.append(argv_tail)
        return ["true"]

    runner = Runner(runs_base=tmp_path / "runs", icloudpd_argv=fake_argv)
    policy = Policy(
        name="p",
        username="u@icloud.com",
        directory=tmp_path / "photos",
        cron="0 * * * *",
    )
    with pytest.raises(RuntimeError, match="no .mounted sentinel"):
        await runner.start(policy, password="pw", trigger="manual")
    assert commands == []
