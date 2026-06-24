# MinerU 部署与接入 Spec

版本: v1.0

## 目标

在 `K:\MinerU` 部署独立 MinerU 环境，用于两份实验室 PDF 的高质量本地解析，并作为 `lab-rag-qa` 的可选解析后端。

## 已确认环境

- 操作系统: Windows
- GPU: Quadro T1000 4GB
- Docker: 未安装
- WSL2 Linux 发行版: 未安装
- 当前项目 Python: 3.9，不满足当前 MinerU Python 3.10-3.12 要求

## 部署决策

- 部署位置: `K:\MinerU`
- Python: 由 `uv` 独立安装 Python 3.12
- 虚拟环境: `K:\MinerU\.venv`
- uv 缓存: `K:\MinerU\uv-cache`
- MinerU 后端: 默认使用 `pipeline`
- 不默认启用 VLM/GPU 后端，原因是显存低于官方建议的 8GB

## 验收标准

- [x] `K:\MinerU\.venv\Scripts\mineru.exe --version` 可运行，版本为 3.2.2。
- [x] Pipeline 模型已下载到 K 盘。
- [x] 两份项目 PDF 已完成完整解析，并输出 Markdown/结构化结果。
- [x] 已接入 `lab-rag-qa`，并保留现有 PyPDF2 回退路径。

## API Key 约定

阿里云百炼的 OpenAI 兼容接口不需要 OpenAI 官方 API Key，但仍然需要有效的阿里云百炼 `DASHSCOPE_API_KEY`，并配置百炼兼容接口的 `base_url`。
