import ast
import os
import re
from urllib.parse import quote_plus
from uuid import uuid4
from dotenv import load_dotenv

load_dotenv()

import markdown
from markupsafe import Markup, escape

from googlemaps import Client as GoogleMaps
from langchain_community.utilities.sql_database import SQLDatabase
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

# ReportLab imports available in execution scope for dynamically generated code
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from boilerplate import (
    building_marker_format_boilerplate,
    holding_period_boilerplate,
    javascript_map_boilerplate,
    marker_boilerplate,
    school_marker_format_boilerplate,
    two_bed_holding_period_boilerplate,
)
from prefix import SQL_PREFIX
from tools import setup_tools

# Database credentials
POSTGRES_USER = os.getenv("PG_USER")
POSTGRES_PASSWORD = os.getenv("PG_PASSWORD")
POSTGRES_HOST = os.getenv("PG_HOST", "localhost")
POSTGRES_PORT = os.getenv("PG_PORT", "5432")
POSTGRES_DB = os.getenv("PG_DB", "condo_gpt")

GENERATED_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "generated")

db = None
usable_tables = []
try:
    if POSTGRES_USER and POSTGRES_PASSWORD:
        connection_string = (
            f"postgresql://{quote_plus(POSTGRES_USER)}:{quote_plus(POSTGRES_PASSWORD)}"
            f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
        )
        db = SQLDatabase.from_uri(connection_string)
        usable_tables = db.get_usable_table_names()
except Exception as exc:
    print(f"Note: Database connection deferred: {exc}")

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.0) if os.getenv("OPENAI_API_KEY") else None

# Build system prompt with database tables and domain boilerplates
prefix = SQL_PREFIX.format(
    table_names=usable_tables,
    marker_boilerplate=marker_boilerplate,
    holding_period_boilerplate=holding_period_boilerplate,
    two_bed_holding_period_boilerplate=two_bed_holding_period_boilerplate,
    javascript_map_boilerplate=javascript_map_boilerplate,
    building_marker_format_boilerplate=building_marker_format_boilerplate,
    school_marker_format_boilerplate=school_marker_format_boilerplate,
)

system_message = SystemMessage(content=prefix)

# Initialize agent tools and ReAct agent
tools = []
agent_executor = None
try:
    if db and llm:
        tools = setup_tools(db, llm)
        agent_executor = create_react_agent(llm, tools, messages_modifier=system_message)
except Exception as exc:
    print(f"Note: Agent initialization deferred: {exc}")


def log_sql_query(sql: str) -> None:
    print(f"\n[SQL GATEWAY EXECUTE]\n{sql}\n")


def _iter_messages(update) -> list:
    if not isinstance(update, dict):
        return []
    messages = update.get("messages", [])
    if not messages:
        return []
    if not isinstance(messages, list):
        return [messages]
    return messages


def _tool_call_name(call) -> str:
    if isinstance(call, dict):
        return str(call.get("name") or "")
    return str(getattr(call, "name", "") or "")


def _tool_call_args(call) -> dict:
    if isinstance(call, dict):
        args = call.get("args", {})
    else:
        args = getattr(call, "args", {})
    return args if isinstance(args, dict) else {}


def _named_content(msg) -> tuple[str, str]:
    if isinstance(msg, dict):
        return str(msg.get("name") or ""), str(msg.get("content") or "")
    return str(getattr(msg, "name", "") or ""), str(getattr(msg, "content", "") or "")


_MAP_DIV = re.compile(
    r"<div\b[^>]*\bid=(['\"])map\1[^>]*>(?:[\s\S]*?</div>)?",
    re.IGNORECASE,
)
_MAP_SCRIPT = re.compile(r"<script\b[^>]*>[\s\S]*?</script>", re.IGNORECASE)


def _is_model_map(text: str) -> bool:
    lowered = text.lower()
    return 'id="map"' in lowered or "id='map'" in lowered or "initmap" in lowered


