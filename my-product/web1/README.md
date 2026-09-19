# AMC Steady Lab · Web1

`web1` 是 AMC 洁净室稳态模拟软件的一期前端，使用 **Vue 3.5.42 + Element Plus 2.14.5** 实现，通过 HTTP API 对接 `my-product/backend` 中的 FastAPI 服务，业务数据保存在 MySQL 数据库中。


## 技术架构

- 前端：Vue 3 Global API、Element Plus、原生 JavaScript/CSS。
- 后端：Python、FastAPI、SQLAlchemy。
- 数据库：MySQL 9.7，默认数据库名为 `amc_simulation`。
- 鉴权：JWT Bearer Token。
- 部署方式：前端采用无构建静态部署，不依赖 Node.js。

## 启动项目（推荐）

以后只需要打开一个 PowerShell 窗口，执行：

```powershell
cd D:\coding\amc-program\my-product
python dev.py
```

启动器会依次检查数据库、启动或复用 `8000` 后端、启动或复用 `8001` 前端，并等待两个服务通过健康检查。看到“启动完成”后再访问：

`http://127.0.0.1:8001`

保持终端窗口运行。按 `Ctrl+C` 会停止由本次命令启动的前后端服务。不要重复开启多个服务窗口；如果端口被其他程序占用，启动器会直接显示原因，而不会出现“看似启动但页面空白”的情况。

首次运行尚未创建 `.venv` 或 `.env` 时，请先完成 [后端首次安装](../backend/README.md#首次安装)。

## 分别启动（备用方式）

### 1. 启动后端

在 PowerShell 中执行：

```powershell
cd D:\coding\amc-program\my-product\backend
.\.venv\Scripts\python.exe -m app.cli check-db
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000

```

后端启动后可以访问：

- 健康检查：`http://127.0.0.1:8000/health`
- API 文档：`http://127.0.0.1:8000/docs`

如果数据库中还没有用户，请先创建账号：

```powershell
cd D:\coding\amc-program\my-product\backend
.\.venv\Scripts\python.exe -m app.cli create-user --username admin --real-name 系统管理员 --role admin
```

命令会提示输入密码。项目不提供硬编码的默认账号或默认密码。

### 2. 启动前端

打开另一个 PowerShell 窗口执行项目自带的无缓存静态服务器：

```powershell
cd D:\coding\amc-program\my-product\web1
python serve.py
```

浏览器访问：

`http://127.0.0.1:8001`

不要直接双击 `index.html`，否则浏览器的本地文件安全策略可能阻止 API 请求。

服务健康检查：

- 前端：`http://127.0.0.1:8001/health`
- 后端：`http://127.0.0.1:8000/health`

## API 配置

前端默认连接 `http://127.0.0.1:8000`。

如需切换后端地址，可以在浏览器控制台执行以下命令后刷新页面：

```javascript
localStorage.setItem('amcApiBaseUrl', 'http://服务器地址:8000');
```

恢复默认地址：

```javascript
localStorage.removeItem('amcApiBaseUrl');
```

后端 `.env` 中的 `CORS_ORIGINS` 必须包含实际的前端访问地址。

## 已实现功能

- 后端账号登录、JWT 保存、登录状态恢复和安全退出。
- 客户、项目、洁净室和方案业务数据加载。
- 方案新建、保存、复制和逻辑删除。
- 百分比参数转换以及 α/β 自动互补。
- 调用 Python 后端执行稳态计算，浏览器不直接写入数据库。
- `ppb` 与 `μg/m³` 输入输出换算。
- `C0 / C1 / Creturn / Cmix / Cout2 / Cr` 六节点结果展示。
- 收敛曲线、节点数据、迭代明细和计算历史。
- 最多 5 个同一洁净室的已计算方案对比。
- 污染物资料、标准库、报告记录、备份记录和操作日志查询。
- CSV 导出、打印和 PDF 输出入口。
- 响应式布局及深浅色主题。

接口统一响应结构：

```json
{
  "code": 0,
  "message": "success",
  "data": {},
  "requestId": "req_xxx"
}
```

## 文件结构

```text
web1/
├─ index.html                 # Vue 页面模板及入口
├─ serve.py                   # 禁用缓存并提供健康检查的本地静态服务器
├─ src/
│  ├─ api.js                  # FastAPI 客户端、JWT 与数据装载
│  ├─ app.js                  # 页面状态、交互和业务编排
│  ├─ styles.css              # 商业化视觉和响应式样式
│  ├─ engine.js               # 历史前端基准引擎，仅供测试页使用
│  └─ mock-api.js             # 历史 Mock 实现，正式页面不再加载
├─ tests/
│  └─ engine-baseline.html    # 独立算法基准测试页面
├─ vendor/                    # 本地 Vue 3 与 Element Plus 文件
├─ THIRD_PARTY_NOTICES.md
└─ README.md
```

正式页面只加载 `api.js` 和 `app.js`，不会加载 `mock-api.js` 或在浏览器中执行 `engine.js`。计算结果、输入快照、迭代过程和操作日志均由后端写入 MySQL。

## 常见问题

### 页面显示 API Offline

依次检查：

1. FastAPI 是否已在 `8000` 端口启动。
2. `http://127.0.0.1:8000/health` 是否能够正常访问。
3. 前端配置的 API 地址是否正确。
4. 后端 `.env` 的 `CORS_ORIGINS` 是否包含 `http://127.0.0.1:8001`。

### 页面空白、刷新无效或端口启动失败

优先关闭以前手工启动的 `http.server`、Uvicorn 窗口，然后重新执行 `python dev.py`。统一启动器和 `serve.py` 会禁用 HTML/JS/CSS 浏览器缓存，并在 Vue 资源加载失败时直接显示错误说明，不会继续呈现无提示空白页。

若需要查看端口占用：

```powershell
netstat -ano | Select-String ':8000|:8001'
```

不要随意结束未知进程；先根据最后一列 PID 在任务管理器中确认它是否是以前启动的 AMC Python 服务。

### 无法登录

确认已经通过后端 CLI 创建用户，并检查用户状态是否为 `active`。本项目不再使用 `engineer01 / demo123` 等 Mock 演示账号。

### 登录后没有业务数据

这表示数据库目前为空。客户、项目、洁净室、污染物和方案需要通过后端接口或初始化数据导入后才会显示，前端不会自动生成演示数据。

## 独立算法测试

在前端静态服务器运行期间访问：

`http://127.0.0.1:8001/tests/engine-baseline.html`

该页面仅用于验证历史浏览器算法基准，不参与正式业务计算。正式计算以 Python 后端结果为准。
