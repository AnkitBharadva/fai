"""Unit tests for CookiesManager rotation."""

import tempfile
from pathlib import Path
from src.cookies_manager import CookiesManager


def test_cookies_manager_rotation():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        c1 = tmp / "jaman.txt"
        c2 = tmp / "magan.txt"
        c1.write_text("cookie1")
        c2.write_text("cookie2")

        manager = CookiesManager(str(tmp))
        assert len(manager.cookies_files) == 2

        f1 = manager.get_cookie_file()
        f2 = manager.get_cookie_file()
        f3 = manager.get_cookie_file()

        assert f1 != f2
        assert f1 == f3
