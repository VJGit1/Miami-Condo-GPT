"""Hybrid retrieval: schema cards, glossary, examples, entities."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

import yaml

RETRIEVAL_DIR = Path(__file__).resolve().parent
ARTIFACTS_DIR = RETRIEVAL_DIR / "artifacts"


@dataclass
class RetrievedContext:
    question: str
    route: str
    schema_cards: list[str] = field(default_factory=list)
    glossary: list[str] = field(default_factory=list)
    examples: list[dict[str, str]] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)
    retrieval_score: float = 0.0

    def to_prompt_block(self) -> str:
        parts: list[str] = []
        if self.glossary:
            parts.append("Glossary:\n" + "\n".join(f"- {g}" for g in self.glossary))
        if self.schema_cards:
            parts.append("Schema:\n" + "\n\n".join(self.schema_cards))
        if self.examples:
            ex_lines = []
            for ex in self.examples:
                ex_lines.append(f"Q: {ex['question']}\nSQL: {ex['sql']}")
            parts.append("Similar examples:\n" + "\n\n".join(ex_lines))
        if self.entities:
            parts.append("Entity matches: " + ", ".join(self.entities))
        return "\n\n".join(parts)


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _score_overlap(query_tokens: set[str], doc_tokens: set[str]) -> float:
    if not query_tokens or not doc_tokens:
        return 0.0
    return len(query_tokens & doc_tokens) / len(query_tokens | doc_tokens)


def _load_glossary() -> list[dict[str, str]]:
    path = RETRIEVAL_DIR / "glossary.yaml"
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data.get("terms", [])


def _load_schema_cards() -> list[str]:
    path = RETRIEVAL_DIR / "schema_cards.yaml"
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    cards: list[str] = []
    for table in data.get("tables", []):
        lines = [
            f"Table {table['name']}: {table.get('use_when', '')}",
            f"Columns: {', '.join(table.get('key_columns', []))}",
            f"Joins: {', '.join(table.get('join_keys', []))}",
        ]
        if table.get("filters"):
            lines.append(f"Filters: {table['filters']}")
        cards.append("\n".join(lines))
    return cards


def _load_examples() -> list[dict[str, str]]:
    path = RETRIEVAL_DIR / "examples.jsonl"
    if not path.exists():
        return []
    examples: list[dict[str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            examples.append(json.loads(line))
    return examples


def _rank_by_overlap(
    question: str, items: list[Any], text_fn
) -> list[tuple[float, Any]]:
    q_tokens = _tokenize(question)
    scored = []
    for item in items:
        doc_tokens = _tokenize(text_fn(item))
        scored.append((_score_overlap(q_tokens, doc_tokens), item))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored


def retrieve_context(
    question: str,
    route: str = "sql_qa",
    *,
    entity_names: Optional[list[str]] = None,
    top_k_examples: int = 3,
    top_k_glossary: int = 5,
    top_k_schema: int = 4,
) -> RetrievedContext:
    """Retrieve hybrid context for plan_sql / synthesize nodes."""
    glossary_terms = _load_glossary()
    schema_cards = _load_schema_cards()
    examples = _load_examples()

    q_lower = question.lower()
    route_hint = route

    # Rank glossary
    gloss_scored = _rank_by_overlap(
        question,
        glossary_terms,
        lambda t: f"{t.get('term', '')} {t.get('definition', '')}",
    )
    glossary_out = [
        f"{t['term']}: {t['definition'].strip()}"
        for _, t in gloss_scored[:top_k_glossary]
        if t.get("term")
    ]

    # Rank schema cards — boost tables mentioned in question
    table_boost = []
    for card in schema_cards:
        score = _score_overlap(_tokenize(question), _tokenize(card))
        if route in {"join", "aggregation", "sql_qa"}:
            if any(kw in q_lower for kw in ("sale", "price", "volume", "join")):
                if "core_condosale" in card:
                    score += 0.3
            if any(kw in q_lower for kw in ("building", "address", "collins", "brickell")):
                if "core_condobuilding" in card:
                    score += 0.3
        table_boost.append((score, card))
    table_boost.sort(key=lambda x: x[0], reverse=True)
    schema_out = [c for _, c in table_boost[:top_k_schema]]

    # Rank examples
    ex_scored = _rank_by_overlap(
        question, examples, lambda e: f"{e.get('question', '')} {e.get('sql', '')}"
    )
    examples_out = [e for _, e in ex_scored[:top_k_examples]]

    entities = list(entity_names or [])
    scores = [s for s, _ in ex_scored[:top_k_examples]] + [s for s, _ in gloss_scored[:1]]
    retrieval_score = sum(scores) / len(scores) if scores else 0.5
    if schema_out:
        retrieval_score = max(retrieval_score, 0.4)

    return RetrievedContext(
        question=question,
        route=route_hint,
        schema_cards=schema_out,
        glossary=glossary_out,
        examples=examples_out,
        entities=entities,
        retrieval_score=min(1.0, retrieval_score + (0.1 if entities else 0)),
    )


@lru_cache(maxsize=1)
def get_example_count() -> int:
    return len(_load_examples())
