from __future__ import annotations

from typing import Any

from sqlalchemy import text

from .database import engine
from .repository import calculate_and_store, create_scheme
from .schemas import SchemePayload


BASE_INPUT = {
    "c0": 10, "g": 1.5, "etaMau": 0.72, "covMau": 1,
    "etaCeil": 0.55, "covCeil": 0.92, "etaAru": 0.35,
    "covAru": 0.8, "alpha": 0.3, "beta": 0.7,
}


def restore_baseline(username: str) -> dict[str, Any]:
    """Restore the original web1 baseline hierarchy without duplicating existing rows."""
    created = {"customers": 0, "projects": 0, "cleanrooms": 0, "standards": 0, "schemes": 0, "results": 0}
    restored = {"customers": 0, "projects": 0, "cleanrooms": 0, "schemes": 0}
    with engine.begin() as connection:
        row = connection.execute(text("""
            SELECT id, username, real_name, role FROM sys_user
            WHERE username=:username AND status='active'
        """), {"username": username}).mappings().first()
        if row is None:
            raise ValueError(f"有效用户不存在：{username}")
        user = dict(row)

        customer_1 = _resource(connection, "customer", "name", "华东芯片制造有限公司", {
            "name": "华东芯片制造有限公司", "contact": "李经理", "phone": None,
            "remark": "web1 一期基准档案", "created_by": user["id"],
        }, created, restored, "customers")
        customer_2 = _resource(connection, "customer", "name", "先进材料科技集团", {
            "name": "先进材料科技集团", "contact": "王工", "phone": None,
            "remark": "web1 一期基准档案", "created_by": user["id"],
        }, created, restored, "customers")

        project_1 = _child_resource(connection, "project", "customer_id", customer_1, "12英寸晶圆厂 AMC 改造", {
            "customer_id": customer_1, "name": "12英寸晶圆厂 AMC 改造", "location": "上海",
            "remark": "web1 一期基准档案", "created_by": user["id"],
        }, created, restored, "projects")
        project_2 = _child_resource(connection, "project", "customer_id", customer_2, "研发中心洁净室验证", {
            "customer_id": customer_2, "name": "研发中心洁净室验证", "location": "苏州",
            "remark": "web1 一期基准档案", "created_by": user["id"],
        }, created, restored, "projects")

        room_1 = _cleanroom(connection, project_1, "A栋核心工艺区", "CR-A01", user["id"], created, restored)
        room_2 = _cleanroom(connection, project_1, "A栋辅助区", "CR-A02", user["id"], created, restored)
        _cleanroom(connection, project_2, "研发洁净室", "CR-R01", user["id"], created, restored)

        formaldehyde = _pollutant_id(connection, "50-00-0")
        ammonia = _pollutant_id(connection, "7664-41-7")
        formaldehyde_standard = _standard(
            connection, formaldehyde, "enterprise", "企业 AMC 控制限值", 3.2,
            "核心工艺区", "2026.1", user["id"], created,
        )
        _standard(
            connection, ammonia, "industry", "洁净室 AMC 行业参考限值", 5,
            "洁净室", "2025", user["id"], created,
        )

        schemes = [
            (room_1, "A栋核心区基准方案", 1, formaldehyde_standard, 3.2, BASE_INPUT),
            (room_1, "MAU增强过滤方案", 2, formaldehyde_standard, 3.2, {
                **BASE_INPUT, "etaMau": 0.88, "etaCeil": 0.62,
            }),
            (room_2, "回风优化验证方案", 1, None, 2.5, {
                **BASE_INPUT, "etaAru": 0.55, "covAru": 0.9, "alpha": 0.35, "beta": 0.65,
            }),
        ]
        for cleanroom_id, name, version, standard_id, target, inputs in schemes:
            scheme_id, was_created, was_restored = _scheme(
                connection, cleanroom_id, name, version, formaldehyde,
                standard_id, target, inputs, user["id"],
            )
            created["schemes"] += int(was_created)
            restored["schemes"] += int(was_restored)
            result_count = connection.execute(
                text("SELECT COUNT(1) FROM calc_result WHERE scheme_id=:id"), {"id": scheme_id}
            ).scalar_one()
            if result_count == 0:
                calculate_and_store(connection, scheme_id, user, f"baseline_restore_{scheme_id}")
                created["results"] += 1

        connection.execute(text("""
            INSERT INTO operation_log (
              user_id, username_snapshot, action, target_type, target, detail, result_status
            ) VALUES (
              :user_id, :username, 'restore_baseline', 'system', 'web1 一期基准数据',
              :detail, 'success'
            )
        """), {
            "user_id": user["id"], "username": user["username"],
            "detail": f"created={created}; restored={restored}",
        })
    return {"created": created, "restored": restored}


