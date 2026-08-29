"""Hybrid retrieval tests — offline."""

from condo_gpt.retrieval.service import get_example_count, retrieve_context


def test_examples_count_at_least_15():
    assert get_example_count() >= 15


def test_retrieve_includes_glossary_for_volume():
    ctx = retrieve_context("What is sales volume for Collins buildings?", "aggregation")
    assert ctx.glossary
    assert any("sales volume" in g.lower() for g in ctx.glossary)


def test_retrieve_includes_schema_cards():
    ctx = retrieve_context("Join sales to buildings", "join")
    assert ctx.schema_cards
    joined = "\n".join(ctx.schema_cards)
    assert "core_condosale" in joined or "core_condobuilding" in joined


def test_retrieve_examples_ranked():
    ctx = retrieve_context("List approved buildings with addresses", "sql_qa")
    assert len(ctx.examples) >= 1
    assert "question" in ctx.examples[0]
    assert "sql" in ctx.examples[0]
