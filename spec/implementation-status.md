# 实验室知识库实施状态

更新时间: 2026-06-04

## 已完成

- 默认事实来源固定为两份 PDF。
- MinerU 3.2.2 已部署到 `K:\MinerU`，并完成 pipeline 模型下载和两页 PDF 解析冒烟验证。
- 项目默认解析器已接入 K 盘本地 MinerU，失败时回退 PyPDF2。
- 本地 PDF 按页解析，chunk 保留 `doc_name`、`page_no`、`section_title`、`chunk_id`。
- 中文断行清洗和章节标题识别。
- 本地关键词/IDF 检索、查询去噪、辨识度词项过滤和规则重排。
- 文档外问题低置信度拒答。
- 本地抽取式答案和 DashScope/Qwen 异常回退。
- CLI: `ingest`、`search`、`ask`。
- HTTP API: `/api/docs`、`/api/search`、`/api/answer`。
- HTTP API 新增 `/api/upload`，支持 PDF 上传后立即全量重建知识库。
- `data/examples/*.pdf` 会自动纳入知识库来源，docx/md 等非 PDF 不进入上传主线。
- HTML 搜索结果固定按相关性得分降序展示前五名，并显示排名与三位小数得分。
- HTML 新增 PDF 上传区，上传完成后刷新文档下拉框并选中新文档。
- HTML 历史乱码问号已清除，并增加用户可见文案编码回归测试。
- README 和 Streamlit 演示文案。
- 10 条检索冒烟集和 10 条问答冒烟集。

## 当前验证结果

- 使用 MinerU 完整解析两份 PDF 后，默认 ingest 成功生成 122 个结构化 chunk。
- 自动测试: 31 个测试通过。
- 检索冒烟集: 10/10 纳入集成测试并通过。
- 问答冒烟集: 10/10 纳入集成测试并通过。
- 文档外问题能够返回“当前文档中未找到足够依据”。

## 剩余风险

- PyPDF2 仅保留为 MinerU 失败时的回退解析器。
- 当前章节识别为规则方法，部分章节标题仍可能不够准确。
- 当前检索是本地关键词/IDF 路线，不包含向量检索。
- DashScope/Qwen 在线生成未纳入默认离线测试。
- `site/index.html` 旧静态页面仍有历史乱码，未作为第一阶段主交付面处理。
