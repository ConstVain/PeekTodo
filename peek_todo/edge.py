"""边缘判定：光标贴右边 -> 展开；离开面板 -> 延时收回。纯逻辑，可单测。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height


class EdgeDetector:
    def __init__(
        self,
        panel_width: int,
        panel_height: int,
        hot_zone: int = 3,
        hide_delay_ms: int = 120,
        hot_zone_pad: int = 0,
    ):
        self.panel_width = panel_width
        self.panel_height = panel_height
        self.hot_zone = hot_zone
        self.hot_zone_pad = hot_zone_pad
        self.hide_delay_ms = hide_delay_ms
        self.shown = False
        self._hide_at: float | None = None

    def panel_rect(self, screen: Rect) -> Rect:
        top = screen.y + round((screen.height - self.panel_height) / 2)
        return Rect(screen.right - self.panel_width, top, self.panel_width, self.panel_height)

    def in_hot_zone(self, pos: tuple[int, int], screen: Rect) -> bool:
        x, y = pos
        panel = self.panel_rect(screen)
        pad = self.hot_zone_pad
        return (
            screen.right - self.hot_zone <= x <= screen.right + 1
            and panel.y - pad <= y <= panel.bottom + pad
        )

    def in_panel(self, pos: tuple[int, int], screen: Rect) -> bool:
        x, y = pos
        r = self.panel_rect(screen)
        return r.x <= x <= r.right and r.y <= y <= r.bottom

    def update(self, pos: tuple[int, int], screen: Rect, now_ms: float) -> tuple[bool, str]:
        in_hot = self.in_hot_zone(pos, screen)
        in_panel = self.in_panel(pos, screen)

        if in_hot:
            self.shown = True
            self._hide_at = None
        elif in_panel:
            if self.shown:
                self._hide_at = None
        elif self.shown:
            if self._hide_at is None:
                self._hide_at = now_ms + self.hide_delay_ms
            elif now_ms >= self._hide_at:
                self.shown = False
                self._hide_at = None

        return self.shown, ("hot" if in_hot else "panel" if in_panel else "idle")
