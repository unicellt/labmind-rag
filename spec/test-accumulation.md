# 测试用例积累规范

版本: v1.0

## 1. 原则

项目的每个产出都必须留下可复用测试资产。测试资产是 Spec 的一部分，不是实现后的补丁。

第一阶段测试目标是保证核心链路可离线、可重复、可回归：

- 两份 PDF 能被解析。
- chunk 保留章节、页码和来源。
- 检索能命中预期片段。
- 问答能基于来源给出保守答案。
- 无 API key 时核心测试仍可运行。

## 2. 测试分层

### 单元测试

覆盖：

- 配置加载。
- schema 字段完整性。
- PDF 页码保留。
- 章节标题识别。
- chunk 切分边界。
- 来源格式化。
- 检索 tokenization。
- 重排规则加权。

### 集成测试

覆盖：

- 从两份 PDF 解析到 chunk JSONL。
- 从 chunk JSONL 构建检索资产。
- 按问题检索返回来源。
- `doc_name` 过滤。
- 空问题、无命中、文档外问题处理。

### RAG 检索评测

验证问题能检索到预期文档片段。

每条检索测试至少包含：

- `id`
- `query`
- `expected_doc`
- `expected_terms`
- `max_rank`
- `notes`

### RAG 问答评测

验证最终回答是否包含关键答案要点，并且不包含明显幻觉。

每条问答测试至少包含：

- `id`
- `question`
- `expected_points`
- `expected_sources`
- `forbidden`
- `notes`

## 3. 建议目录结构

后续实现应采用以下结构：

```text
lab-rag-qa/
  tests/
    unit/
    integration/
    fixtures/
    eval_cases/
      retrieval_smoke.jsonl
      qa_smoke.jsonl
```

其中：

- `unit/`: 单元测试。
- `integration/`: 集成测试。
- `fixtures/`: 小型测试文档、解析结果或 chunk 样例。
- `eval_cases/`: RAG 问答和检索评测样例。

## 4. 10 问冒烟集要求

第一阶段必须建立 10 条黄金问题。

覆盖比例建议：

- 2 条实验步骤问题。
- 2 条实验参数问题。
- 2 条试剂/材料问题。
- 1 条仪器/设备问题。
- 1 条安全/注意事项问题。
- 1 条限定某文档的问题。
- 1 条文档外问题。

黄金问题必须人工确认答案要点。若暂时无法确认，应在 `notes` 中标记 `needs_manual_review`，不得作为强断言测试。

## 5. 检索评测样例格式

检索评测样例使用 JSONL。

示例：

```json
{"id":"ret-001","query":"PCR 退火温度","expected_doc":"gao lab protocol.pdf","expected_terms":["PCR","退火","温度"],"max_rank":5,"notes":""}
```

通过标准：

- `expected_doc` 出现在前 `max_rank` 个结果中。
- 返回片段至少命中一个 `expected_terms`。
- source 中必须包含 `doc_name`、`page_no`、`chunk_id`。

## 6. 问答评测样例格式

问答评测样例使用 JSONL。

示例：

```json
{"id":"qa-001","question":"PCR 反应体系中需要哪些组分？","expected_points":["模板","引物","聚合酶"],"expected_sources":["gao lab protocol.pdf"],"forbidden":["当前文档未提及但模型编造的试剂"],"notes":""}
```

通过标准：

- 答案包含至少一个 `expected_points`。
- sources 中包含至少一个 `expected_sources`。
- 答案不包含 `forbidden` 中的内容。
- 文档外问题必须包含无法确认或未找到依据的表达。

## 7. 离线与在线测试

默认测试必须离线可运行：

- 不要求 DashScope API key。
- 不要求 MinerU API key。
- 不要求网络。
- 使用本地 PDF、本地 chunk、本地检索和抽取式答案。

在线测试单独标记：

- DashScope/Qwen 生成测试。
- SiliconFlow/OpenAI 兼容免费模型生成测试。
- MinerU 解析质量对照测试。
- 后续向量检索测试。

在线测试不得阻塞默认 CI 或本地核心回归。

## 8. 每次交付要求

每次完成一个功能或文档产出时，需要说明：

- 新增或更新了哪些测试。
- 测试覆盖了哪些行为。
- 是否运行成功。
- 是否有未覆盖风险。
- 是否需要人工确认黄金答案。