def _without_model_map(text: str) -> str:
    def drop_script(match: re.Match) -> str:
        block = match.group(0)
        if "initmap" in block.lower() or "google.maps" in block.lower():
            return ""
        return block

    cleaned = _MAP_SCRIPT.sub(drop_script, text)
    cleaned = _MAP_DIV.sub("", cleaned)
    return cleaned.strip()


def process_html(text: str) -> str:
    """Clean duplicate google maps script tags."""
    pattern = r"<script[^>]*\{gmaps_api_key\}[^>]*></script>"
    return re.sub(pattern, "", text, flags=re.IGNORECASE)


def detect_malicious_code(code: str) -> bool:
    """Scan generated Python code against dangerous system modules and methods."""
    malicious_patterns = [
        r'import\s+(sys|subprocess|shlex|socket|ctypes|signal|multiprocessing)',
        r'os\.(system|popen|remove|rmdir|rename|chmod|chown|kill|fork)',
        r'subprocess\.(Popen|run|call|check_output)',
        r'eval\(',
        r'compile\(',
        r'shutil\.(copy|move|rmtree)',
        r'socket\.',
        r'requests\.',
        r'urllib\.',
        r'getattr\(', r'setattr\(',
        r'globals\(', r'locals\(',
        r'importlib\.',
        r'input\(',
        r'os\.exec',
    ]

    for pattern in malicious_patterns:
        if re.search(pattern, code):
            print(f"[SECURITY ALERT] Potentially dangerous pattern detected: {pattern}")
            return True
    return False


def _restricted_import(name, globals=None, locals=None, fromlist=(), level=0):
    """Allow generated reports to import ReportLab and nothing else."""
    if level != 0 or name.split(".", 1)[0] != "reportlab":
        raise ImportError(f"Import of {name} is not allowed")
    return __import__(name, globals, locals, fromlist, level)


def _pdf_namespace() -> dict:
    return {
        "__builtins__": {
            "__import__": _restricted_import,
            "abs": abs,
            "all": all,
            "any": any,
            "bool": bool,
            "dict": dict,
            "enumerate": enumerate,
            "float": float,
            "int": int,
            "len": len,
            "list": list,
            "max": max,
            "min": min,
            "print": print,
            "range": range,
            "round": round,
            "sorted": sorted,
            "str": str,
            "sum": sum,
            "tuple": tuple,
            "zip": zip,
        },
        "letter": letter,
        "canvas": canvas,
        "colors": colors,
        "getSampleStyleSheet": getSampleStyleSheet,
        "Paragraph": Paragraph,
        "SimpleDocTemplate": SimpleDocTemplate,
        "Spacer": Spacer,
        "Table": Table,
        "TableStyle": TableStyle,
    }


def _rewrite_pdf_target(code: str, pdf_path: str) -> str:
    """Point the first PDF filename in generated code at a unique file."""
    literal = pdf_path.replace("\\", "/")

    def _replace(match: re.Match) -> str:
        quote = match.group("q")
        return f"{quote}{literal}{quote}"

    rewritten, count = re.subn(
        r"""(?P<q>['"])(?P<name>[^'"]+\.pdf)(?P=q)""",
        _replace,
        code,
        count=1,
    )
    return rewritten if count else code


def execute_generated_pdf(code: str) -> Markup:
    """Run report code in an isolated namespace. Claim success only if the file exists."""
    if detect_malicious_code(code):
        return Markup(escape("PDF generation was blocked because the code failed the safety scan."))

    os.makedirs(GENERATED_DIR, exist_ok=True)
    filename = f"{uuid4().hex}.pdf"
    pdf_path = os.path.join(GENERATED_DIR, filename)
    namespace = _pdf_namespace()
    try:
        exec(_rewrite_pdf_target(code, pdf_path), namespace)
    except Exception as exc:
        print(f"[EXEC ERROR] Error executing generated code: {exc}")
        return Markup(escape(f"PDF generation failed: {exc}"))

    if os.path.isfile(pdf_path):
        return Markup(
            f'PDF generated. <a href="/downloads/{filename}">Download PDF</a>'
        )
    return Markup(escape("PDF generation failed: the script did not write a PDF file."))


