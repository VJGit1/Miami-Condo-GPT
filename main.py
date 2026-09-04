import ast
import os
import re
import markdown
from markupsafe import Markup

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
POSTGRES_PORT = os.getenv("PG_PORT", "5432")
POSTGRES_DB = os.getenv("PG_DB", "condo_gpt")

connection_string = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@localhost:{POSTGRES_PORT}/{POSTGRES_DB}"
db = None
usable_tables = []
try:
    if POSTGRES_USER and POSTGRES_PASSWORD:
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
        return None, "PDF Generated!", code

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


def process_question(prompted_question: str, conversation_history: list) -> list:
    """Process user query via the LangGraph ReAct agent with dynamic code execution & guardrails."""
    context = "\n".join(
        [
            f"Q: {entry['question']}\nA: {entry['answer']}"
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
    for step in agent_executor.stream({"messages": [HumanMessage(content=prompt)]}):
        for msg in step.get("agent", {}).get("messages", []):
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for call in msg.tool_calls:
                    if sql := call.get("args", {}).get("query"):
                        log_sql_query(sql)

            if msg.content:
                html_block, stripped_text, code = extract_and_remove_html(msg.content)
                
                # Execute generated Python code (e.g. ReportLab) after safety scan
                if code:
                    if not detect_malicious_code(code):
                        try:
                            exec(code, globals())
                        except Exception as exc:
                            print(f"[EXEC ERROR] Error executing generated code: {exc}")

                if stripped_text:
                    content.append(process_markdown(stripped_text))
                if html_block:
                    content.append(html_block)

    return content
