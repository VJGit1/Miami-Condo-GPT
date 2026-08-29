"""Renderer unit tests (no external APIs)."""

from pathlib import Path

from condo_gpt.renderers import render_chart, render_pdf, render_table, sanitize_html
from condo_gpt.schemas import ChartArtifact, ChartDataset, PdfArtifact, PdfSection, TableArtifact


def test_sanitize_strips_script():
    raw = '<div>ok</div><script>alert(1)</script><img src=x onerror="alert(1)">'
    cleaned = sanitize_html(raw)
    assert "<script" not in cleaned.lower()
    assert "onerror" not in cleaned.lower()
    assert "<div>ok</div>" in cleaned


def test_render_chart_contains_canvas():
    art = ChartArtifact(
        title="Sales",
        labels=["A", "B"],
        datasets=[ChartDataset(label="Vol", data=[1.0, 2.0])],
    )
    html = render_chart(art)
    assert "<canvas" in html
    assert "Sales" in html


def test_render_table():
    art = TableArtifact(title="T", columns=["a", "b"], rows=[["1", "2"]])
    html = render_table(art)
    assert "<table" in html
    assert "<th>a</th>" in html


def test_render_pdf(tmp_path: Path):
    art = PdfArtifact(
        title="Report",
        filename="test_report.pdf",
        sections=[
            PdfSection(
                heading="Summary",
                body="Hello",
                table=TableArtifact(columns=["Building", "Sales"], rows=[["X", "3"]]),
            )
        ],
    )
    msg = render_pdf(art, output_dir=tmp_path)
    assert "PDF Generated" in msg
    assert (tmp_path / "test_report.pdf").exists()
