# splitter.py
from __future__ import annotations
import re
import unicodedata
from typing import List, Iterable

class Splitter:
    """
    把输入的“中文逗号分隔串”拆成条目列表的工具类。

    特点：
      - 默认仅以中文逗号（，）分割；可切换为宽松模式（同时识别 , / 、）。
      - 归一化：NFKC 规范化、去首尾空白、把内部连续空白折叠为单空格（便于短语判定）。
      - 过滤空项；可选去重（保序）。
    """

    def __init__(
        self,
        strict_cn_comma: bool = True,    # True: 仅中文逗号；False: 同时识别英文逗号、顿号
        dedup: bool = True,              # 是否去重（保序）
        collapse_inner_spaces: bool = True,  # 折叠内部空白为单空格
    ) -> None:
        self.strict_cn_comma = strict_cn_comma
        self.dedup = dedup
        self.collapse_inner_spaces = collapse_inner_spaces

        if strict_cn_comma:
            # 仅按中文逗号分割
            self._split_pattern = re.compile(r"，+")
        else:
            # 宽松：中文逗号、英文逗号、顿号都当分隔符
            self._split_pattern = re.compile(r"[，,、]+")

        # 用于折叠内部空白
        self._space_re = re.compile(r"\s+")

    # ---- 对外主接口 ----
    def split(self, text: str) -> List[str]:
        """
        返回清洗后的 item 列表。
        """
        if not text:
            return []

        # 1) 统一规范化（不改变全角/半角等）
        norm = unicodedata.normalize("NFC", text).strip()

        # 2) 分割
        parts = self._split_pattern.split(norm)

        # 3) 清洗每个条目
        cleaned = [self._clean_segment(seg) for seg in parts]
        cleaned = [x for x in cleaned if x]  # 过滤空项

        # 4) 可选去重（保序）
        if self.dedup:
            cleaned = self._dedup_ordered(cleaned)

        return cleaned

    # ---- 内部工具 ----
    def _clean_segment(self, seg: str) -> str:
        """
        对分割出的片段做轻量清洗：
          - trim
          - 折叠内部空白为单空格（便于后续“是否短语”判断）
        """
        s = seg.strip()
        if not s:
            return ""
        if self.collapse_inner_spaces:
            s = self._space_re.sub(" ", s)
        return s

    @staticmethod
    def _dedup_ordered(items: Iterable[str]) -> List[str]:
        seen = set()
        out: List[str] = []
        for x in items:
            # 去重时用原样字符串作为键（区分大小写）
            if x not in seen:
                seen.add(x)
                out.append(x)
        return out

if __name__ == "__main__":
    # 测试
    splitter = Splitter(strict_cn_comma=True, dedup=True)

    tests = [
        "apple, banana, orange",
        "apple， banana， orange",
        "apple、 banana、 orange",
        "  apple  ,   banana  ,   orange  ",
        "apple, banana, apple, orange, banana",
        "apple,,banana,,,orange,,",
        "apple，banana、orange,pear",
        "  apple  ，   banana  、   orange  ， pear ",
        "apple, , ,banana, , ,orange, , ",
        "",
        "   ",
        "apple",
        "  apple  ",
    ]

    for i, test in enumerate(tests):
        result = splitter.split(test)
        print(f"Test {i+1}: {test!r} => {result}")