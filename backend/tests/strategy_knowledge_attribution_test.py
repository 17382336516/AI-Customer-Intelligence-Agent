from backend.app.services.strategy_knowledge_attribution import attribute_knowledge


def test_no_retrieved_knowledge_produces_no_applications():
    card = {"product_strategy": "推荐普通商品", "channels": ["APP push"]}
    enriched = attribute_knowledge([card], [])
    assert enriched[0]["knowledge_applications"] == []
    assert enriched[0]["used_knowledge_sources"] == []


def test_bi_bi_zan_concept_is_attributed_to_strategy_field():
    card = {
        "product_strategy": "通过自动储蓄和攒钱机制降低低门槛，帮助用户养成储蓄习惯",
        "content_strategy": "用无痛攒钱场景讲解",
        "promotion_strategy": "低门槛首投权益",
        "channels": ["APP push"],
    }
    retrieval = [
        {
            "document_source": "product\\bi_bi_zan.md",
            "retrieved_content": "自动小额储蓄，降低使用门槛，帮助用户攒钱。",
        }
    ]
    enriched = attribute_knowledge([card], retrieval)
    apps = enriched[0]["knowledge_applications"]
    assert len(apps) == 1
    assert apps[0]["document_source"] == "product\\bi_bi_zan.md"
    assert apps[0]["strategy_field"] == "product_strategy"
    assert "自动" in apps[0]["applied_concept"]
