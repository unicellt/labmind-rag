# 实验室知识库整体实施路线图

版本: v1.0

## 1. 总体目标

第一阶段在 `lab-rag-qa/` 中实现一个基于两份 PDF 的实验室知识库。系统必须支持本地解析、结构化 chunk、BM25/关键词检索、本地规则重排、中文问答、来源引用和离线测试。

主交付面为 CLI 和 HTTP API。UI 作为跟随演示层，不作为第一阶段主验收对象。

## 2. 阶段一：文档与配置整理

### 实现内容

- 将默认知识库事实来源固定为两份 PDF：
  - `lab-rag-qa/data/examples/江涛组相关实验SOP及附录---2020.5.19 (2).pdf`
  - `lab-rag-qa/data/examples/gao lab protocol.pdf`
- 配置中明确 `source_docs`、`parsed_docs`、`chunks`、`index_store`。
- 路径统一按 `lab-rag-qa/` 项目根目录解析。
- 保留 MinerU 配置，但仅作为可选增强，不进入默认链路。

### 完成标准

- 配置加载后能获得两份 PDF 的绝对或项目相对路径。
- 默认 ingest 不再依赖 `data/raw_docs` 中的 `.docx`。

### 测试要求

- 单元测试覆盖配置加载。
- 测试确认 `source_docs` 正好包含两份 PDF。

## 3. 阶段二：解析与结构化

### 实现内容

- 使用本地 PDF 解析器读取两份 PDF。
- 按页提取文本，并保留 `page_no`。
- 清洗空白行、重复空格和明显解析噪声。
- 使用规则识别章节标题。
- 输出结构化中间结果，至少包含 `doc_name`、`page_no`、`section_title`、`text`。

### 完成标准

- 两份 PDF 均能解析出非空页面文本。
- 每页文本都能追踪到原始文档和页码。
- 章节识别失败不阻塞解析，但页码不得丢失。

### 测试要求

- 集成测试覆盖两份 PDF 解析。
- 单元测试覆盖章节识别规则。
- 回归测试覆盖空页或无文本页处理。

## 4. 阶段三：chunk 与索引

### 实现内容

- 以页为基础切分 chunk，避免跨页后丢失来源。
- 每个 chunk 包含 `chunk_id`、`doc_name`、`page_no`、`section_title`、`text`、`metadata`。
- chunk 写入 JSONL。
- 基于 chunk 构建本地 BM25/关键词检索资产。

### 完成标准

- chunk ID 稳定可复现。
- 每条 chunk 都有文档名、页码和文本。
- chunk JSONL 可被重新加载。

### 测试要求

- 单元测试覆盖 chunk 切分和 ID 生成。
- 集成测试覆盖 chunk JSONL 写入与读取。
- 测试确认 chunk 不丢失页码。

## 5. 阶段四：检索与重排

### 实现内容

- 初筛使用 BM25 或增强关键词检索。
- 支持 `top_k` 和 `doc_name` 过滤。
- 检索候选数量应大于最终返回数量。
- 使用本地规则重排候选 chunk。
- 重排规则优先提升包含实验参数、步骤词、试剂词、安全词和精确查询词的片段。

### 完成标准

- `/api/search` 和 `python main.py search` 都能返回稳定 sources。
- sources 包含 `doc_name`、`page_no`、`section_title`、`chunk_id`、`score`、`text`。
- 文档过滤只返回指定文档的来源。

### 测试要求

- 单元测试覆盖 tokenization 和重排加权。
- 集成测试覆盖普通检索、限定文档检索和无命中检索。
- 检索冒烟集至少包含 10 条 JSONL 样例。

## 6. 阶段五：回答生成

### 实现内容

- 默认中文回答。
- 无 API key 时使用本地抽取式兜底答案。
- 有 DashScope/Qwen 配置时可选调用 LLM。
- LLM prompt 必须约束只基于给定上下文回答。
- 两种生成模式都必须返回来源列表。
- 文档外问题必须保守回答。

### 完成标准

- `python main.py ask` 返回 `answer` 和 `sources`。
- `/api/answer` 返回稳定 JSON。
- 无 API key 场景可离线运行。

### 测试要求

- 单元测试覆盖抽取式答案。
- 集成测试覆盖文档外问题保守回答。
- 问答冒烟集至少包含 10 条 JSONL 样例。
- Qwen 相关测试标记为在线可选测试。

## 7. 阶段六：CLI + HTTP API

### 实现内容

CLI 固定支持：

```bash
python main.py ingest
python main.py search "问题"
python main.py ask "问题"
```

HTTP API 固定支持：

- `GET /api/docs`
- `POST /api/search`
- `POST /api/answer`

### 完成标准

- CLI 输出可读中文。
- HTTP API 返回 `application/json; charset=utf-8`。
- 错误请求返回明确错误信息。
- UI 可以继续作为 API 的轻量演示调用方。

### 测试要求

- 集成测试覆盖 CLI search/ask 的核心路径。
- API 测试覆盖三个接口的成功和错误场景。

## 8. 阶段七：测试与评测资产

### 实现内容

- 建立 `tests/unit/`、`tests/integration/`、`tests/fixtures/`、`tests/eval_cases/`。
- 建立 `retrieval_smoke.jsonl`。
- 建立 `qa_smoke.jsonl`。
- 默认测试不依赖网络或 API key。

### 完成标准

- 核心测试可一键运行。
- 10 条检索冒烟样例可离线验证。
- 10 条问答冒烟样例可离线验证。
- 测试结果能说明当前知识库的可用边界。

### 测试要求

- 每个后续功能 PR 或交付都必须更新对应测试。
- 未覆盖风险必须在交付说明中列出。

## 9. 后续增强方向

以下能力不进入第一阶段主线：

- MinerU 解析质量对照。
- DashScope embedding + FAISS 向量检索。
- BM25 + 向量混合检索。
- LLM rerank。
- 更完整的 Streamlit 或 Web UI。
- 更大规模黄金评测集。

这些能力需要单独 Spec 讨论后再进入实现。

## 10. 免费模型 API 接入决策

第一阶段生成器增加通用 OpenAI 兼容接口，首选 SiliconFlow 官方免费模型：

- provider：`openai_compatible`
- base URL：`https://api.siliconflow.cn/v1`
- model：`Qwen/Qwen3-8B`
- key 环境变量：`SILICONFLOW_API_KEY`

约束：

- 只使用用户本人从官方控制台创建的 Key，不使用共享、泄露或来路不明的 Key。
- Key 只保存在项目 `.env`，不得提交仓库。
- 无 Key、网络失败、免费额度耗尽或模型不可用时，自动回退本地抽取式答案。
- 保留 DashScope provider，允许通过配置切换，不与 SiliconFlow Key 混用。

测试要求：

- 离线单元测试模拟 OpenAI 兼容接口成功与失败响应。
- 默认测试不得发出真实网络请求。
- 真实免费模型调用作为可选在线冒烟测试，且不得打印 Key。
- `/api/answer` 返回 `generation` 状态，明确区分 `llm` 与 `extractive`，失败时只暴露非敏感错误类型和信息。
- 实验参数问答默认温度为 `0`；在线冒烟测试必须检查模型逐字保留关键数字和单位。
- HTML 的“搜索文档”固定按相关性得分降序展示前五名，每条结果显示排名与三位小数得分。
- HTML 所有用户可见文案必须为有效中文，不允许出现编码损坏产生的连续问号占位符。
- 文档下拉框过滤编码损坏的异常名称；本地服务禁用页面缓存，避免旧乱码页面继续显示。
