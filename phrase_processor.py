# -*- coding: utf-8 -*-
# phrase_processor.py
from __future__ import annotations
import re
import random
from dataclasses import dataclass
from typing import Dict, Tuple

# 使用你已经实现好的 LLMServer（需含 make_phrase_paragraph(phrase:str)->str）
from LLMServer import LLMService


# ---------- 领域对象 ----------
@dataclass
class PhraseItem:
    """
    短语项
    说明：
      - phrase_raw 允许含 ^b 前缀来标注需要填空的词，例如：'^bmachine learning'
      - phrase 为去除 ^b 后的干净短语
      - target 为需要填空的词（若未标注，则在短语中随机选择一个英文词）
    """
    phrase_raw: str = ""  # 原始短语，可能含 ^b 标注
    phrase: str = ""  # 去除 ^b 后的干净短语
    target: str = ""  # 需要填空的词

    """Anki 字段字典"""
    model_name: str = "单词填空"  # 默认模型名（可按需修改）
    question_key: str = "文字"          # 通用字段名question
    answer_key: str = "中文"    # 通用字段名answer


# ---------- 工具函数 ----------
def parse_phrase_and_pick_target(phrase_raw: str) -> tuple[str, str]:
    """
    解析短语，支持 ^b 标注目标词；若无标注，则随机选择一个“含英文字母”的词作为目标。
    仅保留空格分词中的英文单词做随机候选。
    """
    tokens = [t for t in phrase_raw.strip().split() if t]
    marked_idx = None
    clean_tokens = []
    for i, tok in enumerate(tokens):
        if tok.startswith("^b") and len(tok) > 2:
            marked_idx = i
            clean_tokens.append(tok[2:])
        else:
            clean_tokens.append(tok)

    if not clean_tokens:
        raise ValueError(f"短语为空：{phrase_raw!r}")

    if marked_idx is None:
        candidates = [i for i, t in enumerate(clean_tokens) if re.search(r"[A-Za-z]", t)]
        if not candidates:
            # 若没有英文词，仍选第一个
            target_idx = 0
        else:
            target_idx = random.choice(candidates)
    else:
        target_idx = marked_idx

    clean_phrase = " ".join(clean_tokens).strip()
    target = clean_tokens[target_idx]
    if " " not in clean_phrase:
        raise ValueError(f"PhraseProcessor 仅处理短语（需至少两个词）：{clean_phrase!r}")

    return clean_phrase, target

def _mask_token(token: str) -> str:
    """
    使用 Anki Cloze 语法把一个词变为填空：
      - 仅对字母数字主体执行遮罩，其后的标点原样保留
      - 长度 <= 4：整个词用 {{cN::word}}
      - 长度 > 4 ：保留前 2 个字母，其余用 {{cN::rest}}
    :param token: 原始匹配到的词（可能带后缀标点）
    :param cidx: 题号索引 N（默认 1 → {{c1::...}}）
    """
    m = re.match(r"[A-Za-z0-9]+", token)
    if not m:
        # 非字母数字开头（几乎不会作为目标词），原样返回
        return token

    word = m.group(0)
    suffix = token[len(word):]
    n = len(word)

    if n <= 4:
        masked = f"{{{{c1::{word}}}}}"                 # {{c1::word}}
    else:
        masked = f"{word[:2]}{{{{c1::{word[2:]}}}}}"   # ma{{c1::chine}}

    return masked + suffix


def _replace_target_once(text: str, target: str) -> Tuple[str, bool]:
    """
    在 text 中寻找 target（忽略大小写），仅替换第一次出现的位置为遮罩形式。
    优先整词匹配；若失败，再尝试带 1~3 位字母后缀（如复数/时态）。
    """
    p1 = re.compile(rf"\b({re.escape(target)})\b", re.IGNORECASE)
    p2 = re.compile(rf"\b({re.escape(target)})([A-Za-z]{{1,3}})?\b", re.IGNORECASE)

    def _sub(m):  # m.group(0) 可能包含后缀
        return _mask_token(m.group(0))

    if p1.search(text):
        return p1.sub(_sub, text, count=1), True
    if p2.search(text):
        return p2.sub(_sub, text, count=1), True
    return text, False


