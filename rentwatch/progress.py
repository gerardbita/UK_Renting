from __future__ import annotations

import sys
import time
from typing import TextIO


class ProgressBar:
    def __init__(
        self,
        label: str,
        *,
        total: int | None,
        unit: str,
        width: int = 24,
        stream: TextIO | None = None,
    ):
        self.label = label
        self.total = max(0, total or 0)
        self.unit = unit
        self.width = width
        self.stream = stream or sys.stdout
        self.current = 0
        self.started_at = time.monotonic()
        self.last_render_at = 0.0
        self.last_bucket = -1
        self.last_message = ""
        self.is_tty = bool(getattr(self.stream, "isatty", lambda: False)())

    def update(self, current: int, *, detail: str = "", force: bool = False) -> None:
        self.current = max(0, current)
        if not self.should_render(force=force):
            return
        self.render(detail=detail, final=False)

    def finish(self, *, detail: str = "") -> None:
        self.render(detail=detail, final=True)

    def should_render(self, *, force: bool = False) -> bool:
        if force:
            return True
        now = time.monotonic()
        if self.is_tty:
            return now - self.last_render_at >= 0.2
        if self.total <= 0:
            return now - self.last_render_at >= 10
        bucket = int((self.current / self.total) * 20)
        if bucket != self.last_bucket:
            self.last_bucket = bucket
            return True
        return False

    def render(self, *, detail: str, final: bool) -> None:
        self.last_render_at = time.monotonic()
        message = self.message(detail)
        if final and not self.is_tty and message == self.last_message:
            return
        self.last_message = message
        if self.is_tty:
            self.stream.write("\r\033[2K" + message)
            if final:
                self.stream.write("\n")
        else:
            self.stream.write(message + "\n")
        self.stream.flush()

    def message(self, detail: str) -> str:
        elapsed = max(0, int(time.monotonic() - self.started_at))
        if self.total > 0:
            ratio = min(1.0, self.current / self.total)
            filled = round(self.width * ratio)
            bar = "#" * filled + "-" * (self.width - filled)
            count = f"{self.current:,}/{self.total:,} {self.unit}"
            percent = f"{ratio * 100:5.1f}%"
        else:
            bar = "-" * self.width
            count = f"{self.current:,} {self.unit}"
            percent = "  n/a"
        suffix = f" | {detail}" if detail else ""
        return f"{self.label} [{bar}] {count} {percent} | {elapsed}s{suffix}"


def compact_detail(value: str, *, limit: int = 72) -> str:
    cleaned = " ".join(str(value or "").split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "..."
