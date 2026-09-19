from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from time import perf_counter
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection

from .calculation import (
    ALGO_VERSION,
    DEFAULT_EPSILON,
    DEFAULT_MAX_ITERATIONS,
    DEFAULT_MOLAR_VOLUME,
    CalculationResult,
    SteadyInput,
    calculate_steady_state,
    decimal_strings,
    from_internal,
)
from .errors import BusinessError
from .schemas import SchemePayload


SCHEME_SELECT = """
SELECT s.*, i.c0, i.g, i.eta_mau, i.cov_mau, i.eta_ceil, i.cov_ceil,
       i.eta_aru, i.cov_aru, i.alpha, i.beta
FROM scheme s
JOIN scheme_input i ON i.scheme_id=s.id
WHERE s.id=:id AND s.status <> 'deleted'
"""


def get_scheme_bundle(connection: Connection, scheme_id: int) -> dict[str, Any]:
    row = connection.execute(text(SCHEME_SELECT), {"id": scheme_id}).mappings().first()
    if row is None:
        raise BusinessError(1004, "方案不存在", status_code=404)
    return dict(row)


def scheme_to_api(row: dict[str, Any]) -> dict[str, Any]:
    unit = "ug" if row["conc_unit"] == "ugm3" else row["conc_unit"]
    return {
        "id": row["id"],
        "cleanroomId": row["cleanroom_id"],
        "name": row["name"],
        "version": row["version"],
        "sourceSchemeId": row.get("source_scheme_id"),
        "concUnit": unit,
        "molarMassM": _number(row.get("molar_mass_m")),
        "molarVolumeVm": _number(row["molar_volume_vm"]),
        "stdSource": row["std_source"],
        "stdPollutantId": row.get("std_pollutant_id"),
        "stdLibraryId": row.get("std_library_id"),
        "targetValue": _number(row.get("target_value")),
        "input": {
            "c0": _number(row["c0"]),
            "g": _number(row["g"]),
            "etaMau": _number(row["eta_mau"]),
            "covMau": _number(row["cov_mau"]),
            "etaCeil": _number(row["eta_ceil"]),
            "covCeil": _number(row["cov_ceil"]),
            "etaAru": _number(row["eta_aru"]),
            "covAru": _number(row["cov_aru"]),
            "alpha": _number(row["alpha"]),
            "beta": _number(row["beta"]),
        },
        "deleted": row["status"] == "deleted",
    }


def list_schemes(connection: Connection, cleanroom_id: int) -> list[dict[str, Any]]:
    rows = connection.execute(
        text(SCHEME_SELECT.replace("WHERE s.id=:id", "WHERE s.cleanroom_id=:id") + " ORDER BY s.updated_at DESC"),
        {"id": cleanroom_id},
    ).mappings()
    return [scheme_to_api(dict(row)) for row in rows]


def create_scheme(connection: Connection, payload: SchemePayload, user_id: int) -> dict[str, Any]:
    values = _scheme_values(payload)
    values["created_by"] = user_id
    result = connection.execute(text("""
        INSERT INTO scheme (
          cleanroom_id, name, version, conc_unit, molar_mass_m, molar_volume_vm,
          std_source, std_pollutant_id, std_library_id, target_value, status, created_by
        ) VALUES (
          :cleanroom_id, :name, 1, :conc_unit, :molar_mass_m, :molar_volume_vm,
          :std_source, :std_pollutant_id, :std_library_id, :target_value, 'saved', :created_by
        )
    """), values)
    scheme_id = int(result.lastrowid)
    _insert_scheme_input(connection, scheme_id, payload)
    return scheme_to_api(get_scheme_bundle(connection, scheme_id))


def update_scheme(connection: Connection, scheme_id: int, payload: SchemePayload) -> dict[str, Any]:
    get_scheme_bundle(connection, scheme_id)
    values = _scheme_values(payload)
    values["id"] = scheme_id
    connection.execute(text("""
        UPDATE scheme SET cleanroom_id=:cleanroom_id, name=:name, conc_unit=:conc_unit,
          molar_mass_m=:molar_mass_m, molar_volume_vm=:molar_volume_vm,
          std_source=:std_source, std_pollutant_id=:std_pollutant_id,
          std_library_id=:std_library_id, target_value=:target_value, status='saved'
        WHERE id=:id AND status <> 'deleted'
    """), values)
    input_values = _input_values(payload)
    input_values["scheme_id"] = scheme_id
    connection.execute(text("""
        UPDATE scheme_input SET c0=:c0, g=:g, eta_mau=:eta_mau, cov_mau=:cov_mau,
          eta_ceil=:eta_ceil, cov_ceil=:cov_ceil, eta_aru=:eta_aru, cov_aru=:cov_aru,
          alpha=:alpha, beta=:beta WHERE scheme_id=:scheme_id
    """), input_values)
    return scheme_to_api(get_scheme_bundle(connection, scheme_id))


