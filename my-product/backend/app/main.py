from __future__ import annotations

import logging
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from typing import Any
from uuid import uuid4

from fastapi import Depends, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.engine import Connection

from .catalog import (
    create_resource, delete_resource, get_resource, list_pollutants,
    list_resources, list_standards, update_resource,
)
from .config import get_settings
from .database import engine, get_connection
from .errors import BusinessError
from .importers import import_pollutants
from .repository import (
    calculate_and_store, copy_scheme, create_scheme, get_latest_result,
    get_scheme_bundle, list_results, list_schemes, scheme_to_api, update_scheme,
)
from .schemas import (
    CleanroomPayload, CompareRequest, CustomerPayload, LoginRequest,
    ProjectPayload, SchemePayload,
)
from .security import create_access_token, current_user, require_roles, verify_password


logger = logging.getLogger("amc.backend")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
settings = get_settings()
app = FastAPI(title=settings.app_name, version="1.0.0", docs_url="/docs", openapi_url="/openapi.json")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
business_writer = require_roles("admin", "engineer", "sales")


def envelope(request: Request, data: Any = None, message: str = "success", code: int = 0) -> dict[str, Any]:
    return {"code": code, "message": message, "data": data, "requestId": request.state.request_id}


@app.middleware("http")
async def request_context(request: Request, call_next):
    request.state.request_id = request.headers.get("X-Request-Id") or f"req_{uuid4().hex}"
    started = perf_counter()
    response = await call_next(request)
    response.headers["X-Request-Id"] = request.state.request_id
    logger.info(
        "requestId=%s method=%s path=%s status=%s durationMs=%s",
        request.state.request_id, request.method, request.url.path,
        response.status_code, round((perf_counter() - started) * 1000),
    )
    return response