def extract_and_remove_html(text: str) -> tuple[Markup | None, str, str | None]:
    """
    Extract dynamic Python code (for PDF report generation) and HTML blocks (for Chart.js / Maps).
    """
    # 1. Check for Python code blocks
    python_pattern = r'<pre\s+class="codehilite"><code\s+class="language-python">(.*?)</code></pre>'
    md_pattern = r"```python\s*([\s\S]*?)\s*```"
    python_match = re.search(python_pattern, text, re.DOTALL | re.IGNORECASE)
    md_match = re.search(md_pattern, text, re.DOTALL)
    code_match = python_match or md_match

    if code_match:
        code = code_match.group(1).strip()
        # Decode HTML entities if any
        code = (
            code.replace("&quot;", '"')
            .replace("&amp;", "&")
            .replace("&lt;", "<")
            .replace("&gt;", ">")
            .replace("&#39;", "'")
        )
        if python_match:
            remaining = re.sub(python_pattern, "", text, count=1, flags=re.DOTALL | re.IGNORECASE)
        else:
            remaining = re.sub(md_pattern, "", text, count=1, flags=re.DOTALL)
        return None, remaining.strip(), code

    # 2. Check for HTML code blocks (Chart.js / Maps)
    html_pattern = r"```html\s*([\s\S]*?)\s*```"
    match = re.search(html_pattern, text, re.IGNORECASE)
    if match:
        html_code = match.group(1).strip()
        cleaned_html = process_html(html_code)
        text_without_html = re.sub(html_pattern, "", text, flags=re.IGNORECASE).strip()
        return Markup(cleaned_html), text_without_html, None

    return None, text, None


def process_markdown(text: str) -> Markup:
    """Convert Markdown to safe HTML with syntax highlighting."""
    html_content = markdown.markdown(text, extensions=["extra", "codehilite"])
    return Markup(html_content)


def _history_answer(entry: dict) -> str:
    answer = entry.get("answer", "")
    if isinstance(answer, list):
        answer = " ".join(str(part) for part in answer)
    return str(answer)


def _message_text(msg) -> str:
    content = getattr(msg, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict) and isinstance(part.get("text"), str):
                parts.append(part["text"])
        return "".join(parts)
    return ""


def process_question(prompted_question: str, conversation_history: list) -> list:
    """Process user query via the LangGraph ReAct agent with dynamic code execution & guardrails."""
    if agent_executor is None:
        return [
            process_markdown(
                "The assistant is unavailable. Check the database connection and OPENAI_API_KEY, then restart the app."
            )
        ]

    context = "\n".join(
        [
            f"Q: {entry.get('question', '')}\nA: {_history_answer(entry)}"
            for entry in conversation_history
        ]
    )
    consolidated_prompt = f"""
Previous conversation:
{context}

New question: {prompted_question}

Please answer the new question, taking into account the context from the previous conversation if relevant.
"""
    prompt = consolidated_prompt if conversation_history else prompted_question

    content = []
    for step in agent_executor.stream(
        {"messages": [HumanMessage(content=prompt)]},
        stream_mode="updates",
    ):
        for msg in _iter_messages(step.get("agent") or {}):
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for call in msg.tool_calls:
                    name = _tool_call_name(call)
                    if name:
                        print(f"[TOOL] {name}")
                    args = _tool_call_args(call)
                    if sql := args.get("query"):
                        log_sql_query(sql)

            text = _message_text(msg)
            if not text.strip():
                continue
            html_block, stripped_text, code = extract_and_remove_html(text)
            if code:
                if stripped_text and not _is_model_map(stripped_text):
                    content.append(process_markdown(_without_model_map(stripped_text)))
                content.append(execute_generated_pdf(code))
                continue
            if stripped_text:
                visible = _without_model_map(stripped_text)
                if visible and not _is_model_map(visible):
                    content.append(process_markdown(visible))
            if html_block and not _is_model_map(str(html_block)):
                content.append(html_block)

        for msg in _iter_messages(step.get("tools") or {}):
            name, tool_html = _named_content(msg)
            if name == "show_map" and tool_html.strip():
                content.append(Markup(tool_html.strip()))

    return content
