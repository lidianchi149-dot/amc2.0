from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection

from .errors import BusinessError


RESOURCE_CONFIG = {
    "customers": {
        "table": "customer",
        "fields": ("name", "contact", "phone", "remark"),
        "aliases": {},
        "parent": None,
    },
    "projects": {
        "table": "project",
        "fields": ("customer_id", "name", "location", "remark"),
        "aliases": {"customer_id": "customerId"},
        "parent": "customer_id",
    },
    "cleanrooms": {
        "table": "cleanroom",
        "fields": ("project_id", "name", "code", "remark"),
        "aliases": {"project_id": "projectId"},
        "parent": "project_id",
    },
}


def list_resources(connection: Connection, resource: str, parent_id: int | None = None) -> list[dict[str, Any]]:
    config = RESOURCE_CONFIG[resource]
    where = "status <> 'deleted'"
    params: dict[str, Any] = {}
    if parent_id is not None and config["parent"]:
        where += f" AND {config['parent']}=:parent_id"
        params["parent_id"] = parent_id
    rows = connection.execute(
        text(f"SELECT * FROM {config['table']} WHERE {where} ORDER BY updated_at DESC, id DESC"), params
    ).mappings()
    return [_resource_to_api(dict(row), config) for row in rows]


def get_resource(connection: Connection, resource: str, item_id: int) -> dict[str, Any]:
    config = RESOURCE_CONFIG[resource]
    row = connection.execute(
        text(f"SELECT * FROM {config['table']} WHERE id=:id AND status <> 'deleted'"), {"id": item_id}
    ).mappings().first()
    if row is None:
        raise BusinessError(1004, "资源不存在", status_code=404)
    return _resource_to_api(dict(row), config)


def create_resource(connection: Connection, resource: str, values: dict[str, Any], user_id: int) -> dict[str, Any]:
    config = RESOURCE_CONFIG[resource]
    fields = config["fields"]
    sql_fields = ", ".join((*fields, "created_by"))
    placeholders = ", ".join(f":{field}" for field in (*fields, "created_by"))
    result = connection.execute(
        text(f"INSERT INTO {config['table']} ({sql_fields}) VALUES ({placeholders})"),
        {**{field: values.get(field) for field in fields}, "created_by": user_id},
    )
    return get_resource(connection, resource, int(result.lastrowid))


def update_resource(connection: Connection, resource: str, item_id: int, values: dict[str, Any]) -> dict[str, Any]:
    config = RESOURCE_CONFIG[resource]
    get_resource(connection, resource, item_id)
    assignments = ", ".join(f"{field}=:{field}" for field in config["fields"])
    connection.execute(
        text(f"UPDATE {config['table']} SET {assignments} WHERE id=:id AND status <> 'deleted'"),
        {**{field: values.get(field) for field in config["fields"]}, "id": item_id},
    )
    return get_resource(connection, resource, item_id)


def delete_resource(connection: Connection, resource: str, item_id: int) -> None:
    config = RESOURCE_CONFIG[resource]
    result = connection.execute(
        text(f"UPDATE {config['table']} SET status='deleted' WHERE id=:id AND status <> 'deleted'"),
        {"id": item_id},
    )
    if result.rowcount == 0:
        raise BusinessError(1004, "资源不存在", status_code=404)


def list_pollutants(connection: Connection, keyword: str | None) -> list[dict[str, Any]]:
    where = "status='active'"
    params: dict[str, Any] = {}
    if keyword:
        where += " AND (name_cn LIKE :keyword OR name_en LIKE :keyword OR cas_no LIKE :keyword)"
        params["keyword"] = f"%{keyword}%"
    rows = connection.execute(text(f"SELECT * FROM pollutant WHERE {where} ORDER BY name_cn"), params).mappings()
    return [{
        "id": row["id"], "name": row["name_cn"], "nameCn": row["name_cn"],
        "nameEn": row["name_en"], "formula": row["formula"], "cas": row["cas_no"],
        "casNo": row["cas_no"], "boilingPoint": _number(row["boiling_point"]),
        "molecularFormula": row["molecular_formula"],
        "molarMassM": _number(row["molar_mass"]), "aliases": _json_list(row["aliases"]),
    } for row in rows]


def list_standards(connection: Connection, pollutant_id: int | None, source_type: str | None) -> list[dict[str, Any]]:
    where = ["effective=1"]
    params: dict[str, Any] = {}
    if pollutant_id is not None:
        where.append("pollutant_id=:pollutant_id")
        params["pollutant_id"] = pollutant_id
    if source_type:
        where.append("source_type=:source_type")
        params["source_type"] = source_type
    rows = connection.execute(text(
        "SELECT * FROM std_library WHERE " + " AND ".join(where) + " ORDER BY priority DESC, id DESC"
    ), params).mappings()
    return [{
        "id": row["id"], "pollutantId": row["pollutant_id"], "customerId": row["customer_id"],
        "sourceType": row["source_type"], "name": row["std_name"],
        "targetValue": _number(row["std_value"]), "unit": "ug" if row["unit"] == "ugm3" else row["unit"],
        "scope": row["scope"], "priority": row["priority"], "version": row["version"],
    } for row in rows]


def _resource_to_api(row: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    result = {"id": row["id"], "deleted": row["status"] == "deleted"}
    for field in config["fields"]:
        result[config["aliases"].get(field, field)] = row[field]
    return result


def _number(value: Any) -> float | None:
    return None if value is None else float(value)


def _json_list(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    parsed = json.loads(value)
    return parsed if isinstance(parsed, list) else []
