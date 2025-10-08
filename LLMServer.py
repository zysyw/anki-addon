# -*- coding: utf-8 -*-
from __future__ import annotations
import os
import time
import requests
from typing import List, Dict, Tuple, Optional

class LLMService:
    """
    DeepSeek Chat Completions 的轻量封装。
    提供三类能力：
      1) 单词例句（<=16词）
      2) 短语两句：第一句包含该短语；第二句与第一句相关联、起提示作用
      3) 英文句子 -> 中文翻译
    """
    def __init__(
        self,
        api_key: Optional[str] = None,
        url: str = "https://api.deepseek.com/chat/completions",
        model: str = "deepseek-chat",
        timeout: int = 20,
        retries: int = 2,
        backoff: float = 1.6,
        temperature: float = 0.7,
        top_p: float = 0.9,
    ) -> None:
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        if not self.api_key:
            raise RuntimeError("缺少 DEEPSEEK_API_KEY 环境变量或未传入 api_key。")
        self.url = url
        self.model = model
        self.timeout = timeout
        self.retries = retries
        self.backoff = backoff
        self.temperature = temperature
        self.top_p = top_p

    # --------- Public APIs ---------
    def make_word_sentence(self, word: str) -> str:
        """
        生成一个自然、常见的英文例句（<=16词），包含指定单词。
        只返回句子本身，不加引号/序号/解释。
        """
        prompt = (
            "You are an English writing tutor.\n"
            f"Write ONE natural English sentence (≤25 words) that uses the word '{word}' in a typical context.\n"
            "Return ONLY the sentence. No quotes, labels, or extra text."
        )
        return self._one_line_chat(prompt)

    def make_phrase_paragraph(self, phrase: str) -> str:
        """
        生成一段自然英文文本（包含两句话）：
        - 第一句：必须包含该短语（≤20词）
        - 第二句：与第一句语义相关、提供自然线索或逻辑衔接（≤22词）
        返回：合并后的英文段落字符串。
        """
        prompt = (
            "You are an English writing tutor.\n"
            f"Write TWO related English sentences about a real-life scenario using the phrase: \"{phrase}\".\n"
            "- The first sentence must include the phrase exactly once and be ≤20 words.\n"
            "- The second sentence must be contextually related to the first, providing a natural clue or logical link (≤22 words).\n"
            "- Do NOT use any leading words such as 'Hint:', 'Note:', or numbering.\n"
            "- Return ONLY two sentences, each on its own line, without quotes or explanations."
        )
        text = self._one_block_chat(prompt)

        # 拆分成两句
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if len(lines) >= 2:
            s1, s2 = lines[0], lines[1]
        else:
            # 兜底逻辑
            if "." in text:
                parts = [p.strip() for p in text.split(".") if p.strip()]
                s1 = parts[0]
                s2 = parts[1] if len(parts) > 1 else f"This relates to '{phrase}' in a practical situation."
            else:
                s1 = f"I often use {phrase} when planning our work."
                s2 = "It helps organize tasks and set priorities for the team."

        # 清理句首的“Hint:”等引导词
        def strip_hint(s: str) -> str:
            s = s.lstrip()
            for pre in ["Hint:", "hint:", "Hint -", "hint -"]:
                if s.startswith(pre):
                    return s[len(pre):].lstrip()
            return s

        s1, s2 = strip_hint(s1), strip_hint(s2)

        # 合并成一段话
        paragraph = f"{s1} {s2}"
        return self._clean_line(paragraph)


    def translate_to_zh(self, text: str) -> str:
        """
        将英文句子翻译为简洁自然的中文。
        只返回翻译，不返回原文、不加引号。
        """
        prompt = (
            "You are a professional translator.\n"
            "Translate the following English sentence into concise, natural Simplified Chinese.\n"
            "Return ONLY the translation, no quotes or extra text.\n"
            f"Text: {text}"
        )
        return self._one_line_chat(prompt)

    # --------- Low-level Chat wrapper with retries ---------
    def _chat(self, messages: List[Dict[str, str]], max_tokens: int = 128) -> str:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "max_tokens": max_tokens,
        }

        attempt = 0
        last_err = None
        while attempt <= self.retries:
            try:
                r = requests.post(self.url, json=body, headers=headers, timeout=self.timeout)
                r.raise_for_status()
                data = r.json()
                text = data["choices"][0]["message"]["content"]
                return self._clean_block(text)
            except requests.RequestException as e:
                last_err = e
                if attempt == self.retries:
                    break
                time.sleep(self.backoff ** attempt)
                attempt += 1
            except Exception as e:
                raise RuntimeError(f"DeepSeek 响应解析失败: {e}") from e
        raise RuntimeError(f"DeepSeek 请求失败: {last_err}")

    def _one_line_chat(self, user_prompt: str) -> str:
        text = self._chat(
            messages=[
                {"role": "system", "content": "Be concise. Follow instructions strictly."},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=96,
        )
        # 仅取首行，清理可能的引号
        line = text.splitlines()[0] if text else ""
        return self._clean_line(line)

    def _one_block_chat(self, user_prompt: str) -> str:
        return self._chat(
            messages=[
                {"role": "system", "content": "Be concise. Follow instructions strictly."},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=160,
        )

    # --------- text cleaners ---------
    @staticmethod
    def _clean_block(s: str) -> str:
        return s.strip().strip('"').strip("'").replace("\u3000", " ").replace("\r", "").strip()

    @staticmethod
    def _clean_line(s: str) -> str:
        return LLMService._clean_block(s.replace("\n", " "))


# ======================= 测试程序 =======================
if __name__ == "__main__":
    """
    运行前请确保：
      1) pip install requests
      2) 已设置环境变量 DEEPSEEK_API_KEY
    """
    svc = LLMService()

    # 1) 单词例句
    word = "metabolism"
    s_word = svc.make_word_sentence(word)
    print("【单词例句】", s_word)

    # 2) 短语两句（含短语 + 关联提示）
    phrase = "show up"
    s_paragraph = svc.make_phrase_paragraph(phrase)
    print("【短语段落】", s_paragraph)

    # 3) 翻译
    en = "The project aims to reduce carbon emissions through smart energy management."
    zh = svc.translate_to_zh(en)
    print("【中文翻译】", zh)
