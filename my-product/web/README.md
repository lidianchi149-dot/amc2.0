# AMC-Simulation 网站原型

这是根据《AMC洁净室稳态模拟软件 PRD V1.0》实现的可交互前端原型，采用原生 HTML、CSS 和 JavaScript，无第三方依赖。

## 本地运行

在仓库根目录执行：

```powershell
python -m http.server 4173 --directory my-product/web
```

然后访问 `http://localhost:4173`。

## 已实现

- 响应式工程工作台与深浅主题
- 污染物选择、ppb/μg/m³ 双向换算
- MAU、Ceiling、ARU 三级过滤参数配置
- α/β 联动校验与稳态迭代计算
- 收敛、未收敛和退化工况识别
- 节点浓度、二维气流映射、收敛曲线与迭代明细
- pass/fail/no_standard 达标三态
- 方案本地保存、复制、对比、CSV 导出和打印/PDF
- 客户项目、污染物、标准、报告与系统管理界面

## 实现边界

当前版本是可运行的前端产品原型，方案保存使用浏览器 `localStorage`，列表数据为演示数据。正式交付还需接入 PRD 定义的 `/api` 后端、RBAC、数据库、Excel/PDF 服务端报告以及企业确认后的污染物和标准数据。

核心计算逻辑位于 `engine.js`，按 PRD 的 `steady-v1.0` 公式实现，内部统一使用 μg/m³，默认收敛阈值为 `1e-6`、最大迭代次数为 `200`。