@app.exception_handler(BusinessError)
async def business_error_handler(request: Request, exc: BusinessError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=envelope(request, exc.data, exc.message, exc.code),
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    fields = [
        {"field": ".".join(str(item) for item in error["loc"] if item != "body"), "message": error["msg"]}
        for error in exc.errors()
    ]
    return JSONResponse(status_code=422, content=envelope(request, {"fields": fields}, "参数校验失败", 1001))


@app.exception_handler(IntegrityError)
async def integrity_error_handler(request: Request, exc: IntegrityError) -> JSONResponse:
    logger.warning("requestId=%s database integrity error", request.state.request_id, exc_info=exc)
    return JSONResponse(status_code=409, content=envelope(request, None, "数据约束冲突", 1001))


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("requestId=%s unhandled error", request.state.request_id, exc_info=exc)
    return JSONResponse(status_code=500, content=envelope(request, None, "服务器内部错误", 5000))


@app.get("/health")
def health(request: Request, connection: Connection = Depends(get_connection)) -> dict[str, Any]:
    connection.execute(text("SELECT 1"))
    return envelope(request, {"status": "up", "database": "up", "algorithmVersion": "steady-v1.0"})


@app.post("/api/auth/login")
def login(request: Request, payload: LoginRequest) -> dict[str, Any]:
    user: dict[str, Any] | None = None
    with engine.begin() as connection:
        row = connection.execute(text("""
            SELECT id, username, password_hash, real_name, role, status
            FROM sys_user WHERE username=:username
        """), {"username": payload.username}).mappings().first()
        if row is None or row["status"] != "active" or not verify_password(payload.password, row["password_hash"]):
            connection.execute(text("""
                INSERT INTO operation_log (username_snapshot, action, request_id, ip_address, result_status)
                VALUES (:username, 'login', :request_id, :ip, 'denied')
            """), {
                "username": payload.username, "request_id": request.state.request_id,
                "ip": request.client.host if request.client else None,
            })
        else:
            user = dict(row)
            connection.execute(text("UPDATE sys_user SET last_login_at=NOW() WHERE id=:id"), {"id": user["id"]})
            connection.execute(text("""
                INSERT INTO operation_log (
                  user_id, username_snapshot, action, request_id, ip_address, result_status
                ) VALUES (:id, :username, 'login', :request_id, :ip, 'success')
            """), {
                "id": user["id"], "username": user["username"], "request_id": request.state.request_id,
                "ip": request.client.host if request.client else None,
            })
    if user is None:
        raise BusinessError(1002, "账号或密码错误", status_code=401)
    return envelope(request, {
        "token": create_access_token(user), "userId": user["id"],
        "realName": user["real_name"], "role": user["role"],
    })


@app.post("/api/auth/logout")
def logout(request: Request, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    with engine.begin() as connection:
        _write_audit(connection, user, "logout", request.state.request_id)
    return envelope(request, True)


@app.get("/api/auth/me")
def authenticated_user(request: Request, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    return envelope(request, {
        "userId": user["id"],
        "username": user["username"],
        "realName": user["real_name"],
        "role": user["role"],
    })


@app.get("/api/customers")
def customers(request: Request, connection: Connection = Depends(get_connection)) -> dict[str, Any]:
    return envelope(request, list_resources(connection, "customers"))


@app.post("/api/customers")
def add_customer(request: Request, payload: CustomerPayload, user: dict[str, Any] = Depends(business_writer)):
    with engine.begin() as connection:
        data = create_resource(connection, "customers", payload.model_dump(), user["id"])
        _write_audit(connection, user, "create_customer", request.state.request_id, "customer", data["id"], data["name"])
    return envelope(request, data)


@app.get("/api/customers/{item_id}")
def customer_detail(request: Request, item_id: int, connection: Connection = Depends(get_connection)):
    return envelope(request, get_resource(connection, "customers", item_id))


@app.put("/api/customers/{item_id}")
def edit_customer(request: Request, item_id: int, payload: CustomerPayload, user: dict[str, Any] = Depends(business_writer)):
    with engine.begin() as connection:
        data = update_resource(connection, "customers", item_id, payload.model_dump())
        _write_audit(connection, user, "update_customer", request.state.request_id, "customer", item_id, data["name"])
    return envelope(request, data)


@app.delete("/api/customers/{item_id}")
def remove_customer(request: Request, item_id: int, user: dict[str, Any] = Depends(business_writer)):
    with engine.begin() as connection:
        delete_resource(connection, "customers", item_id)
        _write_audit(connection, user, "delete_customer", request.state.request_id, "customer", item_id)
    return envelope(request, True)


@app.get("/api/projects")
def projects(request: Request, customer_id: int | None = Query(default=None, alias="customerId"), connection: Connection = Depends(get_connection)):
    return envelope(request, list_resources(connection, "projects", customer_id))


@app.post("/api/projects")
def add_project(request: Request, payload: ProjectPayload, user: dict[str, Any] = Depends(business_writer)):
    with engine.begin() as connection:
        data = create_resource(connection, "projects", payload.model_dump(), user["id"])
        _write_audit(connection, user, "create_project", request.state.request_id, "project", data["id"], data["name"])
    return envelope(request, data)


@app.get("/api/projects/{item_id}")
def project_detail(request: Request, item_id: int, connection: Connection = Depends(get_connection)):
    return envelope(request, get_resource(connection, "projects", item_id))


@app.put("/api/projects/{item_id}")
def edit_project(request: Request, item_id: int, payload: ProjectPayload, user: dict[str, Any] = Depends(business_writer)):
    with engine.begin() as connection:
        data = update_resource(connection, "projects", item_id, payload.model_dump(),)
        _write_audit(connection, user, "update_project", request.state.request_id, "project", item_id, data["name"])
    return envelope(request, data)


@app.delete("/api/projects/{item_id}")
def remove_project(request: Request, item_id: int, user: dict[str, Any] = Depends(business_writer)):
    with engine.begin() as connection:
        delete_resource(connection, "projects", item_id)
        _write_audit(connection, user, "delete_project", request.state.request_id, "project", item_id)
    return envelope(request, True)


@app.get("/api/cleanrooms")
def cleanrooms(request: Request, project_id: int | None = Query(default=None, alias="projectId"), connection: Connection = Depends(get_connection)):
    return envelope(request, list_resources(connection, "cleanrooms", project_id))


@app.post("/api/cleanrooms")
def add_cleanroom(request: Request, payload: CleanroomPayload, user: dict[str, Any] = Depends(business_writer)):
    with engine.begin() as connection:
        data = create_resource(connection, "cleanrooms", payload.model_dump(), user["id"])
        _write_audit(connection, user, "create_cleanroom", request.state.request_id, "cleanroom", data["id"], data["name"])
    return envelope(request, data)


@app.get("/api/cleanrooms/{item_id}")
def cleanroom_detail(request: Request, item_id: int, connection: Connection = Depends(get_connection)):
    return envelope(request, get_resource(connection, "cleanrooms", item_id))


@app.put("/api/cleanrooms/{item_id}")
def edit_cleanroom(request: Request, item_id: int, payload: CleanroomPayload, user: dict[str, Any] = Depends(business_writer)):
    with engine.begin() as connection:
        data = update_resource(connection, "cleanrooms", item_id, payload.model_dump())
        _write_audit(connection, user, "update_cleanroom", request.state.request_id, "cleanroom", item_id, data["name"])
    return envelope(request, data)


@app.delete("/api/cleanrooms/{item_id}")
def remove_cleanroom(request: Request, item_id: int, user: dict[str, Any] = Depends(business_writer)):
    with engine.begin() as connection:
        delete_resource(connection, "cleanrooms", item_id)
        _write_audit(connection, user, "delete_cleanroom", request.state.request_id, "cleanroom", item_id)
    return envelope(request, True)


@app.get("/api/cleanrooms/{cleanroom_id}/schemes")
def schemes_by_cleanroom(request: Request, cleanroom_id: int, connection: Connection = Depends(get_connection)):
    return envelope(request, list_schemes(connection, cleanroom_id))


@app.post("/api/schemes")
def add_scheme(request: Request, payload: SchemePayload, user: dict[str, Any] = Depends(business_writer)):
    with engine.begin() as connection:
        data = create_scheme(connection, payload, user["id"])
        _write_audit(connection, user, "create_scheme", request.state.request_id, "scheme", data["id"], data["name"])
    return envelope(request, data)


@app.get("/api/schemes/{scheme_id:int}")
def scheme_detail(request: Request, scheme_id: int, connection: Connection = Depends(get_connection)):
    return envelope(request, scheme_to_api(get_scheme_bundle(connection, scheme_id)))


@app.put("/api/schemes/{scheme_id:int}")
def edit_scheme(request: Request, scheme_id: int, payload: SchemePayload, user: dict[str, Any] = Depends(business_writer)):
    with engine.begin() as connection:
        data = update_scheme(connection, scheme_id, payload)
        _write_audit(connection, user, "update_scheme", request.state.request_id, "scheme", scheme_id, data["name"])
    return envelope(request, data)


@app.delete("/api/schemes/{scheme_id:int}")
def remove_scheme(request: Request, scheme_id: int, user: dict[str, Any] = Depends(business_writer)):
    with engine.begin() as connection:
        result = connection.execute(text("UPDATE scheme SET status='deleted' WHERE id=:id AND status <> 'deleted'"), {"id": scheme_id})
        if result.rowcount == 0:
            raise BusinessError(1004, "方案不存在", status_code=404)
        _write_audit(connection, user, "delete_scheme", request.state.request_id, "scheme", scheme_id)
    return envelope(request, True)


@app.post("/api/schemes/{scheme_id:int}/copy")
def duplicate_scheme(request: Request, scheme_id: int, user: dict[str, Any] = Depends(business_writer)):
    with engine.begin() as connection:
        data = copy_scheme(connection, scheme_id, user["id"])
        _write_audit(connection, user, "copy_scheme", request.state.request_id, "scheme", data["id"], data["name"])
    return envelope(request, data)


@app.post("/api/schemes/{scheme_id:int}/calc")
def calculate_scheme(request: Request, scheme_id: int, user: dict[str, Any] = Depends(business_writer)):
    with engine.begin() as connection:
        data = calculate_and_store(connection, scheme_id, user, request.state.request_id)
    if not data["converged"]:
        return JSONResponse(status_code=422, content=envelope(request, data, data["errorMessage"], 2001))
    return envelope(request, data)


@app.get("/api/schemes/{scheme_id:int}/result")
def latest_result(request: Request, scheme_id: int, connection: Connection = Depends(get_connection)):
    return envelope(request, get_latest_result(connection, scheme_id))


@app.get("/api/schemes/{scheme_id:int}/results")
def result_history(request: Request, scheme_id: int, connection: Connection = Depends(get_connection)):
    return envelope(request, list_results(connection, scheme_id))


@app.post("/api/schemes/compare")
def compare_schemes(request: Request, payload: CompareRequest, user: dict[str, Any] = Depends(current_user)):
    with engine.connect() as connection:
        schemes = [get_scheme_bundle(connection, item) for item in payload.scheme_ids]
        if len({item["cleanroom_id"] for item in schemes}) != 1:
            raise BusinessError(1001, "只能对比同一洁净室的方案", status_code=422)
        results = [get_latest_result(connection, item["id"]) for item in schemes]
    data = [{
        "schemeId": scheme["id"], "name": scheme["name"],
        "input": scheme_to_api(scheme)["input"], "nodes": result["nodes"],
        "cr": result["nodes"]["cr"], "conclusion": result["conclusion"],
    } for scheme, result in zip(schemes, results, strict=True)]
    return envelope(request, {"schemes": data})


@app.get("/api/pollutants")
def pollutants(request: Request, keyword: str | None = None, connection: Connection = Depends(get_connection)):
    return envelope(request, list_pollutants(connection, keyword))


@app.post("/api/pollutants/import")
async def import_pollutant_excel(
    request: Request,
    filename: str = Query(min_length=1, max_length=255),
    user: dict[str, Any] = Depends(require_roles("admin")),
):
    safe_name = Path(filename).name
    if not safe_name.lower().endswith(".xlsx"):
        raise BusinessError(1001, "仅支持 .xlsx 污染物库文件")
    content = await request.body()
    if not content:
        raise BusinessError(1001, "上传文件为空")
    if len(content) > 10 * 1024 * 1024:
        raise BusinessError(1001, "上传文件不能超过 10 MB")
    if not content.startswith(b"PK"):
        raise BusinessError(1001, "文件不是有效的 XLSX 格式")
    try:
        with TemporaryDirectory(prefix="amc_pollutant_") as temp_dir:
            temp_file = Path(temp_dir) / "pollutants.xlsx"
            temp_file.write_bytes(content)
            data = import_pollutants(temp_file, user["username"], file_name=safe_name)
    except (ValueError, FileNotFoundError) as exc:
        raise BusinessError(1001, str(exc)) from exc
    return envelope(request, data, "污染物库导入成功")


@app.get("/api/standards")
def standards(
    request: Request,
    pollutant_id: int | None = Query(default=None, alias="pollutantId"),
    source_type: str | None = Query(default=None, alias="sourceType"),
    connection: Connection = Depends(get_connection),
):
    return envelope(request, list_standards(connection, pollutant_id, source_type))


@app.get("/api/operation-logs")
def operation_logs(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    user: dict[str, Any] = Depends(current_user),
    connection: Connection = Depends(get_connection),
):
    where = "" if user["role"] in {"admin", "manager"} else "WHERE user_id=:user_id"
    rows = connection.execute(text(f"""
        SELECT id, user_id, username_snapshot, action, target, result_status, created_at
        FROM operation_log {where}
        ORDER BY created_at DESC, id DESC LIMIT :limit
    """), {"user_id": user["id"], "limit": limit}).mappings()
    return envelope(request, [{
        "id": row["id"],
        "operator": row["username_snapshot"] or "未知用户",
        "action": row["action"],
        "target": row["target"],
        "status": row["result_status"],
        "createdAt": row["created_at"].strftime("%Y-%m-%d %H:%M:%S"),
    } for row in rows])


@app.get("/api/reports")
def reports(
    request: Request,
    user: dict[str, Any] = Depends(current_user),
    connection: Connection = Depends(get_connection),
):
    rows = connection.execute(text("""
        SELECT rr.id, rr.report_no, rr.scheme_id, rr.calc_result_id, rr.report_type,
               rr.generated_at, cr.conclusion, u.real_name, u.username
        FROM report_record rr
        JOIN calc_result cr ON cr.id=rr.calc_result_id
        JOIN sys_user u ON u.id=rr.generated_by
        ORDER BY rr.generated_at DESC, rr.id DESC
        LIMIT 200
    """)).mappings()
    return envelope(request, [{
        "id": row["id"], "name": row["report_no"], "schemeId": row["scheme_id"],
        "calcResultId": row["calc_result_id"], "reportType": row["report_type"],
        "conclusion": row["conclusion"],
        "createdAt": row["generated_at"].strftime("%Y-%m-%d %H:%M:%S"),
        "createdBy": row["real_name"] or row["username"],
    } for row in rows])


@app.get("/api/backups")
def backups(
    request: Request,
    user: dict[str, Any] = Depends(current_user),
    connection: Connection = Depends(get_connection),
):
    rows = connection.execute(text("""
        SELECT id, file_path, type, status, operator, backup_time
        FROM backup_record ORDER BY backup_time DESC, id DESC LIMIT 100
    """)).mappings()
    return envelope(request, [{
        "id": row["id"], "name": row["file_path"], "type": row["type"],
        "status": row["status"], "operator": row["operator"],
        "createdAt": row["backup_time"].strftime("%Y-%m-%d %H:%M:%S"),
    } for row in rows])


def _write_audit(
    connection: Connection,
    user: dict[str, Any],
    action: str,
    request_id: str,
    target_type: str | None = None,
    target_id: int | None = None,
    target: str | None = None,
) -> None:
    connection.execute(text("""
        INSERT INTO operation_log (
          user_id, username_snapshot, action, target_type, target_id, target, request_id, result_status
        ) VALUES (:user_id, :username, :action, :target_type, :target_id, :target, :request_id, 'success')
    """), {
        "user_id": user["id"], "username": user["username"], "action": action,
        "target_type": target_type, "target_id": target_id, "target": target, "request_id": request_id,
    })
