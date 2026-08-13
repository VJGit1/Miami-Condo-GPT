"""Deterministic renderers for structured artifacts (no model-authored Python exec)."""

from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Sequence

from markupsafe import Markup
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from condo_gpt.schemas import (
    Artifact,
    ChartArtifact,
    DocCitation,
    HtmlArtifact,
    MapArtifact,
    PdfArtifact,
    TableArtifact,
)

_SCRIPT_TAG_RE = re.compile(r"<script\b[^>]*>[\s\S]*?</script>", re.IGNORECASE)
_ON_ATTR_RE = re.compile(r"\son\w+\s*=\s*(['\"]).*?\1", re.IGNORECASE)


def sanitize_html(raw: str) -> str:
    """Remove script tags and inline event handlers from model-produced HTML."""
    cleaned = _SCRIPT_TAG_RE.sub("", raw)
    cleaned = _ON_ATTR_RE.sub("", cleaned)
    # Strip API key placeholders
    cleaned = re.sub(
        r"<script[^>]*\{gmaps_api_key\}[^>]*></script>",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    return cleaned


def render_chart(artifact: ChartArtifact) -> str:
    chart_id = f"chart_{abs(hash(artifact.title + str(artifact.labels))) % 10_000_000}"
    config = {
        "type": artifact.chart_type,
        "data": {
            "labels": artifact.labels,
            "datasets": [ds.model_dump(exclude_none=True) for ds in artifact.datasets],
        },
        "options": {
            "responsive": True,
            "plugins": {"title": {"display": bool(artifact.title), "text": artifact.title}},
        },
    }
    config_json = json.dumps(config)
    return f"""
<div class="chart-artifact">
  <canvas id="{chart_id}"></canvas>
  <script>
    (function() {{
      const ctx = document.getElementById("{chart_id}");
      if (ctx && window.Chart) {{ new Chart(ctx, {config_json}); }}
    }})();
  </script>
</div>
"""


def render_map(artifact: MapArtifact) -> str:
    markers = [
        {
            "lat": m.lat,
            "lng": m.lng,
            "label": m.label,
            "address": m.address or "",
            "kind": m.kind,
        }
        for m in artifact.markers
    ]
    markers_json = json.dumps(markers)
    title = html.escape(artifact.title or "Map")
    # Provide initMap expected by the Google Maps callback in the template
    return f"""
<div class="map-artifact">
  <h3>{title}</h3>
  <div id="map" style="width:100%;height:420px;border-radius:8px;"></div>
  <script>
    window.__condoMapMarkers = {markers_json};
    window.__condoMapZoom = {int(artifact.zoom)};
    function initMap() {{
      const markers = window.__condoMapMarkers || [];
      const center = markers.length
        ? {{ lat: markers[0].lat, lng: markers[0].lng }}
        : {{ lat: 25.7907, lng: -80.1300 }};
      const map = new google.maps.Map(document.getElementById("map"), {{
        zoom: window.__condoMapZoom || 13,
        center
      }});
      const bounds = new google.maps.LatLngBounds();
      markers.forEach((m) => {{
        const pos = {{ lat: m.lat, lng: m.lng }};
        new google.maps.Marker({{
          position: pos,
          map,
          title: (m.label || "") + (m.address ? (" - " + m.address) : ""),
          label: m.label
        }});
        bounds.extend(pos);
      }});
      if (markers.length > 1) {{ map.fitBounds(bounds); }}
    }}
    if (window.google && window.google.maps) {{ initMap(); }}
  </script>
</div>
"""


def render_table(artifact: TableArtifact) -> str:
    title = html.escape(artifact.title) if artifact.title else ""
    head = "".join(f"<th>{html.escape(str(c))}</th>" for c in artifact.columns)
    body_rows = []
    for row in artifact.rows:
        cells = "".join(f"<td>{html.escape(str(c))}</td>" for c in row)
        body_rows.append(f"<tr>{cells}</tr>")
    body = "\n".join(body_rows)
    heading = f"<h3>{title}</h3>" if title else ""
    return f"""
<div class="table-artifact">
  {heading}
  <table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;width:100%">
    <thead><tr>{head}</tr></thead>
    <tbody>{body}</tbody>
  </table>
</div>
"""


def render_pdf(artifact: PdfArtifact, output_dir: Path | None = None) -> str:
    out_dir = output_dir or Path.cwd()
    out_dir.mkdir(parents=True, exist_ok=True)
    # Sanitize filename
    safe_name = re.sub(r"[^\w.\-]+", "_", artifact.filename) or "condo_report.pdf"
    if not safe_name.lower().endswith(".pdf"):
        safe_name += ".pdf"
    path = out_dir / safe_name

    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(str(path), pagesize=letter)
    story = [Paragraph(html.escape(artifact.title), styles["Title"]), Spacer(1, 12)]
    for section in artifact.sections:
        story.append(Paragraph(html.escape(section.heading), styles["Heading2"]))
        if section.body:
            story.append(Paragraph(html.escape(section.body), styles["BodyText"]))
            story.append(Spacer(1, 8))
        if section.table and section.table.columns:
            data = [section.table.columns] + [
                [str(c) for c in row] for row in section.table.rows
            ]
            t = Table(data, hAlign="LEFT")
            t.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ]
                )
            )
            story.append(t)
            story.append(Spacer(1, 12))
    doc.build(story)
    return f'<p class="pdf-artifact">PDF Generated: <code>{html.escape(safe_name)}</code></p>'


def render_html_artifact(artifact: HtmlArtifact) -> str:
    return sanitize_html(artifact.html)


def render_doc_citation(citation: DocCitation) -> str:
    src = html.escape(citation.source)
    snippet = html.escape(citation.snippet[:300])
    return (
        f'<p class="doc-citation">'
        f'<strong>{src}</strong> · p.{citation.page} · '
        f'<em>{snippet}</em></p>'
    )


def render_doc_citations(citations: Sequence[DocCitation]) -> list[str]:
    return [Markup(render_doc_citation(c)) for c in citations]


def render_artifact(artifact: Artifact) -> str:
    if isinstance(artifact, ChartArtifact):
        return render_chart(artifact)
    if isinstance(artifact, MapArtifact):
        return render_map(artifact)
    if isinstance(artifact, TableArtifact):
        return render_table(artifact)
    if isinstance(artifact, PdfArtifact):
        return render_pdf(artifact)
    if isinstance(artifact, HtmlArtifact):
        return render_html_artifact(artifact)
    if isinstance(artifact, DocCitation):
        return render_doc_citation(artifact)
    return ""


def render_artifacts(artifacts: Sequence[Artifact]) -> list[str]:
    return [Markup(render_artifact(a)) for a in artifacts]
