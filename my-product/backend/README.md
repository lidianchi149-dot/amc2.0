# AMC Simulation Python Backend

这是 `web1` 的 Python 后端实现，采用 FastAPI，直接使用已创建的
`amc_simulation` MySQL 数据库。

## 已实现范围

- 按 PRD 公式执行 AMC 稳态不动点迭代。
- 内部统一使用 `ug/m3`，支持 `ppb` 输入/输出换算。
- 后端复验浓度、效率、覆盖率、风比、摩尔质量和迭代参数。
- 检测不收敛及无唯一稳态解的退化工况。
- 在一个数据库事务中保存输入快照、完整精度结果、每步迭代和操作日志。
- 返回统一的 `code/message/data/requestId` 响应信封。
- JWT Bearer Token 鉴权及 Argon2 密码哈希。
- 客户、项目、洁净室、方案 CRUD 与逻辑删除。
- 方案复制、最近结果、结果历史及最多 5 个同洁净室方案对比。
- 污染物 Excel 校验、CAS 规范化、同 CAS 别名合并、幂等导入及资料库查询。
- 标准库、报告、备份和审计记录查询及健康检查。
- 为 `web1` 提供登录用户信息与完整工作区初始化接口。

报告文件生成、用户管理、标准库写入、备份恢复属于文档中的
一期后端功能，但不是计算闭环的直接依赖，建议作为下一批模块实现。

## 首次安装

```powershell
cd D:\coding\amc-program\my-product\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

编辑 `.env`，设置数据库连接和随机的 `JWT_SECRET`。不要提交 `.env`。

## 日常启动（推荐）

前后端统一启动时，在 `my-product` 目录执行：

```powershell
cd D:\coding\amc-program\my-product
python dev.py
```

统一启动器会先执行数据库检查，再启动或复用 `8000` 后端与 `8001` 前端，并等待健康检查通过。保持终端运行，按 `Ctrl+C` 停止由本次命令启动的服务。

## 后端初始化命令

```powershell
cd D:\coding\amc-program\my-product\backend
.\.venv\Scripts\python.exe -m app.cli check-db
.\.venv\Scripts\python.exe -m app.cli create-user --username admin --real-name 系统管理员 --role admin
.\.venv\Scripts\python.exe -m app.cli import-pollutants --file "..\..\客户资料amc\AMC明细汇总-更新V1.xlsx" --username admin
.\.venv\Scripts\python.exe -m app.cli restore-baseline --username admin
```

`import-pollutants` 可重复执行：已存在的 CAS 会更新，不会生成重复污染物。
`restore-baseline` 用于恢复原 `web1` 的客户、项目、洁净室和方案基准数据，
同样可以安全地重复执行。管理员也可以在前端“资料与标准”页面直接上传 `.xlsx` 污染物库。

## 只启动后端（备用方式）

```powershell
cd D:\coding\amc-program\my-product\backend
.\.venv\Scripts\python.exe -m app.cli check-db
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

当终端出现 `address already in use`、`WinError 10013` 或 `WinError 10048` 时，表示 `8000` 已被占用。不要继续重复启动；优先使用统一启动器复用正确的 AMC 后端，或者确认并关闭旧服务。

启动后访问：

- API 文档：`http://127.0.0.1:8000/docs`
- 健康检查：`http://127.0.0.1:8000/health`
- API 根路径：`http://127.0.0.1:8000/api`
- 前端允许来源：`.env` 中 `CORS_ORIGINS`，默认包含 `8001` 与 `5500` 本地端口

## 测试

```powershell
cd D:\coding\amc-program\my-product\backend
.\.venv\Scripts\python.exe -m pytest
```

当前测试已覆盖客户资料中的 `1.xlsx` 和 `2.xlsx` 两组开发基准，并使用未舍入值
验证相对误差不高于 `1e-6`。正式验收时，还应补入客户最终确认的 3-5 组完整案例。
