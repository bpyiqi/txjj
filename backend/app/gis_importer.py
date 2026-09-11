from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .database import BASE_DIR, _sync_engineering_objects, db
from .engine import now_iso


DEFAULT_GEOJSON = BASE_DIR / "data" / "gis" / "latest_design.geojson"


def _first(properties: dict[str, Any], *names: str) -> Any:
    for name in names:
        value = properties.get(name)
        if value not in (None, ""):
            return value
    return None


def _flatten_coordinates(coordinates: Any) -> list[list[float]]:
    if not isinstance(coordinates, list) or not coordinates:
        return []
    if isinstance(coordinates[0], (int, float)) and len(coordinates) >= 2:
        return [[float(coordinates[0]), float(coordinates[1])]]
    result: list[list[float]] = []
    for item in coordinates:
        result.extend(_flatten_coordinates(item))
    return result


def _representative_point(geometry: dict[str, Any]) -> tuple[float | None, float | None]:
    points = _flatten_coordinates(geometry.get("coordinates"))
    if not points:
        return None, None
    longitude = sum(point[0] for point in points) / len(points)
    latitude = sum(point[1] for point in points) / len(points)
    return longitude, latitude


def _source_path(source_path: str | Path | None = None) -> Path:
    return Path(source_path or DEFAULT_GEOJSON).expanduser().resolve()


def _ensure_verification_results(conn) -> None:
    required_count = conn.execute("SELECT COUNT(*) AS n FROM rules WHERE mandatory=1").fetchone()["n"]
    missing = "等待关联现场证据"
    timestamp = now_iso()
    rows = conn.execute(
        "SELECT object_id FROM objects WHERE object_id NOT IN (SELECT object_id FROM verification_results)"
    ).fetchall()
    for row in rows:
        conn.execute(
            """INSERT INTO verification_results
               (object_id,required_count,matched_count,missing_evidence,completeness,status,issue_type,updated_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (row["object_id"], required_count, 0, missing, 0.0, "缺失影像", "影像缺失", timestamp),
        )


def import_geojson(source_path: str | Path | None = None) -> dict[str, Any]:
    source = _source_path(source_path)
    if not source.exists():
        return {
            "status": "not_available",
            "source_path": str(source),
            "feature_count": 0,
            "imported_count": 0,
            "changed": False,
        }

    raw_bytes = source.read_bytes()
    digest = hashlib.sha256(raw_bytes).hexdigest()
    payload = json.loads(raw_bytes.decode("utf-8"))
    features = payload.get("features", []) if isinstance(payload, dict) else []

    with db() as conn:
        source_key = str(source)
        previous = conn.execute(
            "SELECT source_sha256,feature_count FROM gis_import_meta WHERE source_path=?",
            (source_key,),
        ).fetchone()
        if previous and previous["source_sha256"] == digest and previous["feature_count"] == len(features):
            _sync_engineering_objects(conn)
            _ensure_verification_results(conn)
            return {
                "status": "up_to_date",
                "source_path": source_key,
                "feature_count": len(features),
                "imported_count": 0,
                "changed": False,
            }

        imported_count = 0
        timestamp = now_iso()
        for index, feature in enumerate(features):
            geometry = feature.get("geometry") or {}
            properties = dict(feature.get("properties") or {})
            feature_id = _first(properties, "code", "CODE", "object_id", "OBJECT_ID") or feature.get("id")
            if not feature_id:
                feature_id = f"GEO-{index + 1:06d}"
            feature_id = str(feature_id)
            layer = str(_first(properties, "layer", "LAYER") or "UNKNOWN")
            object_type = str(_first(properties, "object_type", "OBJECT_TYPE", "type", "TYPE") or layer)
            geometry_type = str(geometry.get("type") or "Unknown")
            coordinates = geometry.get("coordinates", [])
            longitude, latitude = _representative_point(geometry)
            location = None
            if longitude is not None and latitude is not None:
                location = f"X={longitude:.8f}; Y={latitude:.8f}"
            attributes = {**properties, "gis_source": source.name}
            conn.execute(
                """INSERT INTO objects(
                    object_id,layer,object_type,geometry_type,longitude,latitude,location,source_file,status,
                    site_id,ptc_code,capacity,mode_pose,structure_type,manufacturer,upstream_cable,city,
                    attributes_json,updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(object_id) DO UPDATE SET
                    layer=excluded.layer,object_type=excluded.object_type,geometry_type=excluded.geometry_type,
                    longitude=excluded.longitude,latitude=excluded.latitude,
                    location=COALESCE(objects.location,excluded.location),source_file=excluded.source_file,
                    attributes_json=excluded.attributes_json,updated_at=excluded.updated_at""",
                (
                    feature_id, layer, object_type, geometry_type, longitude, latitude, location,
                    source.name, "缺失影像", _first(properties, "site_id", "SITE_ID"),
                    _first(properties, "ptc_code", "CODE_PTC", "PTC_CODE"),
                    _first(properties, "capacity", "CAPACITE"), _first(properties, "mode_pose", "MODE_POSE"),
                    _first(properties, "structure_type", "TYPE_STRUC"), _first(properties, "manufacturer", "FABRIQUANT"),
                    _first(properties, "upstream_cable", "CABLE_AMON"), _first(properties, "city", "VILLE"),
                    json.dumps(attributes, ensure_ascii=False), timestamp,
                ),
            )
            conn.execute(
                """INSERT INTO gis_features(feature_id,layer,geometry_type,coordinates_json,status,properties_json)
                   VALUES (?,?,?,?,?,?)
                   ON CONFLICT(feature_id,layer) DO UPDATE SET geometry_type=excluded.geometry_type,
                   coordinates_json=excluded.coordinates_json,status=excluded.status,
                   properties_json=excluded.properties_json""",
                (
                    feature_id, layer, geometry_type, json.dumps(coordinates, ensure_ascii=False),
                    "设计图层", json.dumps(properties, ensure_ascii=False),
                ),
            )
            imported_count += 1

        _sync_engineering_objects(conn)
        _ensure_verification_results(conn)
        conn.execute(
            """INSERT INTO gis_import_meta(source_path,source_sha256,feature_count,imported_at)
               VALUES (?,?,?,?)
               ON CONFLICT(source_path) DO UPDATE SET source_sha256=excluded.source_sha256,
               feature_count=excluded.feature_count,imported_at=excluded.imported_at""",
            (source_key, digest, len(features), timestamp),
        )
        return {
            "status": "imported",
            "source_path": source_key,
            "feature_count": len(features),
            "imported_count": imported_count,
            "changed": True,
        }


def import_status() -> dict[str, Any]:
    source = _source_path()
    with db() as conn:
        meta = conn.execute(
            "SELECT source_sha256,feature_count,imported_at FROM gis_import_meta WHERE source_path=?",
            (str(source),),
        ).fetchone()
        object_count = conn.execute("SELECT COUNT(*) AS n FROM objects").fetchone()["n"]
        feature_count = conn.execute("SELECT COUNT(*) AS n FROM gis_features").fetchone()["n"]
    return {
        "source_path": str(source),
        "source_exists": source.exists(),
        "imported": dict(meta) if meta else None,
        "object_count": object_count,
        "feature_count": feature_count,
    }
