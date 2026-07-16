def test_health_returns_typed_success_contract(client) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "success",
        "data": {
            "service": "shravya-backend",
            "environment": "development",
            "provider_mode": "demo",
        },
    }
