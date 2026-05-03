# Anki 自动制卡工具

自动为英语单词和短语生成 Anki 闪卡，整合本地词典、在线词典与 AI 大模型。

## 功能

| 输入类型 | 判断方式 | Anki 模板 | 内容来源 |
|---------|---------|-----------|---------|
| 单词（如 `eloquent`） | 无空格 | 新单词模板 | LDOCE6++ 音标/发音 + 译典通多义项释义 + Gemini 例句 |
| 短语（如 `show up`） | 含空格 | 填空题 | Gemini 生成填空句（挖最易混淆的词）+ 中文注释 |

## 文件结构

```
main.py           # 主程序，交互式输入
anki_service.py   # Anki-Connect 封装（添加卡片、存储音频、字段映射）
dict_service.py   # LDOCE6++ MDX/MDD 封装（音标、发音 MP3、多义项解析）
dreye_service.py  # 译典通在线词典（多义项中文释义，繁→简转换）
gemini_service.py # Google Gemini API（生成例句、填空句）
.env              # 配置文件（不提交到 git）
_archive/         # 旧版代码（FastWQ + DeepSeek 方案）
```

## 依赖安装

```bash
pip install mdict-utils requests beautifulsoup4 opencc-python-reimplemented google-genai python-dotenv
```

## 配置

编辑 `.env`：

```ini
# Google AI Studio API Key
GOOGLE_API_KEY=your_key_here
# 可用模型: gemini-2.5-flash（主力）/ gemini-3-flash-preview（备用，20次/天）
GEMINI_MODEL=gemini-2.5-flash

# 词典路径（LDOCE6++ En-Cn MDX/MDD 文件）
LDOCE6_MDX=C:/path/to/LDOCE6++ En-Cn V2-19.mdx
LDOCE6_MDD=C:/path/to/LDOCE6++ En-Cn V2-19.mdd

# Anki
ANKI_URL=http://127.0.0.1:8765
# 测试牌组: 新单词测试
ANKI_DECK=Everyday English
ANKI_MODEL=新单词模板
```

## 前置条件

- Anki 已安装并运行，且安装了 [Anki-Connect](https://ankiweb.net/shared/info/2055492159) 插件
- Anki 中已存在 `新单词模板`（含字段：单词、词性、音标、发音、中文释义、例句、词典例句、词典释义）和 `填空题` 模板
- 持有 LDOCE6++ En-Cn 的 MDX/MDD 文件

## 使用

```bash
py main.py
```

```
请输入: audacious, show up, resilience，get over
```

- 用英文逗号 `,` 或中文逗号 `，` 分隔多项
- 留空回车退出

## 卡片效果

**单词卡（新单词模板）**
- 正面：单词 + 词性 + 音标 + 发音按钮 + AI 例句
- 背面：中文释义（大字）+ 译典通多义项（含例句）+ 词典例句（带音频）

**短语卡（填空题）**

使用 Anki 填空题模板，挖去短语中最易与其他短语混淆的词：

> She showed **[...]** an hour late without any excuse.

答题后显示答案 `up`，Note 行显示中文翻译。
