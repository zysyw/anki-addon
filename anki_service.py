# anki_service.py
from __future__ import annotations
import time
import requests
from typing import Dict, List, Iterable, Optional

class AnkiService:
    """
    Anki-Connect 轻量封装：
      - _ac(): 调用动作
      - ensure_deck(): 确保牌组存在
      - model_fields(): 缓存并返回模型字段
      - add_note(): 添加单条
      - add_notes(): 批量添加
    """
    def __init__(
        self,
        endpoint: str = "http://127.0.0.1:8765",
        deck: str = "oule",
        model: str = "newFastWQ",
        default_tags: Optional[List[str]] = None,
        retries: int = 2,
        backoff: float = 1.6,
        timeout: int = 12,
        duplicate_scope: str = "deck",   # "deck" | "collection"
        allow_duplicate: bool = False,
        fuzzy_field_match: bool = True,  # 允许字段名的模糊匹配（大小写/空格/下划线）
    ) -> None:
        self.endpoint = endpoint
        self.deck = deck
        self.model = model
        self.default_tags = default_tags or ["auto"]
        self.retries = retries
        self.backoff = backoff
        self.timeout = timeout
        self.duplicate_scope = duplicate_scope
        self.allow_duplicate = allow_duplicate
        self._model_fields_cache: Optional[List[str]] = None
        self._fuzzy = fuzzy_field_match

    # ---------- Core AC call ----------
    def _ac(self, action: str, **params):
        payload = {"action": action, "version": 6, "params": params}
        last_err = None
        for attempt in range(self.retries + 1):
            try:
                r = requests.post(self.endpoint, json=payload, timeout=self.timeout)
                r.raise_for_status()
                data = r.json()
                if data.get("error"):
                    raise RuntimeError(data["error"])
                return data["result"]
            except Exception as e:
                last_err = e
                if attempt >= self.retries:
                    raise RuntimeError(f"Anki-Connect '{action}' 失败: {e}") from e
                time.sleep(self.backoff ** attempt)

    # ---------- Deck / Model ----------
    def ensure_deck(self, deck_name: Optional[str] = None) -> None:
        deck_name = deck_name or self.deck
        decks = set(self._ac("deckNames"))
        if deck_name not in decks:
            self._ac("createDeck", deck=deck_name)

    def model_fields(self, model_name: Optional[str] = None) -> List[str]:
        model_name = model_name or self.model
        if self._model_fields_cache is None:
            self._model_fields_cache = self._ac("modelFieldNames", modelName=model_name)
        return self._model_fields_cache

    # ---------- Add Note(s) ----------
    def add_note(
        self,
        provided_fields: Dict,
        tags: Optional[List[str]] = None,
        deck_name: Optional[str] = None,
        model_name: Optional[str] = None,
        options: Optional[Dict] = None,
    ) -> int:
        deck_name = deck_name or self.deck
        model_name = model_name or self.model
        self.ensure_deck(deck_name)
        mf = self.model_fields(model_name)
        mapper = FieldMapper(mf, fuzzy=self._fuzzy)

        note = {
            "deckName": deck_name,
            "modelName": model_name,
            "fields": mapper.map(provided_fields),
            "tags": (tags or []) + self.default_tags,
            "options": {
                "allowDuplicate": self.allow_duplicate,
                "duplicateScope": self.duplicate_scope,
            },
        }
        if options:
            note["options"].update(options)

        return self._ac("addNote", note=note)

    def add_notes(
        self,
        items: Iterable[Dict],
        tags: Optional[List[str]] = None,
        deck_name: Optional[str] = None,
        model_name: Optional[str] = None,
        options: Optional[Dict] = None,
        sleep_between: float = 0.0,
    ) -> List[Optional[int]]:
        """
        批量添加：items 为一组 provided_fields 字典。
        返回每一条的 noteId（失败为 None）。
        """
        out: List[Optional[int]] = []
        for pf in items:
            try:
                nid = self.add_note(
                    provided_fields=pf,
                    tags=tags,
                    deck_name=deck_name,
                    model_name=model_name,
                    options=options,
                )
                out.append(nid)
            except Exception as e:
                print(f"❌ add_note 失败: {e}")
                out.append(None)
            if sleep_between > 0:
                time.sleep(sleep_between)
        return out


