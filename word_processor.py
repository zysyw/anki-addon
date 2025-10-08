# -*- coding: utf-8 -*-
# word_processor.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict

# 自己的服务类
from LLMServer import LLMService
from anki_service import AnkiService


# ---- 领域对象 ----
@dataclass
class WordItem:
    """单词项（不含空格）"""
    word: str
    
    """Anki 字段字典"""
    model_name: str = "newFastWQ"  # 默认模型名（可按需修改）
    word_key: str = "单词"          # 通用字段名term
    example_key: str = "例句"    # 通用字段名example


# ---- 处理器类 ----
class WordProcessor:
    """
    单词处理器：
      - 输入：WordItem（不含空格的“单词”）
      - 调用 LLMServer 生成一个简洁自然的英文例句
      - 输出：交给 AnkiService 的字段字典（默认使用“精确字段名”）
    """

    def __init__(
        self,
        llm: LLMService,
        *,
        use_generic_keys: bool = False,  # 默认返回精确字段名
    ) -> None:
        """
        :param llm: 你已实现好的 LLMService 实例，需包含 make_word_sentence(word: str) -> str
        """
        self.llm = llm
        self.use_generic_keys = use_generic_keys

    # --- 对外主接口 ---
    def produce_fields(self, item: WordItem) -> Dict[str, str]:
        """
        根据给定的 WordItem 生成用于 Anki 的字段字典。
        """
        w = (item.word or "").strip()
        if not w or (" " in w):
            raise ValueError(f"WordProcessor 仅处理单词（不含空格）：{item.word!r}")

        sentence = (self.llm.make_word_sentence(w) or "").strip()
        if not sentence:
            # 最小兜底，避免空字符串导致后续写卡失败
            sentence = f"I learned the word '{w}' today."

        if self.use_generic_keys:
            return {"term": w, "example": sentence}
        else:
            return {item.word_key: w, item.example_key: sentence}

# ---- 示例运行 ----
if __name__ == "__main__":
    """
    运行前提：
      1) 你的 LLMServer.py 中已实现 LLMService 类，并提供 make_word_sentence(word) 方法
      2) 若 LLMService 依赖 DEEPSEEK_API_KEY，请确保环境变量已设置
    """
    # 初始化你自己的 LLMService
    llm = LLMService()

    item = WordItem(word="metabolism")
    
    # 默认：返回精确字段（use_generic_keys=False）
    wp = WordProcessor(llm)
    fields = wp.produce_fields(item)
    print("精确字段 ->", fields)

    # 如需返回通用键（交给 FieldMapper 去映射），可改为：
    wp_generic = WordProcessor(llm, use_generic_keys=True)
    fields_generic = wp_generic.produce_fields(item)
    print("通用键   ->", fields_generic)

    # （可选）集成写入 Anki
    anki = AnkiService(deck="oule", model=item.model_name, default_tags=["oulu",item.model_name,"auto"])
    note_id = anki.add_note(fields)  # 或 fields_generic
    print("写入 Anki 的 noteId:", note_id)
