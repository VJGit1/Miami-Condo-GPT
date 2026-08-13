"""Typed agent I/O — LLM proposes structure; server renders deterministically."""

from __future__ import annotations

from typing import Annotated, Any, Literal, Optional, Union
from uuid import uuid4

from pydantic import BaseModel, Field


class SqlCitation(BaseModel):
    query: str
    blocked: bool = False
    block_reason: Optional[str] = None
    row_count_hint: Optional[int] = None


class DocCitation(BaseModel):
    type: Literal["doc_citation"] = "doc_citation"
    source: str
    page: int = 1
    snippet: str = ""
    score: Optional[float] = None


class ChartDataset(BaseModel):
    label: str
    data: list[float]
    backgroundColor: Optional[Union[str, list[str]]] = None
    borderColor: Optional[Union[str, list[str]]] = None


class ChartArtifact(BaseModel):
    type: Literal["chart"] = "chart"
    chart_type: Literal["bar", "line", "pie", "doughnut"] = "bar"
    title: str = ""
    labels: list[str]
    datasets: list[ChartDataset]


class MapMarker(BaseModel):
    lat: float
    lng: float
    label: str
    kind: Literal["building", "school", "other"] = "building"
    address: Optional[str] = None


class MapArtifact(BaseModel):
    type: Literal["map"] = "map"
    title: str = ""
    markers: list[MapMarker]
    zoom: int = 13


class TableArtifact(BaseModel):
    type: Literal["table"] = "table"
    title: str = ""
    columns: list[str]
    rows: list[list[Any]]


class PdfSection(BaseModel):
    heading: str
    body: str = ""
    table: Optional[TableArtifact] = None


class PdfArtifact(BaseModel):
    type: Literal["pdf"] = "pdf"
    title: str
    filename: str = "condo_report.pdf"
    sections: list[PdfSection] = Field(default_factory=list)


class HtmlArtifact(BaseModel):
    """Legacy HTML (charts/maps) emitted by the model — sanitized, never executed as code."""

    type: Literal["html"] = "html"
    html: str


Artifact = Annotated[
    Union[ChartArtifact, MapArtifact, TableArtifact, PdfArtifact, HtmlArtifact, DocCitation],
    Field(discriminator="type"),
]


class ConversationTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    sql_citations: list[dict[str, Any]] = Field(default_factory=list)


AgentStatus = Literal["completed", "pending_approval", "refused", "error"]


class AgentResponse(BaseModel):
    run_id: str = Field(default_factory=lambda: str(uuid4()))
    text: str = ""
    artifacts: list[Artifact] = Field(default_factory=list)
    sql_citations: list[SqlCitation] = Field(default_factory=list)
    doc_citations: list[DocCitation] = Field(default_factory=list)
    refused: bool = False
    refusal_reason: Optional[str] = None
    status: AgentStatus = "completed"
    pending_sql: Optional[str] = None
    pending_rationale: Optional[str] = None
    confidence: Optional[float] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    est_cost_usd: Optional[float] = None
    cache_hit: bool = False
    route: Optional[str] = None
    prompt_version: str = ""
    latency_ms: Optional[float] = None
    error: Optional[str] = None

    def display_blocks(self) -> list:
        """Flatten to HTML/text blocks for the legacy template loop."""
        from markupsafe import Markup

        from condo_gpt.renderers import render_artifacts, render_doc_citations

        blocks: list = []
        if self.text:
            blocks.append(Markup(self.text) if not hasattr(self.text, "__html__") else self.text)
        blocks.extend(render_artifacts(self.artifacts))
        if self.doc_citations:
            blocks.extend(render_doc_citations(self.doc_citations))
        if self.sql_citations:
            cites = []
            for c in self.sql_citations:
                status = "BLOCKED" if c.blocked else "executed"
                cites.append(f"-- {status}\n{c.query}")
                if c.block_reason:
                    cites.append(f"-- reason: {c.block_reason}")
            blocks.append(
                Markup(
                    "<details open><summary>SQL citations</summary><pre>"
                    + "\n\n".join(cites)
                    + "</pre></details>"
                )
            )
        meta_parts = []
        if self.run_id:
            meta_parts.append(f"run_id: {self.run_id}")
        if self.est_cost_usd is not None:
            meta_parts.append(f"cost: ${self.est_cost_usd:.4f}")
        if self.cache_hit:
            meta_parts.append("cache hit")
        if self.confidence is not None:
            meta_parts.append(f"confidence: {self.confidence:.0%}")
        if self.status == "pending_approval":
            meta_parts.append("pending approval")
        if meta_parts:
            blocks.append(Markup(f'<p class="run-meta">{" · ".join(meta_parts)}</p>'))
        return blocks
