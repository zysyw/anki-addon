# Coordinator 调用流程概览

```text
Coordinator.run(s)
  -> Splitter.split(s) -> [items]
  -> for each:
       ItemFactory.from_text(item) -> WordItem / PhraseItem
       processor = ProcessorFactory.for(item)
       content = processor.produce_content(item, LLMService)  # 例句/填空Q&A
       note = NoteBuilder(model="FastWQ").build(content)
       AnkiService.add_note(deck="oulu", note)
