import os
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.database import build_engine
from app.repository import calculate_and_store, create_scheme, get_latest_result
from app.schemas import SchemePayload


pytestmark = pytest.mark.skipif(
    os.getenv("AMC_INTEGRATION_TEST") != "1",
    reason="set AMC_INTEGRATION_TEST=1 to run against a disposable/rollback-safe MySQL connection",
)


def test_calculation_transaction_matches_schema() -> None:
    engine = build_engine()
    connection = engine.connect()
    transaction = connection.begin()
    try:
        user_id = int(connection.execute(text("""
            INSERT INTO sys_user (username, password_hash, real_name, role)
            VALUES ('integration_test_user', 'not-used-in-test', '集成测试', 'engineer')
        """)).lastrowid)
        customer_id = int(connection.execute(text("""
            INSERT INTO customer (name, status, created_by)
            VALUES ('集成测试客户', 'active', :user_id)
        """), {"user_id": user_id}).lastrowid)
        project_id = int(connection.execute(text("""
            INSERT INTO project (customer_id, name, status, created_by)
            VALUES (:customer_id, '集成测试项目', 'active', :user_id)
        """), {"customer_id": customer_id, "user_id": user_id}).lastrowid)
        cleanroom_id = int(connection.execute(text("""
            INSERT INTO cleanroom (project_id, name, status, created_by)
            VALUES (:project_id, '集成测试洁净室', 'active', :user_id)
        """), {"project_id": project_id, "user_id": user_id}).lastrowid)

        scheme = create_scheme(connection, SchemePayload.model_validate({
            "cleanroomId": cleanroom_id,
            "name": "集成测试方案",
            "concUnit": "ug",
            "molarMassM": "30.03",
            "molarVolumeVm": "24.04",
            "stdSource": "manual",
            "targetValue": "3.2",
            "input": {
                "c0": "10", "g": "1.5", "etaMau": "0.72", "covMau": "1",
                "etaCeil": "0.55", "covCeil": "0.92", "etaAru": "0.35",
                "covAru": "0.8", "alpha": "0.3", "beta": "0.7",
            },
        }), user_id)
        user = {"id": user_id, "username": "integration_test_user", "real_name": "集成测试"}
        result = calculate_and_store(connection, scheme["id"], user, "req_integration_test")

        assert result["converged"] is True
        assert result["conclusion"] == "pass"
        assert abs(Decimal(str(result["nodes"]["cr"])) - Decimal("1.1517076603")) < Decimal("1e-9")
        assert connection.execute(
            text("SELECT COUNT(*) FROM calc_iter WHERE calc_result_id=:id"), {"id": result["id"]}
        ).scalar_one() == result["iterCount"]
        restored = get_latest_result(connection, scheme["id"])
        assert restored["id"] == result["id"]
        assert restored["iterations"][-1]["crNew"] == result["iterations"][-1]["crNew"]
    finally:
        transaction.rollback()
        connection.close()
        engine.dispose()
