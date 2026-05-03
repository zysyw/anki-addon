# -*- coding: utf-8 -*-
from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Optional
from mdict_utils.reader import query


def _strip(html: str) -> str:
    return re.sub(r"<[^>]+>", "", html).strip()


@dataclass
class DictEntry:
    word: str
    pos: str = ""
    phonetic: str = ""
    definition_zh: str = ""      # 首条中文释义（纯文本，显示在背面醒目位置）
    definition_html: str = ""    # 全部义项（HTML，含编号+例句）
    example_en: str = ""
    example_zh: str = ""
    audio_us_key: str = ""
    audio_uk_key: str = ""
    example_audio_key: str = ""


class DictService:
    """LDOCE6++ En-Cn MDX/MDD 封装，提供查词和音频提取。"""

    def __init__(self, mdx_path: str, mdd_path: str) -> None:
        self.mdx_path = mdx_path
        self.mdd_path = mdd_path

    # ── 公开接口 ──────────────────────────────────────────

    def lookup(self, word: str) -> Optional[DictEntry]:
        html = self._fetch_html(word)
        if not html:
            return None
        return self._parse(word, html)

    def get_audio(self, mdd_key: str) -> Optional[bytes]:
        if not mdd_key:
            return None
        key = "\\" + mdd_key.replace("/", "\\")
        data = query(self.mdd_path, key)
        return data if data else None

    # ── 内部方法 ─────────────────────────────────────────

    def _fetch_html(self, word: str) -> Optional[str]:
        r = query(self.mdx_path, word)
        if not r:
            return None
        html = r.decode("utf-8") if isinstance(r, bytes) else r
        if html.startswith("@@@LINK="):
            return self._fetch_html(html[8:].strip())
        return html

    def _parse(self, word: str, html: str) -> DictEntry:
        e = DictEntry(word=word)

        # 音标
        m = re.search(r'<span class="pron">(.*?)</span>', html, re.DOTALL)
        if m:
            e.phonetic = "/" + _strip(m.group(1)) + "/"

        # 词性
        m = re.search(r'<span class="pos(?!\s*newfamily)"[^>]*>(.*?)</span>', html)
        if m:
            e.pos = _strip(m.group(1))

        # 语法（[C] [U] 等）
        gram_m = re.search(r'<span class="gram">(.*?)</span>', html)
        gram = _strip(gram_m.group(1)) if gram_m else ""

        # 首条中文释义（纯文本，醒目展示）
        m = re.search(r'<TRAN>(.*?)</TRAN>', html)
        if m:
            e.definition_zh = _strip(m.group(1))

        # 全部义项 HTML
        e.definition_html = self._build_definition_html(html, e.pos, gram)

        # 首个词典例句
        m = re.search(r'<EXAEN>(.*?)</EXAEN>', html, re.DOTALL)
        if m:
            e.example_en = _strip(m.group(1)).strip()
        m = re.search(r'<EXAMPLE>(.*?)</EXAMPLE>', html)
        if m:
            e.example_zh = _strip(m.group(1))

        # 音频路径
        m = re.search(r'href="sound://(hwd/ame/[^"]+\.mp3)"', html)
        if m:
            e.audio_us_key = m.group(1)
        m = re.search(r'href="sound://(hwd/bre/[^"]+\.mp3)"', html)
        if m:
            e.audio_uk_key = m.group(1)
        m = re.search(r'href="sound://(exa/[^"]+\.mp3)"', html)
        if m:
            e.example_audio_key = m.group(1)

        return e

    @staticmethod
    def _build_definition_html(html: str, pos: str, gram: str) -> str:
        """
        提取 LDOCE6++ 的全部义项，生成用于 Anki 背面的 HTML 片段。
        按实际内容中的 <span class="sensenum"> 分割（紧跟 < 的是正文，后跟空格的是弹出菜单）。
        仅处理首个词性分区（entryhead 之前），最多显示 7 个义项。
        """
        lines = []
        hd = f"{pos} {gram}".strip()
        if hd:
            lines.append(f'<div class="dd-hd">{hd}</div>')

        # 只取首个词性分区（第二个 entryhead 之前的部分）
        first = html.find('<span class="entryhead">')
        second = html.find('<span class="entryhead">', first + 1)
        primary = html if second == -1 else html[:second]

        # 优先按正文义项编号分割（紧跟 < = 正文内容；后跟空格 = 弹出菜单，跳过）
        # 若无 sensenum（单义项词），退回到 <span class="sense"> 分割
        blocks = re.split(r'<span class="sensenum">\d+</span>(?=<)', primary)
        if len(blocks) <= 1:
            blocks = re.split(r'<span class="sense"[^>]*>', primary)

        num = 0
        for block in blocks[1:]:
            tran_m = re.search(r'<TRAN>(.*?)</TRAN>', block)
            if not tran_m:
                continue
            num += 1
            if num > 7:
                break
            zh_def = _strip(tran_m.group(1))

            exaen_m = re.search(r'<EXAEN>(.*?)</EXAEN>', block, re.DOTALL)
            ex_m = re.search(r'<EXAMPLE>(.*?)</EXAMPLE>', block)
            en_exa = _strip(exaen_m.group(1)) if exaen_m else ""
            zh_exa = _strip(ex_m.group(1)) if ex_m else ""

            lines.append(f'<div class="dd-sense"><b>{num}.</b> {zh_def}</div>')
            if en_exa:
                lines.append(f'<div class="dd-exa">{en_exa}</div>')
            if zh_exa:
                lines.append(f'<div class="dd-zh">{zh_exa}</div>')

        return "\n".join(lines)


# ── 测试 ──────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    from dotenv import load_dotenv
    import os
    load_dotenv()

    svc = DictService(
        mdx_path=os.getenv("LDOCE6_MDX"),
        mdd_path=os.getenv("LDOCE6_MDD"),
    )

    for word in ["trick", "resilience", "eloquent"]:
        entry = svc.lookup(word)
        if entry:
            print(f"=== {word} ===")
            print(f"  词性: {entry.pos}  音标: {entry.phonetic}")
            print(f"  首条释义: {entry.definition_zh}")
            print(f"  全部义项 HTML:\n{entry.definition_html}")
        else:
            print(f"=== {word} === 未找到")
        print()
