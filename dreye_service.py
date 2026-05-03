# -*- coding: utf-8 -*-
"""
译典通 (Dr.eye) 在线查词服务
URL: https://yun.dreye.com/dict_new/dict.php?w=WORD&hidden_codepage=01
"""
from __future__ import annotations
import re
import warnings
from dataclasses import dataclass, field
from typing import Optional

import requests
from bs4 import BeautifulSoup
import opencc

_cc = opencc.OpenCC('t2s')          # 繁→简转换器
_SESSION = requests.Session()
_SESSION.headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'

_URL = 'https://yun.dreye.com/dict_new/dict.php?w={}&hidden_codepage=01'
_MAX_SENSES = 6     # 每个词性最多显示义项数
_MAX_POS    = 2     # 最多显示词性分区数（名词+动词即可，不需要全部）


@dataclass
class DreyeEntry:
    word: str
    phonetic: str = ""
    definition_html: str = ""   # 已转简体的多义项 HTML


class DreyeService:
    """译典通在线词典封装，返回简体中文多义项释义 HTML。"""

    def lookup(self, word: str) -> Optional[DreyeEntry]:
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            try:
                r = _SESSION.get(_URL.format(word), timeout=8, verify=False)
            except Exception as e:
                raise RuntimeError(f"译典通请求失败: {e}") from e

        r.encoding = 'utf-8'
        soup = BeautifulSoup(r.text, 'html.parser')

        entry = DreyeEntry(word=word)

        phon = soup.find('span', class_='phonetic')
        if phon:
            entry.phonetic = phon.get_text(strip=True)

        usual = soup.find('div', id='usual')
        if usual:
            entry.definition_html = self._parse_usual(usual)

        return entry if entry.definition_html else None

    # ── 内部解析 ──────────────────────────────────────────

    @staticmethod
    def _t2s(text: str) -> str:
        return _cc.convert(text)

    def _parse_usual(self, usual) -> str:
        """
        解析 div#usual：
          - div.sg.block 包含所有词性分区
          - p.attr       词性标注（如 n.[C]、vt.、a.）
          - ol > li      每条义项；li 内 div.exp 有例句
        """
        sg = usual.find('div', class_='sg')
        if not sg:
            return ""

        lines: list[str] = []
        current_pos = ""
        sense_global = 0    # 跨词性的连续编号
        pos_count = 0       # 已处理的词性分区数

        for child in sg.children:
            if not hasattr(child, 'name'):
                continue

            if child.name == 'p' and 'attr' in child.get('class', []):
                # 新词性分区
                pos_count += 1
                if pos_count > _MAX_POS:
                    break
                current_pos = self._t2s(child.get_text(strip=True))
                lines.append(f'<div class="dd-hd">{current_pos}</div>')
                sense_global = 0    # 每个词性分区内重新从1编号

            elif child.name == 'ol':
                for li in child.find_all('li', recursive=False):
                    sense_global += 1
                    if sense_global > _MAX_SENSES:
                        break

                    # 中文释义：只取 li 的直接子节点文本（跳过 div.exp 和 img）
                    from bs4 import NavigableString
                    zh_parts = []
                    for node in li.children:
                        if isinstance(node, NavigableString):
                            zh_parts.append(str(node))
                        elif hasattr(node, 'name') and node.name not in ('div', 'img'):
                            zh_parts.append(node.get_text())
                    zh_def = self._t2s(re.sub(r'\s+', ' ', ''.join(zh_parts)).strip())
                    if not zh_def:
                        continue
                    lines.append(
                        f'<div class="dd-sense"><b>{sense_global}.</b> {zh_def}</div>'
                    )

                    # 例句（取 div.exp 里的第一对英文句+中文翻译）
                    exp = li.find('div', class_='exp')
                    if exp:
                        # 英文：exp 的直接子节点（NavigableString + em.col），遇到 <p> 停止
                        en_parts = []
                        for node in exp.children:
                            if isinstance(node, NavigableString):
                                en_parts.append(str(node))
                            elif hasattr(node, 'name') and node.name == 'em':
                                en_parts.append(node.get_text())
                            elif hasattr(node, 'name') and node.name == 'p':
                                break
                        en_sentence = re.sub(r'\s+', ' ', ''.join(en_parts)).strip()

                        # 中文：第一个 <p> 标签
                        p_zh = exp.find('p')
                        zh_sentence = self._t2s(p_zh.get_text(strip=True)) if p_zh else ""

                        if en_sentence:
                            lines.append(f'<div class="dd-exa">{en_sentence}</div>')
                        if zh_sentence:
                            lines.append(f'<div class="dd-zh">{zh_sentence}</div>')

        return '\n'.join(lines)


# ── 测试 ──────────────────────────────────────────────────
if __name__ == '__main__':
    import sys
    sys.stdout.reconfigure(encoding='utf-8')

    svc = DreyeService()
    for w in ['eloquent', 'trick', 'resilience', 'perseverance']:
        entry = svc.lookup(w)
        print(f'=== {w} ===')
        if entry:
            print(f'音标: {entry.phonetic}')
            print(entry.definition_html)
        else:
            print('未找到')
        print()
