from fastapi.testclient import TestClient

from kura import __version__
from kura.api import create_app
from kura.config import DataPaths
from kura.migrations import MIGRATIONS
from tests.conftest import TOKEN


def test_health_reports_version_data_folder_and_schema(client: TestClient, paths: DataPaths):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "version": __version__,
        "dataDir": str(paths.root),
        "schemaVersion": len(MIGRATIONS),
    }


def test_requests_without_the_token_are_refused(client: TestClient):
    response = client.get("/health", headers={"Authorization": ""})

    assert response.status_code == 401


def test_requests_with_a_wrong_token_are_refused(client: TestClient):
    response = client.get("/health", headers={"Authorization": "Bearer guess"})

    assert response.status_code == 401


def test_requests_addressed_to_another_host_are_refused(paths: DataPaths):
    app = create_app(TOKEN, paths)
    headers = {"Authorization": f"Bearer {TOKEN}"}
    with TestClient(app, base_url="http://kura.example", headers=headers) as client:
        response = client.get("/health")

    assert response.status_code == 400


def test_the_app_window_may_call_the_api(client: TestClient):
    response = client.options(
        "/health",
        headers={
            "Origin": "http://tauri.localhost",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://tauri.localhost"


def test_other_web_pages_may_not(client: TestClient):
    response = client.options(
        "/health",
        headers={
            "Origin": "https://somewhere.example",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers
