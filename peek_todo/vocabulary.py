"""时间词的识别。

原则：不写死正则，词表可配置，识别不出就当"未识别"返回 None，绝不抛错。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .model import When

# 内置词表：覆盖常见写法，用户可以在 config 里加
WEEKDAY_TOKENS: dict[int, list[str]] = {
    0: ["周一", "星期一", "礼拜一", "周1", "星期1"],
    1: ["周二", "星期二", "礼拜二", "周2", "星期2"],
    2: ["周三", "星期三", "礼拜三", "周3", "星期3"],
    3: ["周四", "星期四", "礼拜四", "周4", "星期4"],
    4: ["周五", "星期五", "礼拜五", "周5", "星期5"],
    5: ["周六", "星期六", "礼拜六", "周6", "星期6"],
    6: ["周日", "周天", "星期日", "星期天", "礼拜日", "礼拜天", "周7", "星期7"],
}

PERIOD_TOKENS: dict[str, list[str]] = {
    "上午": ["上午", "早上", "早晨", "晨"],
    "下午": ["下午", "午后"],
    "晚上": ["晚上", "晚间", "夜里", "夜"],
}

# 「周X」这种紧凑写法，词表没收录时兜底用
_WEEKDAY_RE = re.compile(r"(?:周|星期|礼拜)\s*([一二三四五六日天1-7])")
_DIGIT_TO_WEEKDAY = {
    "一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6,
    "1": 0, "2": 1, "3": 2, "4": 3, "5": 4, "6": 5, "7": 6,
}


def _normalize(text: str) -> str:
    text = (text or "").strip()
    # 去掉常见装饰：括号、书名号、全角空格
    text = text.replace("\u3000", " ")
    return text


@dataclass
class Vocabulary:
    weekdays: dict[int, list[str]] = field(default_factory=lambda: {k: list(v) for k, v in WEEKDAY_TOKENS.items()})
    periods: dict[str, list[str]] = field(default_factory=lambda: {k: list(v) for k, v in PERIOD_TOKENS.items()})

    @classmethod
    def from_config(cls, raw: dict | None) -> "Vocabulary":
        vocab = cls()
        raw = raw or {}
        for canonical, extra in (raw.get("weekdays") or {}).items():
            index = _weekday_index(canonical)
            if index is None:
                continue
            vocab.weekdays.setdefault(index, [])
            for token in extra:
                if token not in vocab.weekdays[index]:
                    vocab.weekdays[index].append(token)
        for canonical, extra in (raw.get("periods") or {}).items():
            vocab.periods.setdefault(canonical, [])
            for token in extra:
                if token not in vocab.periods[canonical]:
                    vocab.periods[canonical].append(token)
        return vocab

    def weekday_tokens(self) -> list[tuple[str, int]]:
        """按 token 长度倒序，保证「星期一」先于「一」命中。"""
        pairs = [(token, index) for index, tokens in self.weekdays.items() for token in tokens]
        return sorted(pairs, key=lambda p: len(p[0]), reverse=True)

    def period_tokens(self) -> list[tuple[str, str]]:
        pairs = [(token, name) for name, tokens in self.periods.items() for token in tokens]
        return sorted(pairs, key=lambda p: len(p[0]), reverse=True)


def _weekday_index(label: str) -> int | None:
    match = _WEEKDAY_RE.search(label or "")
    if not match:
        return None
    return _DIGIT_TO_WEEKDAY.get(match.group(1))


def parse_when(text: str, vocabulary: Vocabulary, aliases: dict[str, str] | None = None) -> When | None:
    """把「周一下午」这类标题解析成 When；认不出返回 None。"""
    label = _normalize(text)
    aliases = aliases or {}

    # 用户点选纠正过的写法，优先级最高
    if label in aliases:
        label = aliases[label]

    weekday: int | None = None
    for token, index in vocabulary.weekday_tokens():
        if token and token in label:
            weekday = index
            break
    if weekday is None:
        match = _WEEKDAY_RE.search(label)
        if match:
            weekday = _DIGIT_TO_WEEKDAY.get(match.group(1))

    period: str | None = None
    for token, name in vocabulary.period_tokens():
        if token and token in label:
            period = name
            break

    if weekday is None and period is None:
        return None
    return When(weekday=weekday, period=period)


def describe_when(when: When | None) -> str:
    if when is None:
        return "未识别"
    names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    parts = []
    if when.weekday is not None:
        parts.append(names[when.weekday])
    if when.period is not None:
        parts.append(when.period)
    return "".join(parts) if parts else "未识别"
