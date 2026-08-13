"""Document RAG search — offline."""

from condo_gpt.retrieval.doc_search import search_documents


def test_doc_search_shore_club_pets():
    hits = search_documents("Shore Club pet policy weight limit")
    assert hits
    assert any("shore" in h["source"].lower() for h in hits)
    assert any("pet" in h["text"].lower() for h in hits)


def test_doc_search_continuum_rental():
    hits = search_documents("Continuum rental minimum 30 days Airbnb")
    assert hits
    text = " ".join(h["text"].lower() for h in hits)
    assert "rental" in text or "30 days" in text
