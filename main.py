# -*- coding: utf-8 -*-
"""
Anki 自动制卡工具
  - 单词（无空格）→ 新单词模板：LDOCE6++ 发音/音标 + 译典通释义 + Gemini 例句
  - 短语（含空格）→ 填空题模板：Gemini 生成填空句 + 中文注释
用逗号（中/英）分隔多个输入，留空退出。
"""
import sys
import os
import re
import time

sys.stdout.reconfigure(encoding="utf-8")
from dotenv import load_dotenv
load_dotenv()

from dict_service  import DictService
from dreye_service import DreyeService
from gemini_service import GeminiService
from anki_service  import AnkiService

# ── 初始化服务 ────────────────────────────────────────────
dict_svc  = DictService(os.getenv("LDOCE6_MDX"), os.getenv("LDOCE6_MDD"))
dreye_svc = DreyeService()
llm_svc   = GeminiService()

WORD_DECK   = os.getenv("ANKI_DECK",  "新单词测试")
WORD_MODEL  = os.getenv("ANKI_MODEL", "新单词模板")
PHRASE_DECK = os.getenv("ANKI_DECK",  "新单词测试")
PHRASE_MODEL = "填空题"

word_anki   = AnkiService(deck=WORD_DECK,   model=WORD_MODEL,
                          default_tags=[WORD_DECK, "word", "auto"])
phrase_anki = AnkiService(deck=PHRASE_DECK, model=PHRASE_MODEL,
                          default_tags=[PHRASE_DECK, "phrase", "auto"])


# ── 单词流水线 ────────────────────────────────────────────
def add_word(word: str) -> bool:
    print(f"  [单词] {word}")

    # 1) LDOCE6++ 查词
    entry = dict_svc.lookup(word)
    if entry:
        print(f"    词性: {entry.pos}  音标: {entry.phonetic}")
        print(f"    首条释义: {entry.definition_zh}")
    else:
        print("    词典: 未找到")

    # 2) 译典通多义项释义
    dreye = dreye_svc.lookup(word)

    # 3) Gemini 例句
    try:
        ai_sentence = llm_svc.make_word_sentence(word)
        print(f"    AI例句: {ai_sentence}")
    except Exception as e:
        ai_sentence = ""
        print(f"    ⚠ Gemini 例句失败: {e}")

    # 4) 音频
    pronunciation = ""
    dict_example_field = ""
    if entry:
        audio = dict_svc.get_audio(entry.audio_us_key)
        if audio:
            fname = f"ldoce_{word.replace(' ', '_')}_us.mp3"
            word_anki.store_media(fname, audio)
            pronunciation = f"[sound:{fname}]"
        if entry.example_en:
            exa_audio = dict_svc.get_audio(entry.example_audio_key)
            if exa_audio:
                exa_file = entry.example_audio_key.split("/")[-1]
                word_anki.store_media(exa_file, exa_audio)
                dict_example_field = (
                    f"{entry.example_en}　{entry.example_zh} [sound:{exa_file}]"
                )
            else:
                dict_example_field = f"{entry.example_en}　{entry.example_zh}"

    # 5) 写入 Anki
    fields = {
        "单词":    word,
        "词性":    entry.pos       if entry else "",
        "音标":    entry.phonetic  if entry else "",
        "发音":    pronunciation,
        "中文释义": entry.definition_zh if entry else "",
        "例句":    ai_sentence,
        "词典例句": dict_example_field,
        "词典释义": dreye.definition_html if dreye else "",
    }
    try:
        note_id = word_anki.add_note(fields)
        print(f"    ✓ 写入成功，noteId = {note_id}")
        return True
    except Exception as e:
        print(f"    ✗ 写入失败: {e}")
        return False


# ── 短语流水线 ────────────────────────────────────────────
def add_phrase(phrase: str) -> bool:
    print(f"  [短语] {phrase}")

    # Gemini 生成填空句
    try:
        result = llm_svc.make_phrase_cloze(phrase)
    except Exception as e:
        if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
            print(f"    ⚠ API 限额已用尽，跳过")
        else:
            print(f"    ✗ Gemini 失败: {e}")
        return False

    cloze = result.get("cloze", "")
    zh    = result.get("zh", "")

    if not cloze or "{{c1::" not in cloze:
        print(f"    ✗ 生成内容无效: {result}")
        return False

    print(f"    填空句: {cloze}")
    print(f"    中文:   {zh}")

    try:
        note_id = phrase_anki.add_note({"文字": cloze, "例句": zh})
        print(f"    ✓ 写入成功，noteId = {note_id}")
        return True
    except Exception as e:
        print(f"    ✗ 写入失败: {e}")
        return False


# ── 主循环 ────────────────────────────────────────────────
def parse_items(raw: str) -> list[str]:
    """用中/英文逗号分割，去除空白，过滤空串。"""
    return [s.strip() for s in re.split(r"[,，]", raw) if s.strip()]


def check_anki_connect() -> bool:
    """检查 Anki-Connect 是否可用，不可用时打印提示。"""
    try:
        word_anki._ac("version")
        return True
    except Exception:
        print()
        print("  ✗ 无法连接到 Anki-Connect")
        print()
        print("  请确认：")
        print("  1. Anki 软件已打开")
        print("  2. 已安装 Anki-Connect 插件（插件代码：2055492159）")
        print("     菜单 → 工具 → 插件 → 获取插件，输入上述代码安装后重启 Anki")
        print()
        return False


def main():
    print("=" * 55)
    print("  Anki 制卡工具  （单词/短语，逗号分隔，留空退出）")
    print("=" * 55)

    if not check_anki_connect():
        input("  按回车键退出...")
        return

    while True:
        try:
            raw = input("\n请输入: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n退出。")
            break

        if not raw:
            print("退出。")
            break

        items = parse_items(raw)
        if not items:
            continue

        # 确认牌组
        words   = [x for x in items if " " not in x]
        phrases = [x for x in items if " " in x]
        print()
        if words:
            print(f"  单词 → 牌组「{WORD_DECK}」：{', '.join(words)}")
        if phrases:
            print(f"  短语 → 牌组「{PHRASE_DECK}」：{', '.join(phrases)}")
        try:
            confirm = input("\n确认添加？(y/回车 确认，其他取消): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n退出。")
            break
        if confirm not in ("", "y", "yes"):
            print("已取消。")
            continue

        print(f"\n共 {len(items)} 项，开始处理...\n")
        for i, item in enumerate(items):
            is_phrase = " " in item
            if is_phrase:
                add_phrase(item)
            else:
                add_word(item)

            # 相邻 Gemini 调用之间稍作间隔，避免触发速率限制
            if i < len(items) - 1:
                time.sleep(2)

        print("\n本批处理完成 ✓")


if __name__ == "__main__":
    main()