def _resource(connection, table: str, key: str, value: str, values: dict[str, Any], created, restored, counter: str) -> int:
    row = connection.execute(
        text(f"SELECT id, status FROM {table} WHERE {key}=:value ORDER BY id LIMIT 1"), {"value": value}
    ).mappings().first()
    if row:
        if row["status"] == "deleted":
            connection.execute(text(f"UPDATE {table} SET status='active' WHERE id=:id"), {"id": row["id"]})
            restored[counter] += 1
        return int(row["id"])
    fields = ", ".join(values)
    placeholders = ", ".join(f":{field}" for field in values)
    result = connection.execute(text(f"INSERT INTO {table} ({fields}) VALUES ({placeholders})"), values)
    created[counter] += 1
    return int(result.lastrowid)


def _child_resource(connection, table: str, parent_key: str, parent_id: int, name: str, values, created, restored, counter: str) -> int:
    row = connection.execute(text(f"""
        SELECT id, status FROM {table} WHERE {parent_key}=:parent_id AND name=:name ORDER BY id LIMIT 1
    """), {"parent_id": parent_id, "name": name}).mappings().first()
    if row:
        if row["status"] == "deleted":
            connection.execute(text(f"UPDATE {table} SET status='active' WHERE id=:id"), {"id": row["id"]})
            restored[counter] += 1
        return int(row["id"])
    fields = ", ".join(values)
    placeholders = ", ".join(f":{field}" for field in values)
    result = connection.execute(text(f"INSERT INTO {table} ({fields}) VALUES ({placeholders})"), values)
    created[counter] += 1
    return int(result.lastrowid)


def _cleanroom(connection, project_id: int, name: str, code: str, user_id: int, created, restored) -> int:
    return _child_resource(connection, "cleanroom", "project_id", project_id, name, {
        "project_id": project_id, "name": name, "code": code,
        "remark": "web1 一期基准档案", "created_by": user_id,
    }, created, restored, "cleanrooms")


def _pollutant_id(connection, cas_no: str) -> int:
    pollutant_id = connection.execute(
        text("SELECT id FROM pollutant WHERE cas_no=:cas_no AND status='active'"), {"cas_no": cas_no}
    ).scalar_one_or_none()
    if pollutant_id is None:
        raise ValueError(f"污染物库缺少 CAS {cas_no}，请先执行 import-pollutants")
    return int(pollutant_id)


def _standard(connection, pollutant_id: int, source_type: str, name: str, value: float, scope: str, version: str, user_id: int, created) -> int:
    standard_id = connection.execute(text("""
        SELECT id FROM std_library
        WHERE pollutant_id=:pollutant_id AND source_type=:source_type
          AND std_name=:name AND version=:version
        ORDER BY id LIMIT 1
    """), {
        "pollutant_id": pollutant_id, "source_type": source_type,
        "name": name, "version": version,
    }).scalar_one_or_none()
    if standard_id is not None:
        return int(standard_id)
    result = connection.execute(text("""
        INSERT INTO std_library (
          pollutant_id, source_type, std_name, std_value, unit, scope,
          priority, version, effective, created_by
        ) VALUES (
          :pollutant_id, :source_type, :name, :value, 'ugm3', :scope,
          10, :version, 1, :created_by
        )
    """), {
        "pollutant_id": pollutant_id, "source_type": source_type, "name": name,
        "value": value, "scope": scope, "version": version, "created_by": user_id,
    })
    created["standards"] += 1
    return int(result.lastrowid)


def _scheme(connection, cleanroom_id: int, name: str, version: int, pollutant_id: int, standard_id: int | None, target: float, inputs: dict[str, Any], user_id: int) -> tuple[int, bool, bool]:
    row = connection.execute(text("""
        SELECT id, status FROM scheme WHERE cleanroom_id=:cleanroom_id AND name=:name
        ORDER BY id LIMIT 1
    """), {"cleanroom_id": cleanroom_id, "name": name}).mappings().first()
    if row:
        restored = row["status"] == "deleted"
        if restored:
            connection.execute(text("UPDATE scheme SET status='saved' WHERE id=:id"), {"id": row["id"]})
        return int(row["id"]), False, restored
    payload = SchemePayload.model_validate({
        "cleanroomId": cleanroom_id, "name": name, "concUnit": "ug",
        "molarMassM": 30.03, "molarVolumeVm": 24.04,
        "stdSource": "enterprise" if standard_id else "manual",
        "stdPollutantId": pollutant_id, "stdLibraryId": standard_id,
        "targetValue": target, "input": inputs,
    })
    scheme = create_scheme(connection, payload, user_id)
    if version != 1:
        connection.execute(text("UPDATE scheme SET version=:version WHERE id=:id"), {
            "version": version, "id": scheme["id"],
        })
    return int(scheme["id"]), True, False
