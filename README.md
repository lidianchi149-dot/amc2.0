# AMC 洁净室稳态模拟软件

本仓库为 AMC 洁净室稳态模拟软件一期项目，包含 Vue 3 前端、FastAPI 后端、MySQL 数据库脚本和客户需求文档。

## 项目结构

```text
amc-program/
├─ my-product/
│  ├─ dev.py                 # 本地前后端统一启动器
│  ├─ web1/                  # Vue 3 + Element Plus 前端
│  ├─ backend/               # Python FastAPI 后端与计算引擎
│  └─ 数据库脚本(DBA)/       # MySQL 建库建表脚本
└─ 客户资料amc/              # 客户提供的需求与基础资料
```

## 首次运行准备

项目要求：

- Windows PowerShell
- Python 3.11 或更高版本
- MySQL 9.7（当前开发环境使用 Docker MySQL）

首次使用时安装后端环境：

```powershell
cd D:\coding\amc-program\my-product\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

随后编辑 `my-product/backend/.env`，确认 `DATABASE_URL`、`JWT_SECRET` 和 `CORS_ORIGINS` 配置正确。已有 `.env` 时不要覆盖。

## 日常启动（推荐）

日常开发不需要分别输入多条前后端命令，只需运行统一启动器：

```powershell
cd D:\coding\amc-program\my-product
python dev.py
```

启动器会：

1. 检查后端虚拟环境和 MySQL 连接。
2. 启动或复用 `http://127.0.0.1:8000` 后端。
3. 启动或复用 `http://127.0.0.1:8001` 前端。
4. 等待前后端健康检查通过后提示访问地址。
5. 检测端口冲突和服务异常退出，避免无提示白屏。

看到“启动完成”后访问：

- 前端：`http://127.0.0.1:8001`
- 后端健康检查：`http://127.0.0.1:8000/health`
- API 文档：`http://127.0.0.1:8000/docs`

保持启动窗口运行。按 `Ctrl+C` 停止由本次命令启动的服务。

## 初始化业务数据

如果数据库还没有管理员或基础数据，在后端目录执行：

```powershell
cd D:\coding\amc-program\my-product\backend
.\.venv\Scripts\python.exe -m app.cli create-user --username admin --real-name 系统管理员 --role admin
.\.venv\Scripts\python.exe -m app.cli import-pollutants --file "..\..\客户资料amc\AMC明细汇总-更新V1.xlsx" --username admin
.\.venv\Scripts\python.exe -m app.cli restore-baseline --username admin
```

创建用户时会提示输入密码。项目不提供硬编码默认密码。

## 启动故障排查

如果浏览器无法访问、页面空白或刷新无效：

1. 关闭以前手工启动的 `http.server` 和 Uvicorn 终端。
2. 重新运行 `python dev.py`，以终端中的健康检查结果为准。
3. 分别访问 `http://127.0.0.1:8000/health` 和 `http://127.0.0.1:8001/health`。
4. 如提示端口占用，使用以下命令确认 PID，再通过任务管理器核对进程：

```powershell
netstat -ano | Select-String ':8000|:8001'
```

不要直接双击 `web1/index.html`，也不要随意结束无法确认来源的系统进程。

更详细说明请查看：

- [前端说明](my-product/web1/README.md)
- [后端说明](my-product/backend/README.md)
