def test_unknown_route_returns_typed_error_contract(client) -> None:
    response = client.get("/api/v1/unknown")

    assert response.status_code == 404
    body = response.json()
    assert body["status"] == "error"
    assert body["code"] == "HTTP_404"
    assert body["recoverable"] is True
    assert "next_actions" in body