def copy_scheme(connection: Connection, scheme_id: int, user_id: int) -> dict[str, Any]:
    source = get_scheme_bundle(connection, scheme_id)
    result = connection.execute(text("""
        INSERT INTO scheme (
          cleanroom_id, name, version, source_scheme_id, conc_unit, molar_mass_m,
          molar_volume_vm, std_source, std_pollutant_id, std_library_id,
          target_value, status, created_by
        ) VALUES (
          :cleanroom_id, :name, :version, :source_id, :conc_unit, :molar_mass_m,
          :molar_volume_vm, :std_source, :std_pollutant_id, :std_library_id,
          :target_value, 'saved', :created_by
        )
    """), {
        **source,
        "name": f"{source['name']}（副本）",
        "version": int(source["version"]) + 1,
        "source_id": scheme_id,
        "created_by": user_id,
    })
    new_id = int(result.lastrowid)
    connection.execute(text("""
        INSERT INTO scheme_input (
          scheme_id, c0, g, eta_mau, cov_mau, eta_ceil, cov_ceil,
          eta_aru, cov_aru, alpha, beta
        ) VALUES (
          :new_id, :c0, :g, :eta_mau, :cov_mau, :eta_ceil, :cov_ceil,
          :eta_aru, :cov_aru, :alpha, :beta
        )
    """), {**source, "new_id": new_id})
    return scheme_to_api(get_scheme_bundle(connection, new_id))


