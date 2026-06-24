# 实验室 SOP 知识库

基于两份实验室 PDF 的本地可测试 RAG 知识库。

检索默认使用混合模式：本地关键词检索与 FAISS 向量检索分别召回候选片段，
再通过加权 RRF 融合和本地规则重排后交给 LLM。

默认 PDF 解析器为部署在 `K:\MinerU` 的 MinerU `pipeline` 后端；MinerU 失败时自动回退 PyPDF2。

默认事实来源：

- `data/examples/江涛组相关实验SOP及附录---2020.5.19 (2).pdf`
- `data/examples/gao lab protocol.pdf`

## 安装

```bash
pip install -r requirements.txt
copy .env.example .env
```

默认生成服务为 SiliconFlow 官方免费模型 `Qwen/Qwen3-8B`。在项目 `.env`
中配置本人从官方控制台创建的 `SILICONFLOW_API_KEY` 后启用；未配置 API key 或网络
不可用时，系统自动使用本地抽取式答案。
项目启动时会优先加载当前项目的 `.env`，覆盖机器中可能存在的旧 `DASHSCOPE_API_KEY`。

阿里云百炼支持 OpenAI 兼容调用方式。使用 OpenAI Python/Node SDK 调用百炼时：

- `api_key` 使用 `DASHSCOPE_API_KEY`。
- `base_url` 使用 `https://dashscope.aliyuncs.com/compatible-mode/v1`。
- 不需要 OpenAI 官方 `OPENAI_API_KEY`。
- OpenAI 兼容表示接口协议兼容，并不表示调用 OpenAI 官方模型。

## CLI

```bash
python main.py ingest
python main.py search "ARTP诱变仪参数设置"
python main.py ask "如何使用 UniProt 查询蛋白基本信息？"
```

首次运行 `ingest` 时，MinerU 会解析两份完整 PDF，耗时明显长于 PyPDF2。

## HTTP API

```bash
python server.py
```

服务地址：`http://127.0.0.1:8765`

接口：

- `GET /api/docs`
- `POST /api/search`
- `POST /api/answer`
- `POST /api/upload`

示例请求：

```json
{"question":"ARTP诱变仪参数设置","top_k":5,"doc_name":null,"rerank":true}
```

`/api/upload` 使用 `multipart/form-data`，字段名为 `file`，仅支持 PDF。上传后文件保存到
`data/examples/`，并立即全量重建知识库；同名 PDF 会自动重命名。

## 测试

```bash
python -m unittest discover -s tests -p "test_*.py"
```

测试包括真实 PDF 解析、chunk 页码保留、检索与重排、API 契约、10 条检索冒烟集和 10 条问答冒烟集。

## 规格文档

项目整体规格位于根目录 `../spec/`。
