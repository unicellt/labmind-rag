import os
import importlib.util
import json
import re
import urllib.request
from pathlib import Path
try:
    from dotenv import load_dotenv as _python_load_dotenv
except ModuleNotFoundError:
    _python_load_dotenv = None
from src.prompts import LAB_QA_SYSTEM_PROMPT, build_user_prompt
from src.schemas import RetrievedChunk


def _load_project_env(env_path: Path) -> None:
    if _python_load_dotenv is not None:
        _python_load_dotenv(dotenv_path=env_path, override=True)
        return
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ[key.strip()] = value.strip().strip("\"'")


class AnswerGenerator:
    def __init__(
        self,
        provider: str,
        model: str,
        temperature: float,
        base_url: str = "",
        api_key_env: str = "",
    ):
        self.provider = provider
        self.model = model
        self.temperature = temperature
        self.base_url = base_url.rstrip("/")
        self.api_key_env = api_key_env
        self.last_mode = "extractive"
        self.last_error = ""
        project_env = Path(__file__).resolve().parents[1] / ".env"
        _load_project_env(project_env)

    def generate(self, question: str, chunks: list[RetrievedChunk], answer_type: str = "综合") -> str:
        if not chunks:
            return "当前文档中未找到足够依据回答该问题。"
        context = "\n\n".join(
            f"[来源: {item.doc_name} / 第 {item.page_no} 页 / {item.chunk_id} / score={item.score:.3f}]\n{item.text}"
            for item in chunks
        )
        user_prompt = build_user_prompt(question, context, answer_type=answer_type)
        if self.provider.lower() == "dashscope":
            if not os.getenv("DASHSCOPE_API_KEY") or importlib.util.find_spec("dashscope") is None:
                return self._extractive_answer(question, chunks)
            try:
                answer = self._dashscope_chat(user_prompt)
                self.last_mode = "llm"
                return answer
            except Exception as exc:
                self.last_error = f"{type(exc).__name__}: {exc}"
                return self._extractive_answer(question, chunks)
        if self.provider.lower() in {"openai_compatible", "siliconflow"}:
            if not self.api_key_env or not os.getenv(self.api_key_env) or not self.base_url:
                return self._extractive_answer(question, chunks)
            try:
                answer = self._openai_compatible_chat(user_prompt)
                self.last_mode = "llm"
                return answer
            except Exception as exc:
                self.last_error = f"{type(exc).__name__}: {exc}"
                return self._extractive_answer(question, chunks)
        return self._extractive_answer(question, chunks)

    def _openai_compatible_chat(self, user_prompt: str) -> str:
        api_key = os.getenv(self.api_key_env)
        if not api_key:
            raise RuntimeError(f"{self.api_key_env} is not configured")
        payload = json.dumps(
            {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": LAB_QA_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": self.temperature,
            },
            ensure_ascii=False,
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=90) as response:
            result = json.loads(response.read().decode("utf-8"))
        return result["choices"][0]["message"]["content"]

    def _dashscope_chat(self, user_prompt: str) -> str:
        api_key = os.getenv("DASHSCOPE_API_KEY")
        if not api_key:
            raise RuntimeError("DASHSCOPE_API_KEY is not configured")
        try:
            import dashscope
        except ModuleNotFoundError:
            raise RuntimeError("dashscope package is not installed")
        dashscope.api_key = api_key
        response = dashscope.Generation.call(
            model=self.model,
            messages=[
                {"role": "system", "content": LAB_QA_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=self.temperature,
            result_format="message",
        )
        if response.status_code != 200:
            return f"DashScope 调用失败：{response.code} {response.message}"
        return response.output.choices[0].message.content

    @staticmethod
    def _extractive_answer(question: str, chunks: list[RetrievedChunk]) -> str:
        lines = ["以下为基于当前文档片段整理的抽取式答案。"]
        for idx, chunk in enumerate(chunks[:3], start=1):
            text = AnswerGenerator._relevant_excerpt(question, chunk.text)
            section = f" / {chunk.section_title}" if chunk.section_title else ""
            lines.append(f"{idx}. {text}（来源：{chunk.doc_name} / 第 {chunk.page_no} 页{section} / {chunk.chunk_id}）")
        return "\n".join(lines)

    @staticmethod
    def _relevant_excerpt(question: str, text: str, max_chars: int = 700) -> str:
        ascii_terms = re.findall(r"[a-zA-Z0-9_\-]+", question.lower())
        chinese_runs = re.findall(r"[\u4e00-\u9fa5]{2,}", question)
        chinese_terms = []
        for run in chinese_runs:
            for size in range(2, min(4, len(run)) + 1):
                chinese_terms.extend(run[index:index + size] for index in range(len(run) - size + 1))
        terms = set(ascii_terms + chinese_terms)
        sentences = [item.strip() for item in re.split(r"(?<=[。；;！？!?])|\n", text) if item.strip()]
        scored = []
        for index, sentence in enumerate(sentences):
            lowered = sentence.lower()
            score = sum(max(len(term), 1) for term in terms if term.lower() in lowered)
            scored.append((score, index, sentence))
        selected = sorted((item for item in scored if item[0] > 0), key=lambda item: (-item[0], item[1]))[:8]
        if not selected:
            return " ".join(text.split())[:max_chars]
        selected.sort(key=lambda item: item[1])
        excerpt = " ".join(item[2] for item in selected)
        return excerpt[:max_chars]
