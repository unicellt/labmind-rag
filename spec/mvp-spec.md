# 实验室知识库 MVP Spec

版本: v1.0

## 1. 背景

目标是在 `lab-rag-qa/` 项目中，基于两份实验室 PDF 文档构建一个可检索、可问答、可溯源、可测试的实验室知识库。

参考项目为 `RAG-cy/`，但本项目优先保证工程可维护性、测试沉淀和回答可信度。

## 2. 第一阶段范围

第一阶段只覆盖以下两份 PDF：

- `lab-rag-qa/data/examples/江涛组相关实验SOP及附录---2020.5.19 (2).pdf`
- `lab-rag-qa/data/examples/gao lab protocol.pdf`

暂不把 `.docx` 作为事实来源，避免与 PDF 产生重复内容或解析差异。`.docx` 可作为后续解析质量对照材料。

第一阶段不包含：

- 向量检索和 FAISS 主链路。
- MinerU 强依赖解析链路。
- 自动设计新实验方案。
- 文档外知识扩展回答。
- 完整生产级 UI 改造。

## 3. MVP 目标

MVP 必须支持：

- 本地解析两份 PDF。
- 将文档结构化为带章节、页码和 chunk 标识的片段。
- 构建可重复生成的检索资产。
- 对用户问题进行 BM25/关键词检索。
- 对候选 chunk 进行本地规则重排。
- 基于检索结果生成中文答案。
- 无 API key 时提供本地抽取式兜底答案。
- 有 DashScope/Qwen 配置时可选调用 LLM 生成答案。
- 每个答案返回可核查来源。
- 对文档未覆盖的问题给出保守回答。
- 积累可重复运行的测试和评测用例。

## 4. 用户问题类型

优先支持：

- 实验步骤查询，例如某实验的操作流程。
- 试剂、材料、设备查询。
- 条件参数查询，例如时间、温度、浓度、转速、体积。
- 注意事项和安全风险查询。
- 中英文混合问题。
- 针对某一文档的限定查询。

暂不优先支持：

- 跨多篇文献的科研推理。
- 无文档依据的实验设计建议。
- 替代正式 SOP 的安全审批。
- 对文档外知识进行无来源扩展。

## 5. 数据流

第一阶段数据流固定为：

1. 读取配置中的两份 PDF。
2. 本地解析 PDF，按页保留原文。
3. 清洗空白字符和明显解析噪声。
4. 识别章节标题，识别不到时允许为空。
5. 以页为基础切分 chunk，避免 chunk 跨页后丢失来源。
6. 写出 chunk JSONL。
7. 基于 chunk 构建 BM25/关键词检索资产。
8. 检索候选 chunk。
9. 本地规则重排。
10. 组装上下文并生成答案。
11. 返回答案和来源列表。

## 6. 配置要求

配置中必须明确：

- `source_docs`: 第一阶段事实来源 PDF 列表。
- `parsed_docs`: 解析结果输出目录。
- `chunks`: chunk JSONL 输出路径。
- `index_store`: 检索索引输出目录。
- `chunk_size`: chunk 目标长度。
- `chunk_overlap`: chunk 重叠长度。
- `top_k`: 默认返回来源数量。
- `llm.provider`: 默认 `dashscope`。
- `llm.model`: 默认 `qwen-turbo-latest` 或当前项目可用 Qwen 模型。

路径应相对 `lab-rag-qa/` 项目根目录解析。

## 7. 数据结构

### DocumentChunk

每个 chunk 至少包含：

- `chunk_id`: 稳定 chunk ID。
- `doc_name`: 文档文件名。
- `page_no`: 页码，必须保留。
- `section_title`: 章节标题，可为空。
- `text`: chunk 文本。
- `metadata`: 解析和来源补充信息。

### RetrievedChunk

检索结果在 `DocumentChunk` 基础上增加：

- `score`: 检索或重排后的分数。

### AnswerResult

问答结果至少包含：

- `answer`: 中文答案或抽取式兜底答案。
- `sources`: 来源数组。

每条 source 至少包含：

- `doc_name`
- `page_no`
- `section_title`
- `chunk_id`
- `score`
- `text`

## 8. 对外接口

### CLI

第一阶段固定支持：

```bash
python main.py ingest
python main.py search "问题"
python main.py ask "问题"
```

CLI 行为：

- `ingest`: 解析两份 PDF，生成 chunk 和索引资产。
- `search`: 返回相关来源片段。
- `ask`: 返回答案和来源列表。

### HTTP API

第一阶段固定支持：

- `GET /api/docs`
- `POST /api/search`
- `POST /api/answer`

`POST /api/search` 与 `POST /api/answer` 请求体：

```json
{"question":"PCR 反应体系如何配置？","top_k":5,"doc_name":null,"rerank":true}
```

`/api/answer` 响应体：

```json
{"answer":"...","sources":[{"doc_name":"gao lab protocol.pdf","page_no":1,"section_title":"...","chunk_id":"...","score":0.95,"text":"..."}]}
```

## 9. 检索与重排规范

检索第一阶段采用本地可复现路线：

- 初筛使用 BM25 或当前项目关键词检索增强版本。
- 支持 `doc_name` 过滤。
- 候选数量应大于最终 `top_k`，用于重排。
- 重排使用本地规则，不依赖 LLM。

重排加权信号包括：

- 命中完整查询词或关键英文术语。
- 包含实验参数单位，例如 `uL`、`mL`、`min`、`h`、`rpm`、`g`、`mg`、`ng`、`%`。
- 包含步骤词，例如“步骤”“操作”“加入”“混匀”“孵育”“离心”。
- 包含试剂词，例如“buffer”“primer”“enzyme”“抗体”“培养基”。
- 包含安全词，例如“注意”“危险”“PPE”“废弃物”。

## 10. 回答规范

回答默认中文。

回答必须遵守：

- 优先基于检索到的文档片段。
- 实验参数、剂量、温度、时间、浓度等保持原文一致。
- 能引用文档时必须提供来源。
- 多个来源冲突时说明冲突，并分别列出来源。
- 未找到足够依据时明确说明“当前文档中未找到足够依据”。
- 不把模型常识伪装成文档事实。

无 API key 时：

- 使用本地抽取式答案。
- 答案应摘要 top sources 中的关键句。
- 仍必须返回来源列表。

有 DashScope/Qwen 配置时：

- 可调用 LLM 生成更自然的答案。
- prompt 必须要求只基于给定上下文回答。
- LLM 输出不得省略来源。

## 11. 验收标准

MVP 可验收条件：

- `python main.py ingest` 能处理两份 PDF 并生成 chunk 与索引资产。
- chunk 中每条记录都有 `doc_name`、`page_no`、`chunk_id`、`text`。
- `python main.py search "问题"` 能返回带页码和章节信息的来源。
- `python main.py ask "问题"` 能返回中文答案和来源。
- HTTP API 三个接口可用，并返回稳定 JSON。
- 10 条检索评测样例可离线运行。
- 10 条问答冒烟样例可离线运行抽取式答案评测。
- 文档外问题能保守回答，不产生确定性幻觉。

