# -*- coding: utf-8 -*-
from __future__ import annotations
import json
import re
import os
from dotenv import load_dotenv
from google import genai

load_dotenv()


class GeminiService:
    """Google Gemini 封装，提供单词例句和短语段落生成。"""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY")
        if not self.api_key:
            raise RuntimeError("缺少 GOOGLE_API_KEY")
        self.model = model or os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")
        self._client = genai.Client(api_key=self.api_key)

    def _ask(self, prompt: str) -> str:
        resp = self._client.models.generate_content(model=self.model, contents=prompt)
        return resp.text.strip().strip('"').strip("'")

    def _ask_raw(self, prompt: str) -> str:
        resp = self._client.models.generate_content(model=self.model, contents=prompt)
        return resp.text.strip()

    def make_word_sentence(self, word: str) -> str:
        """生成包含该单词的自然英文例句（≤25词）。"""
        prompt = (
            f"Write ONE natural English sentence (≤25 words) using '{word}' "
            "in a typical everyday context. Return ONLY the sentence."
        )
        return self._ask(prompt)

    def make_word_definitions(self, word: str) -> str:
        """
        生成单词的多义项中文释义 HTML（最多5条）。
        每条包含词性、中文释义、出版物例句及中文翻译。
        返回可直接填入 Anki 字段的 HTML 片段。
        """
        prompt = (
            f'For the English word "{word}", list up to 5 of its most important senses.\n'
            "For each sense provide:\n"
            '  "pos"        : part of speech (e.g. noun, verb, adjective, adverb)\n'
            '  "zh"         : concise Chinese definition (10-30 characters)\n'
            '  "example"    : one authentic example sentence from a published book or '
            "magazine (append source in em-dash format, e.g. — George Orwell, 1984)\n"
            '  "example_zh" : Chinese translation of that sentence\n\n'
            "Return ONLY a valid JSON array, no markdown fences, no extra text.\n"
            "Example format:\n"
            '[\n'
            '  {"pos":"noun","zh":"花招；骗局","example":"It was an old trick — '
            'Arthur Conan Doyle, The Adventures of Sherlock Holmes","example_zh":'
            '"这是个老把戏。"}\n'
            ']'
        )
        raw = self._ask_raw(prompt)
        # 从返回文本中提取 JSON 数组
        m = re.search(r'\[.*\]', raw, re.DOTALL)
        if not m:
            return ""
        try:
            senses = json.loads(m.group())
        except json.JSONDecodeError:
            return ""

        lines = []
        for i, s in enumerate(senses, 1):
            pos = s.get("pos", "")
            zh = s.get("zh", "")
            example = s.get("example", "")
            example_zh = s.get("example_zh", "")
            pos_tag = f"[{pos}] " if pos else ""
            lines.append(f'<div class="dd-sense"><b>{i}.</b> {pos_tag}{zh}</div>')
            if example:
                lines.append(f'<div class="dd-exa">{example}</div>')
            if example_zh:
                lines.append(f'<div class="dd-zh">{example_zh}</div>')
        return "\n".join(lines)

    def make_phrase_cloze(self, phrase: str) -> dict:
        """
        为短语生成 Anki 填空题卡片内容。
        返回 {"cloze": "...", "zh": "..."}
          cloze: 含 {{c1::word}} 标记的英文句，只挖去最容易搞混的那个词
          zh:    该句的中文翻译
        """
        prompt = (
            f'The English phrase is: "{phrase}"\n\n'
            "Task: Write ONE natural English sentence (≤22 words) that uses this phrase "
            "in a context that strongly hints at its meaning.\n\n"
            "Then identify the single word in the phrase most likely to be confused with "
            "an alternative (e.g. a different particle, a near-synonym). "
            "Wrap ONLY that word with Anki cloze syntax {{c1::word}} — keep everything "
            "else visible, including the rest of the phrase.\n\n"
            "Also provide a Chinese translation of the full sentence.\n\n"
            "Return ONLY valid JSON (no markdown), exactly:\n"
            '{"cloze": "<sentence with {{c1::word}}>", "zh": "<Chinese translation>"}\n\n'
            "Examples:\n"
            '- phrase "show up" → {"cloze": "She showed {{c1::up}} an hour late without any excuse.", '
            '"zh": "她毫无理由地迟到了一个小时。"}\n'
            '- phrase "get over" → {"cloze": "It took him months to get {{c1::over}} the loss.", '
            '"zh": "他花了好几个月才从失去中走出来。"}\n'
            '- phrase "stay fit" → {"cloze": "He jogs every morning to stay {{c1::fit}}.", '
            '"zh": "他每天早晨慢跑以保持健康。"}'
        )
        raw = self._ask_raw(prompt)
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        if not m:
            return {"cloze": "", "zh": ""}
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            return {"cloze": "", "zh": ""}

    def make_phrase_paragraph(self, phrase: str) -> str:
        """生成两句关联英文文本：第一句含短语，第二句作提示。"""
        prompt = (
            f'Write TWO related English sentences using the phrase "{phrase}".\n'
            "- Sentence 1: must contain the phrase exactly once, ≤20 words.\n"
            "- Sentence 2: contextually related, ≤22 words.\n"
            "Return ONLY the two sentences, each on its own line."
        )
        return self._ask(prompt)


# ── 测试 ──────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    svc = GeminiService()
    print("模型:", svc.model)
    print("单词例句:", svc.make_word_sentence("eloquent"))
    print("短语段落:", svc.make_phrase_paragraph("show up"))
