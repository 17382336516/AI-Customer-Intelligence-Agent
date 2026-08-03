from fastapi.testclient import TestClient

from app.main import app


def test_demo_dataset_to_strategy_cards_end_to_end():
    with TestClient(app) as client:
        dataset_response = client.post("/api/v1/demo/dataset")
        assert dataset_response.status_code == 201
        dataset = dataset_response.json()
        assert dataset["quality"]["can_analyze"] is True

        analysis_response = client.post(
            "/api/v1/analyses",
            json={
                "dataset_id": dataset["id"],
                "question": "哪些人群适合做旅行攒钱专题页？请输出页面方向和 slogan",
                "strategy_goal": "完整产品策略卡",
                "brand_tone": "温暖可信",
                "analysis_window": "全部数据",
            },
        )
        assert analysis_response.status_code == 202
        analysis_id = analysis_response.json()["id"]

        final_response = client.get(f"/api/v1/analyses/{analysis_id}")
        assert final_response.status_code == 200
        final = final_response.json()
        assert final["status"] == "completed"
        assert final["result"]["route"] == "full_strategy"
        assert len(final["result"]["strategy_cards"]) >= 3

        event_response = client.get(f"/api/v1/analyses/{analysis_id}/events")
        assert event_response.status_code == 200
        assert len(event_response.json()) >= 5

        delete_response = client.delete(f"/api/v1/datasets/{dataset['id']}")
        assert delete_response.status_code == 204
