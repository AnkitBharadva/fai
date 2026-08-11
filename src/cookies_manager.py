"""Cookies Manager module for rotating Netscape-format cookie files."""

import random
from pathlib import Path
from typing import List, Optional


class CookiesManager:
    """Manages and rotates cookie files from a file or directory."""

    def __init__(self, cookies_input: Optional[str] = "cookies"):
        self.cookies_files: List[Path] = []
        self._index = 0
        self._init_cookies(cookies_input)

    def _init_cookies(self, input_path: Optional[str]) -> None:
        if not input_path:
            input_path = "cookies"

        path = Path(input_path)
        if path.is_file() and path.exists():
            self.cookies_files.append(path.resolve())
        elif path.is_dir() and path.exists():
            for f in path.glob("*.txt"):
                if f.is_file() and f.stat().st_size > 0:
                    self.cookies_files.append(f.resolve())

        # Also check relative ./cookies directory as fallback
        if not self.cookies_files:
            default_dir = Path("cookies")
            if default_dir.is_dir() and default_dir.exists():
                for f in default_dir.glob("*.txt"):
                    if f.is_file() and f.stat().st_size > 0:
                        self.cookies_files.append(f.resolve())

    def get_cookie_file(self) -> Optional[str]:
        """Return path to a rotated cookie file, or None if no cookie files are available."""
        if not self.cookies_files:
            return None

        cookie_path = self.cookies_files[self._index % len(self.cookies_files)]
        self._index = (self._index + 1) % len(self.cookies_files)
        return str(cookie_path)

    def get_random_cookie_file(self) -> Optional[str]:
        """Return a randomly chosen cookie file path."""
        if not self.cookies_files:
            return None
        return str(random.choice(self.cookies_files))
