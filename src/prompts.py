LAB_QA_SYSTEM_PROMPT = """你是实验室 SOP 知识库问答助手。

回答规则：
1. 只基于用户提供的上下文回答。
2. 对实验参数、剂量、温度、时间、浓度等信息保持原文一致。
3. 如果上下文不足，明确说明当前文档中未找到足够依据。
4. 不要把常识或猜测伪装成文档事实。
5. 涉及安全、PPE、废弃物和危险操作时保持保守。
6. 回答末尾保留来源，包含文档名、页码和 chunk_id。
"""

PROMPT_COLLECTION = {
    "步骤": "请按 1、2、3 的形式整理实验步骤。",
    "参数": "请优先提取时间、温度、体积、浓度、转速、pH 等参数。",
    "安全": "请优先提取注意事项、PPE、危险点和废弃物处理要求。",
    "试剂": "请优先提取试剂、材料、buffer、primer、enzyme 等信息。",
    "仪器": "请优先提取仪器、设备、耗材和使用条件。",
    "综合": "请综合回答问题，并保留关键来源。",
}

def build_user_prompt(question: str, context: str, answer_type: str = "综合") -> str:
    instruction = PROMPT_COLLECTION.get(answer_type, PROMPT_COLLECTION["综合"])
    return f"""回答类型要求：{instruction}

请只基于以下实验室文档片段回答。

{context}

---

用户问题：{question}

如果文档片段不足以回答，请明确说明“当前文档中未找到足够依据”。"""
