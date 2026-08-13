from pathlib import Path

from backend.app.services.knowledge_base import KnowledgeBase


def test_metadata_contract_and_growth_routing():
    kb = KnowledgeBase(Path("backend/app/enterprise_rag"))
    hits = kb.search("如何提升年轻用户转化？", top_k=3)
    assert hits
    assert hits[0]["document_type"] == "user_growth"
    assert hits[0]["chunk_id"]
    assert "matched_keywords" in hits[0]


def test_brand_routing_reserves_brand_and_case_sources():
    kb = KnowledgeBase(Path("backend/app/enterprise_rag"))
    hits = kb.search("如何识别年轻、非一线城市的潜力用户？", top_k=3)
    types = {hit["document_type"] for hit in hits}
    assert "brand" in types
    assert "marketing_case" in types
