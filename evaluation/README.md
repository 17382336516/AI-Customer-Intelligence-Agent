# Evaluation v1

## Insight I1

`I1 Segment Recognition Rate` evaluates whether Insight Agent evidence identifies the
Golden Label segment through normalized signals in `insight_records`: `top_tags`,
`value_tier`, `behavior_profile`, `recommended_actions`, and the supporting profile
text. It does not compare a product-interest label directly with a lifecycle label.

## Knowledge preflight

Runner loads the configured Enterprise RAG directory before Agent execution and prints
`knowledge_base_loaded_documents_count`. A zero-document knowledge base stops the run.

## Artifacts

Each completed question persists four JSON artifacts under
`evaluation/reports/artifacts/<dataset_id>/<question_id>/`.
