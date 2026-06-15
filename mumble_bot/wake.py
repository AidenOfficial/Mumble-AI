"""唤醒词匹配 + query 提取。

主路：正则匹配（独特短语，别撞手机助手）。命中后取唤醒词之后的文本为 query；
若为空，调用方应等下一句（见 orchestrator/main 的 follow-up 逻辑）。
可选：rapidfuzz 模糊兜底（应对 STT 把"豆沙"听成近音字），需在 config 配 wake_fuzzy_terms。
v2 可换 Porcupine 端侧唤醒。
"""

from __future__ import annotations

import re

try:
    from rapidfuzz import fuzz
except ImportError:  # rapidfuzz 可选
    fuzz = None

_STRIP = " \t，,。.！!？?、~"


class WakeMatcher:
    def __init__(self, regex: str, fuzzy_threshold: int = 0, fuzzy_terms=None):
        self._re = re.compile(regex)
        self._threshold = fuzzy_threshold
        self._fuzzy_terms = list(fuzzy_terms or [])

    def match(self, text: str) -> tuple[bool, str]:
        """返回 (是否命中, 唤醒词之后的 query 文本)。未命中返回 (False, "")。"""
        if not text:
            return False, ""
        m = self._re.search(text)
        if m:
            return True, text[m.end():].strip(_STRIP)
        if fuzz is not None and self._threshold > 0 and self._fuzzy_terms:
            for term in self._fuzzy_terms:
                if fuzz.partial_ratio(term, text) >= self._threshold:
                    # 模糊命中难以精确定位唤醒词边界，整句作为 query 交给 LLM
                    return True, text.strip(_STRIP)
        return False, ""
