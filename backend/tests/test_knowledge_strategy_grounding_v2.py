from app.services.strategy_verifier import verify_strategy_grounding


def _verify(knowledge, strategy):
    evidence = [{"document_source": "product/bi_bi_zan.md", "evidence_text": knowledge}]
    trace = [{"source": "product/bi_bi_zan.md", "concept": "自动小额储蓄", "used_in": "product_strategy"}]
    return verify_strategy_grounding(strategy, evidence, trace)


def test_business_concept_grounding_passes_semantic_alias():
    result = _verify("自动小额储蓄降低使用门槛", {"product_strategy": "通过低门槛储蓄机制培养用户长期习惯"})
    assert result["knowledge_grounded"] is True
    assert result["grounding_score"] == 1.0
    assert result["matched_concepts"][0]["match_type"] == "business_concept_match"


def test_brand_trust_alias_passes():
    evidence = [{"document_source": "brand/brand_profile.md", "evidence_text": "品牌定位与品牌价值"}]
    trace = [{"source": "brand/brand_profile.md", "concept": "品牌定位", "used_in": "content_strategy"}]
    result = verify_strategy_grounding({"content_strategy": "提升用户信任和品牌认可"}, evidence, trace)
    assert result["knowledge_grounded"] is True


def test_unrelated_promotion_does_not_match_product_concept():
    result = _verify("自动储蓄降低使用门槛", {"product_strategy": "普通满减优惠"})
    assert result["knowledge_grounded"] is False
    assert result["grounding_score"] == 0.0