def calculate_and_store(
    connection: Connection,
    scheme_id: int,
    user: dict[str, Any],
    request_id: str,
) -> dict[str, Any]:
    scheme = get_scheme_bundle(connection, scheme_id)
    epsilon, max_iterations, default_vm = _calculation_settings(connection)
    started = perf_counter()
    model = SteadyInput(
        c0=scheme["c0"], g=scheme["g"], eta_mau=scheme["eta_mau"], cov_mau=scheme["cov_mau"],
        eta_ceil=scheme["eta_ceil"], cov_ceil=scheme["cov_ceil"], eta_aru=scheme["eta_aru"],
        cov_aru=scheme["cov_aru"], alpha=scheme["alpha"], beta=scheme["beta"],
        conc_unit=scheme["conc_unit"], molar_mass_m=scheme["molar_mass_m"],
        molar_volume_vm=scheme["molar_volume_vm"] or default_vm,
        target_value=scheme["target_value"], epsilon=epsilon, max_iterations=max_iterations,
    )
    calculated = calculate_steady_state(model)
    calculation_ms = max(0, round((perf_counter() - started) * 1000))

    snapshot_values = {
        "scheme_id": scheme_id, "conc_unit": scheme["conc_unit"],
        "c0_original": model.c0, "g_original": model.g,
        "c0_internal": calculated.nodes_internal["c0"],
        "g_internal": model.g if model.conc_unit == "ugm3" else model.g * model.molar_mass_m / model.molar_volume_vm,
        "eta_mau": model.eta_mau, "cov_mau": model.cov_mau,
        "eta_ceil": model.eta_ceil, "cov_ceil": model.cov_ceil,
        "eta_aru": model.eta_aru, "cov_aru": model.cov_aru,
        "alpha": model.alpha, "beta": model.beta,
        "molar_mass_m": model.molar_mass_m, "molar_volume_vm": model.molar_volume_vm,
        "epsilon": model.epsilon, "max_iterations": model.max_iterations,
        "std_source": scheme["std_source"], "std_pollutant_id": scheme["std_pollutant_id"],
        "std_library_id": scheme["std_library_id"], "target_value": model.target_value,
        "input_full_precision": json.dumps({
            "c0Original": str(model.c0), "gOriginal": str(model.g),
            "c0Internal": str(calculated.nodes_internal["c0"]),
            "gInternal": str(model.g if model.conc_unit == "ugm3" else model.g * model.molar_mass_m / model.molar_volume_vm),
            "etaMau": str(model.eta_mau), "covMau": str(model.cov_mau),
            "etaCeil": str(model.eta_ceil), "covCeil": str(model.cov_ceil),
            "etaAru": str(model.eta_aru), "covAru": str(model.cov_aru),
            "alpha": str(model.alpha), "beta": str(model.beta),
            "molarMassM": None if model.molar_mass_m is None else str(model.molar_mass_m),
            "molarVolumeVm": str(model.molar_volume_vm), "epsilon": str(model.epsilon),
            "maxIterations": model.max_iterations,
            "targetValue": None if model.target_value is None else str(model.target_value),
        }, ensure_ascii=False),
        "created_by": user["id"],
    }
    snapshot = connection.execute(text("""
        INSERT INTO calc_input_snapshot (
          scheme_id, conc_unit, c0_original, g_original, c0_internal, g_internal,
          eta_mau, cov_mau, eta_ceil, cov_ceil, eta_aru, cov_aru, alpha, beta,
          molar_mass_m, molar_volume_vm, epsilon, max_iterations, std_source,
          std_pollutant_id, std_library_id, target_value, input_full_precision, created_by
        ) VALUES (
          :scheme_id, :conc_unit, :c0_original, :g_original, :c0_internal, :g_internal,
          :eta_mau, :cov_mau, :eta_ceil, :cov_ceil, :eta_aru, :cov_aru, :alpha, :beta,
          :molar_mass_m, :molar_volume_vm, :epsilon, :max_iterations, :std_source,
          :std_pollutant_id, :std_library_id, :target_value, :input_full_precision, :created_by
        )
    """), snapshot_values)
    snapshot_id = int(snapshot.lastrowid)
    standard = _standard_snapshot(connection, scheme, calculated)
    nodes = calculated.nodes_internal
    result = connection.execute(text("""
        INSERT INTO calc_result (
          scheme_id, input_snapshot_id, c0, c1, c_return, cmix, cout2, cr,
          result_full_precision, conclusion, std_source_snapshot, std_name_snapshot,
          std_version_snapshot, std_value_snapshot, algo_version, converged, iter_count,
          error_code, error_message, calculation_ms, request_id, created_by
        ) VALUES (
          :scheme_id, :snapshot_id, :c0, :c1, :c_return, :cmix, :cout2, :cr,
          :full_precision, :conclusion, :std_source, :std_name, :std_version,
          :std_value, :algo_version, :converged, :iter_count, :error_code,
          :error_message, :calculation_ms, :request_id, :created_by
        )
    """), {
        "scheme_id": scheme_id, "snapshot_id": snapshot_id, "c0": nodes["c0"],
        "c1": nodes["c1"], "c_return": nodes["cReturn"], "cmix": nodes["cmix"],
        "cout2": nodes["cout2"], "cr": nodes["cr"],
        "full_precision": json.dumps(decimal_strings(nodes), ensure_ascii=False),
        "conclusion": calculated.conclusion, "std_source": scheme["std_source"],
        "std_name": standard["name"], "std_version": standard["version"],
        "std_value": calculated.target_internal, "algo_version": ALGO_VERSION,
        "converged": calculated.converged, "iter_count": calculated.iter_count,
        "error_code": calculated.error_code, "error_message": calculated.error_message,
        "calculation_ms": calculation_ms, "request_id": request_id, "created_by": user["id"],
    })
    result_id = int(result.lastrowid)
    connection.execute(text("""
        INSERT INTO calc_iter (
          calc_result_id, iter_no, cr_old, c1, c_return, cmix, cout2, cr_new,
          delta_value, iteration_full_precision
        ) VALUES (
          :calc_result_id, :iter_no, :cr_old, :c1, :c_return, :cmix, :cout2,
          :cr_new, :delta_value, :iteration_full_precision
        )
    """), [
        {
            "calc_result_id": result_id, "iter_no": row.iter_no, "cr_old": row.cr_old,
            "c1": row.c1, "c_return": row.c_return, "cmix": row.cmix, "cout2": row.cout2,
            "cr_new": row.cr_new, "delta_value": row.delta,
            "iteration_full_precision": json.dumps({
                "crOld": str(row.cr_old), "c1": str(row.c1), "cReturn": str(row.c_return),
                "cmix": str(row.cmix), "cout2": str(row.cout2), "crNew": str(row.cr_new),
                "delta": str(row.delta),
            }, ensure_ascii=False),
        }
        for row in calculated.iterations_internal
    ])
    _audit(connection, user, "calculate", "scheme", scheme_id, scheme["name"], request_id)
    return result_to_api(result_id, scheme_id, calculated, calculation_ms, user["real_name"] or user["username"])


