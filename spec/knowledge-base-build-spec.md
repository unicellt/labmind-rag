# 实验室 SOP 知识库构建 Spec

版本: v1.0

更新时间: 2026-06-09

## 1. 目标

基于两份实验室 PDF 构建一个可检索、可问答、可溯源、可测试的实验室 SOP 知识库。

第一阶段交付重点：

- 以 `lab-rag-qa/` 为主体工程。
- 仅使用已确认的两份 PDF 作为事实来源。
- 支持本地解析、本地检索、本地重排、可选大模型生成。
- 所有回答必须返回来源，来源至少包含文档名、页码、章节、chunk ID 和相关性分数。
- 默认中文回答，英文术语、参数和单位保持原文。

## 2. 数据源

当前知识库事实来源固定为：

- `lab-rag-qa/data/examples/江涛组相关实验SOP及附录---2020.5.19 (2).pdf`
- `lab-rag-qa/data/examples/gao lab protocol.pdf`

第一阶段不引入网页、外部数据库、用户上传文档或未审核资料。

## 3. 解析策略

默认解析器为本地 MinerU：

- MinerU 安装位置：`K:\MinerU`
- 可执行文件：`K:/MinerU/.venv/Scripts/mineru.exe`
- 输出目录：`K:/MinerU/output/lab-rag-qa`
- backend：`pipeline`

解析失败时回退 PyPDF2，保证系统离线可运行。

结构化页数据必须保留：

- `doc_name`
- `page_no`
- `section_title`
- `text`
- `metadata.parser`

## 4. Chunk 与索引

chunk 配置：

- `chunk_size`: 900
- `chunk_overlap`: 150
- 输出文件：`lab-rag-qa/data/chunks/chunks.jsonl`
- 索引清单：`lab-rag-qa/data/index_store/index_manifest.json`

chunk 设计要求：

- 以页码为主要来源边界。
- 避免跨页导致引用丢失。
- 每个 chunk 必须有稳定 `chunk_id`。
- 文档、页码、章节和解析器元数据必须随 chunk 保存。

## 5. 检索与重排

当前检索路线为关键词/IDF 检索加本地规则重排。

检索阶段：

- 使用中文、英文、数字、实验参数等词项进行候选召回。
- 支持 `doc_name` 文档过滤。
- 支持低置信度空结果，避免文档外问题硬答。

重排阶段优先提升：

- 精确查询词命中。
- 实验参数命中，如时间、温度、体积、浓度、转速、功率。
- 步骤词命中。
- 试剂、仪器和安全相关词命中。

HTML 搜索结果固定展示相关性分数最高的前五名，并显示三位小数得分。

## 6. 回答生成

默认生成配置：

- provider：`openai_compatible`
- base URL：`https://api.siliconflow.cn/v1`
- model：`Qwen/Qwen3-8B`
- temperature：`0.0`
- key 环境变量：`SILICONFLOW_API_KEY`

生成规则：

- 只基于检索上下文回答。
- 实验参数、数字、单位必须保持原文。
- 文档片段不足时明确说明未找到足够依据。
- 生成答案和抽取式答案都必须返回来源。
- 无 API Key、网络失败、额度失败或模型错误时自动回退本地抽取式答案。

API 返回 `generation` 状态：

- `mode`: `llm` 或 `extractive`
- `provider`
- `model`
- `error`: 仅在失败时返回非敏感错误信息

## 7. 对外接口

CLI：

```bash
python main.py ingest
python main.py search "ARTP诱变仪参数设置"
python main.py ask "ARTP诱变仪的电源功率是多少？"
```

HTTP API：

- `GET /api/docs`
- `POST /api/search`
- `POST /api/answer`
- `POST /api/upload`

`/api/search` 请求示例：

```json
{"question":"蛋白纯化","top_k":5,"doc_name":null,"rerank":true}
```

`/api/answer` 返回结构：

```json
{
  "answer": "回答文本",
  "sources": [
    {
      "doc_name": "gao lab protocol.pdf",
      "page_no": 7,
      "section_title": "二、丝状真菌ARTP 诱变",
      "chunk_id": "gao lab protocol-p007-01",
      "score": 2.09,
      "text": "来源片段"
    }
  ],
  "generation": {
    "mode": "llm",
    "provider": "openai_compatible",
    "model": "Qwen/Qwen3-8B"
  }
}
```

## 8. HTML 演示层

页面入口：

- `http://127.0.0.1:8765/index.html`
- `lab-rag-qa/打开实验室知识库.html`
- `lab-rag-qa/启动并打开实验室知识库.bat`

HTML 行为要求：

- 文档下拉框显示“全部文档”和两份有效 PDF。
- 支持上传 PDF，上传后保存到 `data/examples/` 并立即全量重建知识库。
- 同名 PDF 自动重命名并作为独立文档保留。
- 搜索文档固定展示前五名。
- 每条结果显示排名、相关性得分、文档名、页码、chunk ID、来源类型和片段。
- 不允许出现编码损坏产生的连续问号占位符。
- 服务端禁用页面缓存，避免旧页面残留。

## 9. 测试资产

默认测试命令：

```bash
python -m unittest discover -s tests -p "test_*.py"
```

当前测试覆盖：

- 配置加载。
- PDF 解析和 chunk 生成。
- MinerU 本地解析器。
- 关键词检索。
- 本地规则重排。
- 抽取式答案。
- OpenAI 兼容模型调用模拟。
- API 契约。
- HTML 搜索前五名契约。
- HTML 文案乱码回归。
- PDF 上传、同名重命名、动态来源发现和上传后检索。
- 启动入口文件契约。
- 10 条检索冒烟集。
- 10 条问答冒烟集。

在线模型调用不进入默认测试，避免依赖网络、额度和个人 API Key。

## 10. 当前验证状态

截至 2026-06-09：

- 两份 PDF 已由 MinerU 完整解析。
- 默认 ingest 生成 122 个结构化 chunk。
- SiliconFlow `Qwen/Qwen3-8B` 已完成端到端调用验证。
- ARTP 参数问题可正确返回 `120W`、`1mm`、`10L·min⁻¹`。
- 本地服务地址：`http://127.0.0.1:8765/index.html`
- 自动测试已累计到 31 条并通过。

## 11. 已知边界

- 当前检索仍是关键词/IDF 路线，不包含向量检索。
- 当前章节识别主要依赖规则，复杂目录或跨页标题可能不完美。
- MinerU 部署路径固定在当前机器的 `K:\MinerU`。
- 大模型调用依赖用户自己的 `SILICONFLOW_API_KEY`。
- HTML 是演示层，不承担复杂权限、用户管理或多知识库管理。

## 12. 后续增强方向

进入下一阶段前需要单独 Spec 讨论：

- 向量检索与 BM25 混合检索。
- LLM rerank。
- 多路由知识库。
- 文档上传与增量索引。
- 更完整的 UI 状态展示。
- 更大规模黄金评测集。