class FieldMapper:
    """
    字段映射规则：
      1) 精确同名字段优先（provided 中 key 与模型字段完全一致）
      2) 通用键自动映射到候选字段名（按顺序择一）
         - term         -> Word / Expression / Term / Front / 单词 / 词条
         - example      -> Example / Examples / Sentence / 例句 / 中文
         - question     -> Front / Question / 题面 / 句子填空 / 文字
         - answer       -> Back / Answer / 答案 / Definition
         - gloss        -> Definition / Meaning / Gloss / 释义 / 中文释义 / Back
         - phonetic     -> Phonetic / IPA / 音标
         - collocation  -> Collocation / Phrases / 搭配
         - paragraph    -> Passage / Paragraph / Context / 文段 / 上下文
      3) fuzzy=True 时，支持“大小写/空格/下划线”归一化后的弱匹配，
         例如 provided['Question'] 也能匹配到模型字段 'question' 或 'Question ' 等。
    """
    GENERIC_MAP = {
        "term":        ["Word", "Expression", "Term", "Front", "单词", "词条"],
        "example":     ["Example", "Examples", "Sentence", "例句", "中文"],
        "question":    ["Front", "Question", "题面", "句子填空", "文字"],
        "answer":      ["Back", "Answer", "答案", "Definition"],
        "gloss":       ["Definition", "Meaning", "Gloss", "释义", "中文释义", "Back"],
        "phonetic":    ["Phonetic", "IPA", "音标"],
        "collocation": ["Collocation", "Phrases", "搭配"],
        "paragraph":   ["Passage", "Paragraph", "Context", "上下文", "文段"],
        # 你也可以在此扩展更多通用键
    }

    def __init__(self, model_fields: List[str], fuzzy: bool = True) -> None:
        self.model_fields = model_fields
        self.fuzzy = fuzzy
        self._mf_set = set(model_fields)
        if fuzzy:
            self._norm_to_real = {self._norm(f): f for f in model_fields}

    # ---- public ----
    def map(self, provided: Dict) -> Dict:
        fields = {f: "" for f in self.model_fields}

        # 1) 精确同名字段优先写入
        for k, v in provided.items():
            if k in self._mf_set:
                fields[k] = v

        # 2) fuzzy：弱匹配 provided 的键到模型字段
        if self.fuzzy:
            for k, v in provided.items():
                if k in self._mf_set:
                    continue
                nk = self._norm(k)
                if nk in self._norm_to_real:
                    real = self._norm_to_real[nk]
                    if not fields.get(real):
                        fields[real] = v

        # 3) 通用键映射（仅在目标字段还空时生效）
        def fill(generic_key: str, candidates: List[str]):
            if generic_key not in provided:
                return
            val = provided[generic_key]
            for cand in candidates:
                # 先精确；再 fuzzy
                if cand in self._mf_set and not fields[cand]:
                    fields[cand] = val
                    return
                if self.fuzzy:
                    nc = self._norm(cand)
                    real = self._norm_to_real.get(nc)
                    if real and not fields[real]:
                        fields[real] = val
                        return

        for gk, cands in self.GENERIC_MAP.items():
            fill(gk, cands)

        return fields

    # ---- helpers ----
    @staticmethod
    def _norm(name: str) -> str:
        """归一化：小写 + 去空格/下划线。"""
        return "".join(ch for ch in name.lower() if ch not in {" ", "_"})
    
if __name__ == "__main__":
    '''#获取模型字段
    svc = AnkiService(model="单词填空")
    model_fields = svc.model_fields()
    print("模型字段:", model_fields)

    #测试add_note
    note = {
        "文字": "{{c1::Paris}} is the capital of France?",
        "中文": "法国的首都是巴黎."
    }
    svc.add_note(note)
    # 测试批量添加
    svc = AnkiService(model="单词填空")
    notes = [
        {
            "文字": "{{c1::Paris}} is the capital of France?",
            "中文": "法国的首都是巴黎."
        },
        {
            "文字": "{{c1::Berlin}} is the capital of Germany?",
            "中文": "德国的首都是柏林."
        }
    ]
    svc.add_notes(notes)'''
    #测试newfastwq模型的add_note
    svc = AnkiService(model="newFastWQ")
    '''note = {
        "单词": "Paris",
        "例句": "Paris is the capital of France."
    }
    svc.add_note(note)'''
    # 测试批量添加
    notes = [
        {
            "单词": "Berlin",
            "例句": "Berlin is the capital of Germany."
        },
        {
            "单词": "Tokyo",
            "例句": "Tokyo is the capital of Japan."
        }
    ]
    svc.add_notes(notes)