from fastapi.testclient import TestClient

from backend.app.main import app


def test_geojson_import_exposes_spatial_objects_and_features():
    with TestClient(app) as client:
        imported = client.post("/api/management/gis/import")
        assert imported.status_code == 200, imported.text

        status = client.get("/api/management/gis/status")
        assert status.status_code == 200
        assert status.json()["source_exists"] is True
        assert status.json()["imported"]["feature_count"] == 629

        objects = client.get("/api/management/engineering-objects")
        assert objects.status_code == 200
        rows = objects.json()
        assert len(rows) >= 600
        spatial = next(row for row in rows if row["longitude"] is not None and row["geometry"])
        assert spatial["layer"]
        assert spatial["design_attributes"]

        gis = client.get("/api/gis")
        assert gis.status_code == 200
        payload = gis.json()
        assert len(payload["features"]) == 629
        assert {feature["geometry_type"] for feature in payload["features"]} >= {"Point", "LineString"}
