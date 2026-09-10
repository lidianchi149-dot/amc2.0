# AMC Steady Lab · Web1

`web1` 是按一期文档重新实现的商业演示前端，技术栈为 **Vue 3.5.42 + Element Plus 2.14.5**。旧版 `my-product/web` 已保留，两个版本互不覆盖。

## 运行

本项目采用无构建方式，Vue 3 与 Element Plus 运行文件已固定在 `vendor` 目录，启动一个静态服务器即可：

```powershell
python -m http.server 8001 --directory my-product/web1
```

然后访问 `http://127.0.0.1:8001`。

首次打开无需联网。演示账号：

- `engineer01 / demo123`
- `admin / admin123`
- `viewer / viewer123`

## 已实现范围

- Vue 3 Composition-compatible Global API + Element Plus 组件体系。
- 商业化登录页、响应式工作台、深浅色主题。
- 客户 → 项目 → 洁净室 → 方案业务档案链路。
- 方案新建、保存、复制、逻辑删除。
- 百分比输入转 0–1 小数、α/β 自动互补及输入校验。
- `ppb ↔ μg/m³` 换算，默认摩尔体积 `24.04 L/mol`。
- 一期稳态迭代模型、`1e-6` 收敛阈值、最多 `200` 次迭代。
- `C0 / C1 / Creturn / Cmix / Cout2 / Cr` 六节点展示。
- `pass / fail / no_standard` 三态结论。
- 收敛曲线、节点数据、迭代明细与气流路径动画。
- 最多 3 个方案对比、污染物资料库、标准库。
- 报告记录、CSV 导出、打印/PDF、备份和审计入口。
- Mock REST API 统一返回 `{ code, message, data, requestId }`。

## 文件结构

```text
web1/
├─ index.html          # Vue 3 + Element Plus 页面模板
├─ src/
│  ├─ app.js           # 页面状态、交互与业务编排
│  ├─ engine.js        # AMC 稳态计算引擎
│  ├─ mock-api.js      # 按接口文档实现的浏览器内 Mock API
│  └─ styles.css       # 商业化视觉与响应式样式
├─ vendor/             # 本地 Vue 3 与 Element Plus 运行文件
└─ README.md
```

## 计算口径

```text
C1       = C0 × (1 - η_MAU × cov_MAU)
C_return = Cr_old × (1 - η_ARU × cov_ARU)
Cmix     = α × C1 + β × C_return
Cout2    = Cmix × (1 - η_ceil)
Cr_new   = Cmix × (1 - η_ceil × cov_ceil) + α × G
```

当前为前端演示版，Mock API 与数据位于浏览器内存。进入正式商用开发时，可保持现有 API 契约，将 `mock-api.js` 替换为真实后端服务。

浏览器访问 `http://127.0.0.1:8001/tests/engine-baseline.html` 可运行企业 Excel 基准样例与 α/β 校验自检。