def _split_first_sentence(paragraph: str) -> Tuple[str, str]:
    """
    简单切分段落的首句与其余文本。
    依据英文句号/问号/感叹号分割（保留分隔符到首句尾部）。
    """
    m = re.search(r"([.?!])\s+", paragraph)
    if not m:
        return paragraph.strip(), ""
    end = m.end()  # 切点在空格后一位
    first = paragraph[:m.end(1)].strip()
    rest = paragraph[m.end(1):].strip()
    return first, rest


# ---------- 短语处理器 ----------
class PhraseProcessor:
    """
    短语处理器：
      - 输入：字符串（可含 ^b 前缀标注目标词）
      - 通过 LLMService 生成“两句合并成段落”的英文文本（第一句含短语，第二句为提示）
      - 仅对第一句的目标词做填空处理；第二句保持原文，作为提示/上下文
      - 输出字段字典（默认使用“精确字段名”）：{ 'Question': 段落(首句已填空), 'Answer': 原段落 + 目标词 }
        若 use_generic_keys=True，则返回 {'question':..., 'answer':..., 'term':...}
    """

    def __init__(
        self,
        llm: LLMService,
        *,
        use_generic_keys: bool = False,    # 默认返回精确字段名
    ) -> None:
        self.llm = llm
        self.use_generic_keys = use_generic_keys

    # --- 对外主接口 ---
    def produce_fields(self, item: PhraseItem) -> Dict[str, str]:
        """
        输入：PhraseItem（phrase 为干净短语，target 为填空词）
        输出：用于 Anki 的字段字典（题面为“首句填空 + 第二句提示”）
        """
        item.phrase, item.target = parse_phrase_and_pick_target(item.phrase_raw)
        phrase = item.phrase
        target = item.target

        # 让 LLM 生成“两句合并为段落”的文本
        paragraph = (self.llm.make_phrase_paragraph(phrase) or "").strip()
        if not paragraph:
            # 兜底
            paragraph = f"I often use {phrase} when discussing this topic. It helps clarify our goals."

        # 仅在第一句进行填空处理
        s1, s_rest = _split_first_sentence(paragraph)
        q1, ok = _replace_target_once(s1, target)
        if not ok:
            # 找不到目标词：尝试在整个段落替换一次
            q_paragraph, ok2 = _replace_target_once(paragraph, target)
            if ok2:
                question = q_paragraph
            else:
                # 最后兜底：自造一句含短语的首句并替换
                fallback = f"We relied on {phrase} to solve the problem."
                q1, _ = _replace_target_once(fallback, target)
                question = f"{q1} {s_rest}".strip()
        else:
            question = f"{q1} {s_rest}".strip() if s_rest else q1

        # 答案：将原段落翻译为中文
        answer = self.llm.translate_to_zh(paragraph)


        if self.use_generic_keys:
            return {"question": question, "answer": answer}
        else:
            return {item.question_key: question, item.answer_key: answer}


# ----------------- 类内测试程序 -----------------
if __name__ == "__main__":
    """
    运行前提：
      1) 你的 LLMServer.py 已实现 LLMService make_phrase_paragraph(phrase) 方法
      2) 若 LLMService 依赖 DEEPSEEK_API_KEY，请确保环境变量已设置
    """
    llm = LLMService()

    # 默认：返回精确字段（Question/Answer/Expression）
    pp = PhraseProcessor(llm)
    # 含 ^b 标注（指定填空词）
    item = PhraseItem(phrase_raw="^bmachine learning")
    fields1 = pp.produce_fields(item)
    print("精确字段 (标注) ->", fields1)

    # 不含标注：在短语中随机选择一个词作为填空词
    item = PhraseItem(phrase_raw="renewable energy")
    fields2 = pp.produce_fields(item)
    print("精确字段 (随机) ->", fields2)

    # 若需要返回通用键，便于 FieldMapper 自动映射
    item = PhraseItem(phrase_raw="deep neural network")
    pp_generic = PhraseProcessor(llm, use_generic_keys=True)
    fields3 = pp_generic.produce_fields(item)
    print("通用键 ->", fields3)

    # （可选）写入 Anki（取消注释需要你已有的 AnkiService）
    from anki_service import AnkiService
    anki = AnkiService(deck="oule", model=item.model_name, default_tags=["oulu",item.model_name,"auto"])
    note_id = anki.add_note(fields1)
    print("写入 Anki 的 noteId:", note_id)
