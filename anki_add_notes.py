# -*- coding: utf-8 -*-
# anki_add_notes.py
"""
- ItemFactory：把文本条目构造成领域对象（单词 or 短语）
- ProcessorFactory：为不同 Item 选择对应处理器（WordProcessor / PhraseProcessor）
- NoteBuilder：将处理结果规范为可写入 Anki 的字段字典（预留扩展点）
- Coordinator：编排整体流程：拆分 -> 构造 Item -> 处理 -> 构建 Note -> 写入 Anki
"""

from __future__ import annotations
import re
import time
from dataclasses import dataclass
from typing import List, Optional, Dict, Protocol, Union

# --- 你已完成并可直接导入的类（此处不重复实现） ---
from LLMServer import LLMService
from splitter import Splitter
from anki_service import AnkiService
from word_processor import WordProcessor, WordItem
from phrase_processor import PhraseProcessor, PhraseItem  # 已支持从原始字符串解析 ^b 并 Cloze；答案=中文翻译


Item = Union[WordItem, PhraseItem]


# ========= 工厂：ItemFactory =========
class ItemFactory:
    """将输入的文本条目构造成领域对象。"""

    @staticmethod
    def from_text(text: str) -> Optional[Item]:
        t = (text or "").strip()
        if not t:
            return None
        # 有空格 -> 短语
        if re.search(r"\s", t):
            return PhraseItem(phrase_raw=t)
        # 无空格 -> 单词
        return WordItem(word=t)


# ========= 工厂：ProcessorFactory =========

class ProcessorFactory:
    """根据 Item 类型返回对应处理器实例。"""

    def __init__(self, wp: WordProcessor, pp: PhraseProcessor):
        self.wp = wp
        self.pp = pp

    def for_item(self, item: Item) -> Union[WordProcessor, PhraseProcessor]:
        if isinstance(item, WordItem):
            return self.wp
        elif isinstance(item, PhraseItem):
            return self.pp
        raise TypeError(f"不支持的 Item 类型：{type(item)}")

# ========= NoteBuilder =========
class NoteBuilder:
    """
    负责把处理器输出的 content（字段字典）构造成“可写入 Anki”的字段结构。
    现在做法很轻：直接透传；预留钩子，便于未来对不同模型做字段重映射/合并/附加多媒体等。
    """

    def __init__(self, model_name: str = "newFastWQ"):
        self.model_name = model_name

    def build(self, content_fields: Dict[str, str]) -> Dict[str, str]:
        """
        输入：处理器产出的字段字典（Word/Example 或 Expression/Question/Answer 等）
        输出：可交给 AnkiService.add_note 的 fields（保持键值）
        """
        return dict(content_fields)  # 目前直接透传；需要时可在此处做模型定制映射


# ========= 协调器 =========
class Coordinator:
    """
    编排总流程：Splitter -> ItemFactory -> ProcessorFactory -> NoteBuilder -> AnkiService
    """

    def __init__(
        self,
        splitter: Splitter,
        deck: str,
        llm: LLMService,
        builder: NoteBuilder = NoteBuilder(),
        *,
        sleep_between: float = 0.3,
        verbose: bool = True,
    ) -> None:
        self.splitter = splitter
        self.deck = deck
        self.builder = builder
        # 处理器（按你的实现，默认输出精确字段名）
        self.wp = WordProcessor(llm, use_generic_keys=False)         # -> {"Word","Example"}
        self.pp = PhraseProcessor(llm, use_generic_keys=False)       # -> {"Expression","Question","Answer"}
        self.proc_factory = ProcessorFactory(self.wp, self.pp)
        self.sleep_between = sleep_between
        self.verbose = verbose

    def run(self, input_cn: str) -> List[Optional[int]]:
        parts = self.splitter.split(input_cn)
        if self.verbose:
            print(f"▶ 待处理 {len(parts)} 项：{parts}")

        note_ids: List[Optional[int]] = []
        for text in parts:
            try:
                item = ItemFactory.from_text(text)
                if item is None:
                    if self.verbose:
                        print(f"• 跳过空条目: {text!r}")
                    note_ids.append(None)
                    continue

                processor = self.proc_factory.for_item(item)
                fields = processor.produce_fields(item)  # 字段字典（精确字段名）
                built_fields = self.builder.build(fields)

                if self.verbose:
                    kind = "短语" if isinstance(item, PhraseItem) else "单词"
                    print(f"• {kind}: {text} -> {built_fields}")

                anki = AnkiService(deck=self.deck, model=item.model_name, default_tags=[self.deck, item.model_name, "auto"])
                nid = anki.add_note(built_fields)
                note_ids.append(nid)
                if self.verbose:
                    print(f"  ✓ 写入 Anki: noteId = {nid}")
            except Exception as e:
                note_ids.append(None)
                print(f"  ✗ 失败: {text} -> {e}")
            if self.sleep_between > 0:
                time.sleep(self.sleep_between)

        if self.verbose:
            ok = sum(1 for x in note_ids if x is not None)
            print(f"\n完成：成功 {ok} / {len(parts)}，noteIds = {note_ids}")
        return note_ids


# ========= 测试程序 =========
if __name__ == "__main__":
    """
    运行前准备：
      1) 你的 llm_server.py 已实现 LLMServer（含 make_word_sentence / make_phrase_paragraph / translate_to_zh）
      2) 打开 Anki 并启用 Anki-Connect；设置好环境变量（如 DEEPSEEK_API_KEY）
      3) newFastWQ 模型存在（或让 FieldMapper 兼容映射）；牌组名默认 'oulu'
    """
    # 依赖实例
    splitter = Splitter(strict_cn_comma=True, dedup=True, collapse_inner_spaces=True)

    DECK_NAME = "oule"  # 请按需修改为你已有的牌组名

    llm = LLMService()

    app = Coordinator(
        splitter=splitter,
        deck=DECK_NAME,
        llm=llm,
        sleep_between=0.4,
        verbose=True,
    )

    # 测试输入：混合单词 & 短语；短语可含 ^b 标注填空词
    demo = "aurora，metabolism，^bmachine learning，renewable energy，deep neural network"

    app.run(demo)
