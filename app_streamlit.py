import streamlit as st
from src.config import load_config
from src.pipeline import LabRAGPipeline

st.set_page_config(page_title="实验室 SOP 知识库", layout="wide")
st.title("实验室 SOP 知识库智能问答")

with st.sidebar:
    st.subheader("知识库")
    if st.button("重新构建知识库", use_container_width=True):
        with st.spinner("正在解析 PDF 并生成 chunk..."):
            count = LabRAGPipeline(load_config()).ingest()
        st.success(f"已生成 {count} 个 chunk")
    st.caption("默认使用 data/examples 中的两份 PDF")

question = st.text_area("输入问题", placeholder="例如：ARTP诱变仪参数如何设置？", height=100)

if st.button("生成答案", type="primary") and question.strip():
    with st.spinner("正在检索 SOP 文档..."):
        result = LabRAGPipeline(load_config()).answer(question.strip())
    st.subheader("答案")
    st.write(result["answer"])
    st.subheader("来源")
    for source in result["sources"]:
        st.markdown(
            f"- `{source['doc_name']}` / 第 `{source['page_no']}` 页 / "
            f"`{source['chunk_id']}` / score `{source['score']:.3f}`"
        )