def result_to_api(
    result_id: int,
    scheme_id: int,
    result: CalculationResult,
    calculation_ms: int,
    created_by: str,
) -> dict[str, Any]:
    return {
        "id": result_id, "schemeId": scheme_id, "converged": result.converged,
        "iterCount": result.iter_count, "algoVersion": result.algo_version,
        "nodes": {key: _number(value) for key, value in result.nodes.items()},
        "unit": result.unit, "conclusion": result.conclusion,
        "targetValue": _number(result.target_value),
        "iterations": [
            {
                "iterNo": row.iter_no, "crOld": _number(row.cr_old), "c1": _number(row.c1),
                "cReturn": _number(row.c_return), "cmix": _number(row.cmix),
                "cout2": _number(row.cout2), "crNew": _number(row.cr_new),
                "delta": _number(row.delta),
            }
            for row in result.iterations
        ],
        "epsilon": _number(result.epsilon), "calculationMs": calculation_ms,
        "errorCode": result.error_code, "errorMessage": result.error_message,
        "createdBy": created_by, "calcTime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def get_latest_result(connection: Connection, scheme_id: int) -> dict[str, Any]:
    scheme = get_scheme_bundle(connection, scheme_id)
    row = connection.execute(text("""
        SELECT r.*, x.conc_unit, x.molar_mass_m, x.molar_volume_vm, x.target_value,
               u.real_name, u.username
        FROM calc_result r
        JOIN calc_input_snapshot x ON x.id=r.input_snapshot_id
        JOIN sys_user u ON u.id=r.created_by
        WHERE r.scheme_id=:scheme_id ORDER BY r.calc_time DESC, r.id DESC LIMIT 1
    """), {"scheme_id": scheme_id}).mappings().first()
    if row is None:
        raise BusinessError(1004, "该方案尚无计算结果", status_code=404)
    return _stored_result_to_api(connection, dict(row), scheme)


def list_results(connection: Connection, scheme_id: int) -> list[dict[str, Any]]:
    scheme = get_scheme_bundle(connection, scheme_id)
    rows = connection.execute(text("""
        SELECT r.*, x.conc_unit, x.molar_mass_m, x.molar_volume_vm, x.target_value,
               u.real_name, u.username
        FROM calc_result r
        JOIN calc_input_snapshot x ON x.id=r.input_snapshot_id
        JOIN sys_user u ON u.id=r.created_by
        WHERE r.scheme_id=:scheme_id ORDER BY r.calc_time DESC, r.id DESC
    """), {"scheme_id": scheme_id}).mappings()
    return [_stored_result_to_api(connection, dict(row), scheme, include_iterations=False) for row in rows]


def _stored_result_to_api(
    connection: Connection,
    row: dict[str, Any],
    scheme: dict[str, Any],
    *,
    include_iterations: bool = True,
) -> dict[str, Any]:
    model = SteadyInput(
        c0=scheme["c0"], g=scheme["g"], eta_mau=scheme["eta_mau"], cov_mau=scheme["cov_mau"],
        eta_ceil=scheme["eta_ceil"], cov_ceil=scheme["cov_ceil"], eta_aru=scheme["eta_aru"],
        cov_aru=scheme["cov_aru"], alpha=scheme["alpha"], beta=scheme["beta"],
        conc_unit=row["conc_unit"], molar_mass_m=row["molar_mass_m"], molar_volume_vm=row["molar_volume_vm"],
        target_value=row["target_value"],
    )
    exact = _json_object(row["result_full_precision"])
    internal = {key: Decimal(str(exact.get(key, row[_db_node(key)]))) for key in ("c0", "c1", "cReturn", "cmix", "cout2", "cr")}
    nodes = {key: _number(from_internal(value, model)) for key, value in internal.items()}
    iterations: list[dict[str, Any]] = []
    if include_iterations:
        iter_rows = connection.execute(text("""
            SELECT * FROM calc_iter WHERE calc_result_id=:id ORDER BY iter_no
        """), {"id": row["id"]}).mappings()
        for item in iter_rows:
            stored = _json_object(item["iteration_full_precision"])
            iterations.append({
                "iterNo": item["iter_no"],
                **{key: _number(from_internal(Decimal(str(stored[key])), model)) for key in ("crOld", "c1", "cReturn", "cmix", "cout2", "crNew", "delta")},
            })
    return {
        "id": row["id"], "schemeId": row["scheme_id"], "converged": bool(row["converged"]),
        "iterCount": row["iter_count"], "algoVersion": row["algo_version"], "nodes": nodes,
        "unit": "ug" if row["conc_unit"] == "ugm3" else row["conc_unit"],
        "conclusion": row["conclusion"], "targetValue": _number(row["target_value"]),
        "iterations": iterations, "calculationMs": row["calculation_ms"],
        "errorCode": row["error_code"], "errorMessage": row["error_message"],
        "createdBy": row["real_name"] or row["username"],
        "calcTime": row["calc_time"].strftime("%Y-%m-%d %H:%M:%S"),
    }


def _scheme_values(payload: SchemePayload) -> dict[str, Any]:
    return {
        "cleanroom_id": payload.cleanroom_id, "name": payload.name, "conc_unit": payload.conc_unit,
        "molar_mass_m": payload.molar_mass_m, "molar_volume_vm": payload.molar_volume_vm,
        "std_source": payload.std_source, "std_pollutant_id": payload.std_pollutant_id,
        "std_library_id": payload.std_library_id, "target_value": payload.target_value,
    }


def _input_values(payload: SchemePayload) -> dict[str, Any]:
    return payload.input.model_dump(by_alias=False)


def _insert_scheme_input(connection: Connection, scheme_id: int, payload: SchemePayload) -> None:
    connection.execute(text("""
        INSERT INTO scheme_input (
          scheme_id, c0, g, eta_mau, cov_mau, eta_ceil, cov_ceil, eta_aru, cov_aru, alpha, beta
        ) VALUES (
          :scheme_id, :c0, :g, :eta_mau, :cov_mau, :eta_ceil, :cov_ceil, :eta_aru, :cov_aru, :alpha, :beta
        )
    """), {**_input_values(payload), "scheme_id": scheme_id})


def _calculation_settings(connection: Connection) -> tuple[Decimal, int, Decimal]:
    rows = connection.execute(text("""
        SELECT config_key, config_value FROM system_config
        WHERE status='active' AND config_key IN (
          'calculation.epsilon', 'calculation.max_iterations', 'conversion.molar_volume_vm'
        )
    """)).mappings()
    values = {row["config_key"]: row["config_value"] for row in rows}
    return (
        Decimal(values.get("calculation.epsilon", str(DEFAULT_EPSILON))),
        int(values.get("calculation.max_iterations", DEFAULT_MAX_ITERATIONS)),
        Decimal(values.get("conversion.molar_volume_vm", str(DEFAULT_MOLAR_VOLUME))),
    )


def _standard_snapshot(connection: Connection, scheme: dict[str, Any], result: CalculationResult) -> dict[str, Any]:
    if scheme["std_library_id"] is None:
        return {"name": "手工输入" if scheme["target_value"] is not None else None, "version": None}
    row = connection.execute(text("SELECT std_name, version FROM std_library WHERE id=:id"), {"id": scheme["std_library_id"]}).mappings().first()
    return {"name": row["std_name"] if row else None, "version": row["version"] if row else None}


def _audit(connection: Connection, user: dict[str, Any], action: str, target_type: str, target_id: int, target: str, request_id: str) -> None:
    connection.execute(text("""
        INSERT INTO operation_log (
          user_id, username_snapshot, action, target_type, target_id, target, request_id, result_status
        ) VALUES (:user_id, :username, :action, :target_type, :target_id, :target, :request_id, 'success')
    """), {
        "user_id": user["id"], "username": user["username"], "action": action,
        "target_type": target_type, "target_id": target_id, "target": target, "request_id": request_id,
    })


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    return json.loads(value)


def _db_node(key: str) -> str:
    return {"cReturn": "c_return"}.get(key, key)


def _number(value: Any) -> float | int | None:
    if value is None:
        return None
    number = Decimal(str(value))
    return int(number) if number == number.to_integral_value() else float(number)
