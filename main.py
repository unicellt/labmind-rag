import click
import sys
from src.config import load_config
from src.mineru_parser import MinerUParser
from src.pipeline import LabRAGPipeline

def console_safe(text: str) -> str:
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    return str(text).encode(encoding, errors="replace").decode(encoding, errors="replace")

@click.group()
def cli():
    """实验室 SOP 知识库 RAG 工具。"""

@cli.command()
def ingest():
    """解析默认 PDF 文档并生成 chunk 与检索资产。"""
    pipeline = LabRAGPipeline(load_config())
    count = pipeline.ingest()
    click.echo(f"已生成 {count} 个 chunk。")

@cli.command("mineru-url")
@click.argument("pdf_url")
def mineru_url(pdf_url):
    """使用 MinerU 解析一个可访问的 PDF URL。"""
    cfg = load_config()
    parser = MinerUParser(api_base=cfg.parser.mineru_api_base)
    output_dir = parser.parse_pdf_url(pdf_url, cfg.parser.mineru_output_dir)
    click.echo(f"MinerU 解析结果已保存到：{output_dir}")


@cli.command("preview-chunks")
@click.option("--limit", default=5, help="预览 chunk 数量。")
@click.option("--output", default="data/chunks/chunk_preview.md", help="预览输出路径。")
def preview_chunks(limit, output):
    """生成 chunk Markdown 预览。"""
    import json
    from pathlib import Path

    cfg = load_config()
    rows = [json.loads(line) for line in cfg.paths.chunks.read_text(encoding="utf-8").splitlines() if line.strip()]
    lines = [f"# Chunk 预览", "", f"chunk_count: {len(rows)}", "", "## 文档统计"]
    for doc in sorted(set(r["doc_name"] for r in rows)):
        doc_rows = [r for r in rows if r["doc_name"] == doc]
        lengths = [len(r["text"]) for r in doc_rows]
        lines.append(f"- {doc}: {len(doc_rows)} chunks, min={min(lengths)}, max={max(lengths)}, avg={sum(lengths)//len(lengths)} chars")
    lines.extend(["", f"## 前 {limit} 个 chunk"])
    for r in rows[:limit]:
        preview = r["text"][:1200]
        lines.append(f"\n### {r['chunk_id']} | {r['doc_name']} | page={r.get('page_no')} | len={len(r['text'])}")
        lines.append("```text")
        lines.append(preview)
        lines.append("```")
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    click.echo(f"预览已写入：{output_path}")

@cli.command()
@click.argument("question")
@click.option("--top-k", default=None, type=int, help="返回来源数量。")
@click.option("--doc-name", default=None, help="限定查询的文档名。")
@click.option("--no-rerank", is_flag=True, help="关闭本地规则重排。")
def search(question, top_k, doc_name, no_rerank):
    """检索相关文档片段。"""
    pipeline = LabRAGPipeline(load_config())
    sources = pipeline.search(question, top_k=top_k, doc_name=doc_name, rerank=not no_rerank)
    if not sources:
        click.echo("未检索到相关来源。")
        return
    for idx, item in enumerate(sources, start=1):
        section = f" / {item['section_title']}" if item.get("section_title") else ""
        click.echo(console_safe(f"{idx}. {item['doc_name']} / 第 {item['page_no']} 页{section} / {item['chunk_id']} / score={item['score']:.3f}"))
        click.echo(console_safe(item["text"][:500].replace("\n", " ")))
        click.echo("")

@cli.command()
@click.argument("question")
@click.option("--top-k", default=None, type=int, help="返回来源数量。")
@click.option("--doc-name", default=None, help="限定查询的文档名。")
@click.option("--no-rerank", is_flag=True, help="关闭本地规则重排。")
def ask(question, top_k, doc_name, no_rerank):
    """基于知识库回答问题。"""
    pipeline = LabRAGPipeline(load_config())
    result = pipeline.answer(question, top_k=top_k, doc_name=doc_name, rerank=not no_rerank)
    click.echo(console_safe(result["answer"]))
    click.echo("\n来源：")
    for item in result["sources"]:
        section = f" / {item['section_title']}" if item.get("section_title") else ""
        click.echo(console_safe(f"- {item['doc_name']} / 第 {item['page_no']} 页{section} / {item['chunk_id']} / score={item['score']:.3f}"))

if __name__ == "__main__":
    cli()
