(function () {
  "use strict";

  const $ = (selector, scope = document) => scope.querySelector(selector);
  const $$ = (selector, scope = document) => Array.from(scope.querySelectorAll(selector));
  const engine = window.AMCEngine;
  const pollutants = [
    { id: "nh3", name: "氨 / Ammonia", formula: "NH₃", cas: "7664-41-7", mass: 17.03 },
    { id: "acetic", name: "乙酸 / Acetic acid", formula: "CH₃COOH", cas: "64-19-7", mass: 60.05 },
    { id: "so2", name: "二氧化硫 / Sulfur dioxide", formula: "SO₂", cas: "7446-09-5", mass: 64.07 },
    { id: "hcl", name: "氯化氢 / Hydrogen chloride", formula: "HCl", cas: "7647-01-0", mass: 36.46 },
    { id: "toluene", name: "甲苯 / Toluene", formula: "C₇H₈", cas: "108-88-3", mass: 92.14 },
    { id: "ipa", name: "异丙醇 / Isopropyl alcohol", formula: "C₃H₈O", cas: "67-63-0", mass: 60.10 }
  ];
  const state = { unit: "ug", lastResult: null, saved: false };

  function toast(message) {
    const el = $("#toast");
    el.textContent = message;
    el.classList.add("show");
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => el.classList.remove("show"), 2300);
  }

  function format(value, digits = 4) {
    if (!Number.isFinite(value)) return "—";
    if (Math.abs(value) > 99999 || (Math.abs(value) > 0 && Math.abs(value) < 0.001)) return value.toExponential(3);
    return value.toLocaleString("zh-CN", { maximumFractionDigits: digits, minimumFractionDigits: Math.min(2, digits) });
  }

  function currentPollutant() {
    return pollutants.find((item) => item.id === $("#pollutantSelect").value) || pollutants[0];
  }

  function convert(value, from, to) {
    if (from === to || !Number.isFinite(value)) return value;
    const mass = Number($("#molarMass").value);
    const volume = Number($("#molarVolume").value);
    return from === "ppb" ? engine.ppbToUg(value, mass, volume) : engine.ugToPpb(value, mass, volume);
  }

  function readInputs() {
    const rawC0 = Number($("#c0Input").value);
    const rawG = Number($("#gInput").value);
    return {
      c0: state.unit === "ug" ? rawC0 : convert(rawC0, "ppb", "ug"),
      g: state.unit === "ug" ? rawG : convert(rawG, "ppb", "ug"),
      etaMau: Number($("#etaMau").value) / 100,
      covMau: Number($("#covMau").value) / 100,
      etaCeil: Number($("#etaCeil").value) / 100,
      covCeil: Number($("#covCeil").value) / 100,
      etaAru: Number($("#etaAru").value) / 100,
      covAru: Number($("#covAru").value) / 100,
      alpha: Number($("#alphaInput").value) / 100,
      beta: Number($("#betaInput").value) / 100
    };
  }

  function targetInUg() {
    if (!$("#targetEnabled").checked) return null;
    const value = Number($("#targetInput").value);
    if (!Number.isFinite(value) || value < 0) throw new Error("目标限值必须是非负数字");
    return state.unit === "ug" ? value : convert(value, "ppb", "ug");
  }

  function displayValue(valueUg) {
    return state.unit === "ug" ? valueUg : convert(valueUg, "ug", "ppb");
  }

  function unitText() { return state.unit === "ug" ? "μg/m³" : "ppb"; }

  function calculate(silent = false) {
    const validation = $("#validationMessage");
    validation.textContent = "";
    try {
      const input = readInputs();
      if ([input.c0, input.g].some((value) => value > engine.ppbToUg(1000000, Number($("#molarMass").value), Number($("#molarVolume").value)))) {
        validation.textContent = "提示：输入浓度超过 1,000,000 ppb 等值范围，请确认量级。";
      }
      const result = engine.calculate(input);
      result.input = input;
      result.target = targetInUg();
      result.pollutant = currentPollutant();
      result.createdAt = new Date();
      state.lastResult = result;
      state.saved = false;
      renderResult();
      if (!silent) toast(result.status === "converged" ? `计算完成 · ${result.iterationCount} 次迭代收敛` : result.message);
    } catch (error) {
      validation.textContent = error.message;
      if (!silent) toast("参数校验未通过");
    }
  }

  function compliance(result) {
    if (result.status !== "converged") return { type: "waiting", label: "计算异常", icon: "!", description: result.message };
    if (result.target === null) return { type: "no-standard", label: "未设置标准", icon: "—", description: "结果有效，但不生成达标结论" };
    if (result.cr <= result.target) return { type: "pass", label: "达标", icon: "✓", description: `低于目标限值 ${format(displayValue(result.target))} ${unitText()}` };
    return { type: "fail", label: "未达标", icon: "×", description: `超出目标限值 ${format(displayValue(result.target))} ${unitText()}` };
  }

  function renderResult() {
    const result = state.lastResult;
    if (!result) return;
    const c = compliance(result);
    const unit = unitText();
    const finalValue = displayValue(result.cr);
    $("#resultSummary").className = `result-summary ${c.type}`;
    $("#resultIcon").textContent = c.icon;
    $("#resultStatus").textContent = c.label;
    $("#resultDescription").textContent = c.description;
    $("#resultCr").textContent = format(finalValue, 6);
    $("#metricCr").textContent = format(finalValue);
    $("#metricCompliance").textContent = c.label;
    $("#metricIterations").textContent = result.iterationCount ? `${result.iterationCount} 次` : "异常";
    $("#metricTrend").textContent = result.status === "converged" ? "已收敛" : "需检查";
    $("#metricGap").textContent = result.target === null || !Number.isFinite(result.cr) ? "—" : `${result.cr <= result.target ? "余量" : "超限"} ${format(Math.abs(displayValue(result.target - result.cr)))} ${unit}`;
    $("#metricTarget").textContent = result.target === null ? "—" : format(displayValue(result.target));
    $("#resultTime").textContent = `结果快照 · ${result.createdAt.toLocaleString("zh-CN", { hour12: false })}`;
    $("#iterationBadge").textContent = result.iterations.length;
    $("#csvButton").disabled = false;
    $("#printButton").disabled = false;
    updateUnits();
    renderNodes();
    renderChart();
    renderIterations();
    const density = Math.max(.15, Math.min(.85, result.target ? result.cr / Math.max(result.target, 1) * .5 : .45));
    $(".particles").style.opacity = density.toFixed(2);
  }

  function renderNodes() {
    const r = state.lastResult;
    if (!r) return;
    const values = { c0: r.input.c0, c1: r.c1, cReturn: r.cReturn, cMix: r.cMix, cOut2: r.cOut2, cr: r.cr };
    Object.entries(values).forEach(([key, value]) => {
      const node = $(`[data-node="${key}"]`);
      if (node) node.textContent = format(displayValue(value));
    });
    const labels = { c0: "室外浓度 C₀", c1: "MAU 出口 C₁", cReturn: "ARU 回风 Creturn", cMix: "混风浓度 Cmix", cOut2: "Ceiling 本体出口 Cout₂", cr: "稳态室内浓度 Cᵣ" };
    $("#nodeTable").innerHTML = Object.entries(values).map(([key, value]) => `<div><small>${labels[key]}</small><strong>${format(displayValue(value), 6)} ${unitText()}</strong></div>`).join("");
  }

  function renderIterations() {
    const r = state.lastResult;
    $("#iterationTable").innerHTML = r.iterations.map((row) => `<tr><td>${row.index}</td><td>${format(displayValue(row.oldCr), 6)}</td><td>${format(displayValue(row.cReturn), 6)}</td><td>${format(displayValue(row.cMix), 6)}</td><td>${format(displayValue(row.cr), 6)}</td><td>${format(displayValue(row.delta), 7)}</td></tr>`).join("");
  }

  function renderChart() {
    const svg = $("#convergenceChart");
    const values = state.lastResult.iterations.map((row) => displayValue(row.cr));
    if (!values.length) return;
    const width = 720, height = 220, left = 48, right = 20, top = 22, bottom = 30;
    const min = Math.min(...values), max = Math.max(...values);
    const spread = Math.max(max - min, Math.abs(max) * .08, .000001);
    const yMin = Math.max(0, min - spread * .2), yMax = max + spread * .2;
    const x = (i) => left + (values.length === 1 ? 0 : i / (values.length - 1) * (width - left - right));
    const y = (v) => top + (yMax - v) / (yMax - yMin) * (height - top - bottom);
    const path = values.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
    const area = `${path} L${x(values.length - 1)},${height - bottom} L${left},${height - bottom} Z`;
    const grid = [0, .5, 1].map((ratio) => { const yy = top + ratio * (height - top - bottom); const val = yMax - ratio * (yMax - yMin); return `<line class="grid-line" x1="${left}" y1="${yy}" x2="${width-right}" y2="${yy}"/><text x="4" y="${yy+3}">${format(val, 2)}</text>`; }).join("");
    svg.innerHTML = `<defs><linearGradient id="chartGradient" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#0da5a4" stop-opacity=".22"/><stop offset="1" stop-color="#0da5a4" stop-opacity="0"/></linearGradient></defs>${grid}<line x1="${left}" y1="${height-bottom}" x2="${width-right}" y2="${height-bottom}"/><path class="chart-area" d="${area}"/><path class="chart-path" d="${path}"/><circle cx="${x(values.length-1)}" cy="${y(values[values.length-1])}" r="4"/><text x="${left}" y="${height-8}">1</text><text x="${width-right-18}" y="${height-8}">${values.length} 次</text>`;
    $("#chartCaption").textContent = `Cr / ${unitText()}`;
  }

  function updateUnits() {
    $$(".unit-label").forEach((el) => { el.textContent = unitText(); });
    $("#metricUnit").textContent = unitText();
    $("#metricTargetUnit").textContent = unitText();
  }

  function changeUnit(nextUnit) {
    if (nextUnit === state.unit) return;
    const previous = state.unit;
    ["#c0Input", "#gInput", "#targetInput"].forEach((id) => {
      const input = $(id);
      const value = Number(input.value);
      if (Number.isFinite(value)) input.value = Number(convert(value, previous, nextUnit).toPrecision(10));
    });
    state.unit = nextUnit;
    $$(".segmented button").forEach((button) => button.classList.toggle("active", button.dataset.unit === nextUnit));
    updateUnits();
    if (state.lastResult) renderResult();
  }

  function syncRatio(source) {
    const sourceInput = source === "alpha" ? $("#alphaInput") : $("#betaInput");
    const partner = source === "alpha" ? $("#betaInput") : $("#alphaInput");
    const value = Math.max(0, Math.min(100, Number(sourceInput.value) || 0));
    sourceInput.value = value;
    partner.value = Number((100 - value).toFixed(2));
    $("#alphaTrack").style.width = `${$("#alphaInput").value}%`;
  }

  function populateDataViews() {
    $("#dashboardContent").innerHTML = `<article class="card dash-card"><h3>本月计算</h3><div class="big-stat">28 <small>次 · 94% 已收敛</small></div></article><article class="card dash-card"><h3>活跃项目</h3><div class="big-stat">6 <small>个 · 12 间洁净室</small></div></article><article class="card dash-card"><h3>待处理异常</h3><div class="big-stat">2 <small>项参数需复核</small></div></article><article class="card dash-card wide"><h3>最近计算</h3><div class="activity-list"><div><i></i><span>NH₃ 控制方案 A · Fab 3 / CR-01</span><time>刚刚</time></div><div><i></i><span>乙酸基线方案 · 精密光学 / A-02</span><time>昨天 16:42</time></div><div><i></i><span>SO₂ 高负荷工况 · Fab 2 / CR-07</span><time>9月1日</time></div></div></article><article class="card dash-card"><h3>交付进度</h3><div class="big-stat">75% <small>M3 · 结果表达</small></div></article>`;
    $("#projectsContent").innerHTML = `<div class="data-toolbar"><input class="search-box" placeholder="搜索客户、项目或洁净室"><span class="tag">6 个活跃项目</span></div>${table(["客户 / 项目","洁净室","方案数","最近计算","状态"],[ ["华东芯片制造有限公司<small>Fab 3 洁净厂房升级</small>","光刻区 CR-01","4","今天 10:32","<span class='tag'>进行中</span>"],["精密光学科技<small>A区环境控制改造</small>","镀膜间 A-02","3","昨天 16:42","<span class='tag'>进行中</span>"],["先进封装实验室<small>AMC 基线评估</small>","测试区 LAB-05","2","8月29日","<span class='tag warning'>待复核</span>"] ])}`;
    $("#pollutantsContent").innerHTML = `<div class="data-toolbar"><input class="search-box" id="pollutantSearch" placeholder="按名称或 CAS 号搜索"><span class="tag warning">示例数据 · 上线前复核</span></div><div id="pollutantRows"></div>`;
    renderPollutantRows(pollutants);
    $("#standardsContent").innerHTML = `<div class="data-toolbar"><input class="search-box" placeholder="搜索标准或污染物"><span class="tag">4 条已启用</span></div>${table(["标准名称","污染物","目标值","来源 / 范围","状态"],[ ["光刻区 NH₃ 控制要求","NH₃","35.00 μg/m³","企业 · 全局","<span class='tag'>已启用</span>"],["客户 A 乙酸限值","CH₃COOH","12.00 ppb","客户 · 精密光学","<span class='tag'>已启用</span>"],["行业参考 SO₂","SO₂","50.00 μg/m³","行业 · 参考","<span class='tag gray'>草稿</span>"] ])}`;
    $("#reportsContent").innerHTML = `<div class="data-toolbar"><input class="search-box" placeholder="搜索方案或报告编号"><span class="tag">结果快照可追溯</span></div>${table(["报告编号 / 方案","格式","计算结果","生成时间","操作人"],[ ["AMC-20260903-008<small>NH₃ 控制方案 A · V2</small>","PDF","<span class='tag'>达标</span>","今天 10:32","林工程师"],["AMC-20260902-021<small>乙酸基线方案 · V1</small>","Excel","<span class='tag warning'>未达标</span>","昨天 16:48","周工程师"],["AMC-20260901-014<small>SO₂ 高负荷工况 · V4</small>","PDF","<span class='tag'>达标</span>","9月1日 14:12","林工程师"] ])}`;
    $("#settingsContent").innerHTML = `<article class="card setting-card"><h3>稳态计算参数</h3><div class="setting-row"><span>收敛阈值 ε</span><b>1 × 10⁻⁶</b></div><div class="setting-row"><span>最大迭代次数</span><b>200</b></div><div class="setting-row"><span>摩尔体积默认值</span><b>24.04 L/mol</b></div><div class="setting-row"><span>算法版本</span><b>steady-v1.0</b></div></article><article class="card setting-card"><h3>权限与审计</h3><div class="setting-row"><span>启用角色</span><b>5 类</b></div><div class="setting-row"><span>在线用户</span><b>8 人</b></div><div class="setting-row"><span>今日关键操作</span><b>14 条</b></div><div class="setting-row"><span>最近备份</span><b>待配置</b></div></article>`;
    renderCompare();
  }

  function table(headers, rows) {
    return `<table class="simple-table"><thead><tr>${headers.map((h) => `<th>${h}</th>`).join("")}</tr></thead><tbody>${rows.map((row) => `<tr>${row.map((cell) => `<td>${cell}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
  }

  function renderPollutantRows(rows) {
    $("#pollutantRows").innerHTML = table(["污染物","化学式","CAS 号","摩尔质量","数据状态"], rows.map((p) => [`${p.name}<small>用于单位换算与标准匹配</small>`, p.formula, p.cas, `${p.mass} g/mol`, "<span class='tag'>可用</span>"]));
  }

  function renderCompare() {
    const current = state.lastResult ? displayValue(state.lastResult.cr) : 7.82;
    const max = Math.max(current, 16.2, 1);
    $("#compareContent").innerHTML = `<div class="data-toolbar"><span class="tag">同一洁净室 · CR-01</span><span>2 / 5 个方案</span></div><div class="compare-bars"><div class="compare-bar"><span>当前方案 A</span><div><i style="width:${current/max*100}%"></i></div><strong>${format(current)} ${unitText()}</strong></div><div class="compare-bar"><span>低成本方案 B</span><div><i style="width:${16.2/max*100}%;background:linear-gradient(90deg,#7357bd,#a68de7)"></i></div><strong>16.20 ${unitText()}</strong></div></div>${table(["方案","MAU 效率","Ceiling 效率","ARU 效率","Cr","结论"],[ ["当前方案 A","65%","85%","40%",`${format(current)} ${unitText()}`,current <= Number($("#targetInput").value) ? "<span class='tag'>达标</span>" : "<span class='tag warning'>未达标</span>"],["低成本方案 B","45%","72%","20%",`16.20 ${unitText()}`,"<span class='tag'>达标</span>"] ])}`;
  }

  function exportCsv() {
    if (!state.lastResult) return;
    const r = state.lastResult, c = compliance(r), unit = unitText();
    const rows = [["AMC 洁净室稳态模拟报告"],["方案", $("#schemeName").value],["污染物", r.pollutant.name],["CAS", r.pollutant.cas],["算法版本",r.version],["显示单位",unit],["C0",displayValue(r.input.c0)],["G",displayValue(r.input.g)],["C1",displayValue(r.c1)],["Creturn",displayValue(r.cReturn)],["Cmix",displayValue(r.cMix)],["Cout2",displayValue(r.cOut2)],["Cr",displayValue(r.cr)],["目标值",r.target === null ? "未设置" : displayValue(r.target)],["结论",c.label],["迭代次数",r.iterationCount],["摩尔质量",$("#molarMass").value],["摩尔体积",$("#molarVolume").value]];
    const csv = "\ufeff" + rows.map((row) => row.map((value) => `"${String(value).replaceAll('"','""')}"`).join(",")).join("\r\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `AMC_${$("#schemeName").value}_${new Date().toISOString().slice(0,10)}.csv`;
    link.click(); URL.revokeObjectURL(link.href); toast("计算数据已导出");
  }

  function bindEvents() {
    $$(".nav-item").forEach((button) => button.addEventListener("click", () => switchView(button.dataset.view)));
    $$('[data-jump="simulation"]').forEach((button) => button.addEventListener("click", () => switchView("simulation")));
    $("#menuButton").addEventListener("click", () => { $("#sidebar").classList.add("open"); $("#sidebarScrim").classList.add("show"); });
    $("#sidebarScrim").addEventListener("click", closeSidebar);
    $("#themeButton").addEventListener("click", () => { document.body.classList.toggle("dark"); localStorage.setItem("amc-theme", document.body.classList.contains("dark") ? "dark" : "light"); });
    $("#calculateButton").addEventListener("click", () => calculate());
    $("#saveButton").addEventListener("click", saveScheme);
    $("#copyButton").addEventListener("click", () => { $("#schemeName").value += " · 副本"; state.saved = false; toast("已复制为新草稿"); });
    $("#resetButton").addEventListener("click", resetDemo);
    $("#csvButton").addEventListener("click", exportCsv);
    $("#printButton").addEventListener("click", () => window.print());
    $$(".segmented button").forEach((button) => button.addEventListener("click", () => changeUnit(button.dataset.unit)));
    $("#alphaInput").addEventListener("input", () => syncRatio("alpha"));
    $("#betaInput").addEventListener("input", () => syncRatio("beta"));
    $$("input[type=range]").forEach((input) => input.addEventListener("input", () => { input.nextElementSibling.value = `${input.value}%`; }));
    $("#pollutantSelect").addEventListener("change", () => { const p = currentPollutant(); $("#molarMass").value = p.mass; $("#pollutantMeta").textContent = `${p.formula} · ${p.cas}`; });
    $("#targetEnabled").addEventListener("change", (event) => { $("#targetInput").disabled = !event.target.checked; });
    $$(".result-tabs button").forEach((button) => button.addEventListener("click", () => switchTab(button.dataset.tab)));
    $("#pollutantSearch").addEventListener("input", (event) => { const q = event.target.value.toLowerCase(); renderPollutantRows(pollutants.filter((p) => `${p.name}${p.cas}${p.formula}`.toLowerCase().includes(q))); });
    $("#newProjectButton").addEventListener("click", () => toast("新建项目表单将在后端接入后启用"));
  }

  function switchView(name) {
    $$(".view").forEach((view) => view.classList.toggle("active", view.id === `view-${name}`));
    $$(".nav-item").forEach((item) => item.classList.toggle("active", item.dataset.view === name));
    const label = $(`.nav-item[data-view="${name}"]`)?.textContent.trim().replace(/\d+$/, "") || "工作台";
    $("#breadcrumbCurrent").textContent = label;
    if (name === "compare") renderCompare();
    closeSidebar(); window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function closeSidebar() { $("#sidebar").classList.remove("open"); $("#sidebarScrim").classList.remove("show"); }
  function switchTab(name) { $$(".result-tabs button").forEach((b) => b.classList.toggle("active", b.dataset.tab === name)); $$(".tab-panel").forEach((p) => p.classList.toggle("active", p.id === `tab-${name}`)); }

  function saveScheme() {
    try {
      const record = { name: $("#schemeName").value, pollutant: currentPollutant().id, unit: state.unit, input: readInputs(), target: targetInUg(), savedAt: new Date().toISOString() };
      localStorage.setItem("amc-current-scheme", JSON.stringify(record)); state.saved = true; toast("方案已保存到本机工作空间");
    } catch (error) { toast(error.message); }
  }

  function resetDemo() {
    const values = { c0Input:48,gInput:12,molarMass:17.03,molarVolume:24.04,alphaInput:30,betaInput:70,etaMau:65,covMau:100,etaCeil:85,covCeil:95,etaAru:40,covAru:80,targetInput:35 };
    Object.entries(values).forEach(([id,value]) => { $(`#${id}`).value = value; });
    $$("input[type=range]").forEach((input) => { input.nextElementSibling.value = `${input.value}%`; });
    $("#pollutantSelect").value = "nh3"; $("#targetEnabled").checked = true; $("#targetInput").disabled = false; syncRatio("alpha"); changeUnit("ug"); calculate(true); toast("已恢复演示参数");
  }

  function init() {
    $("#pollutantSelect").innerHTML = pollutants.map((p) => `<option value="${p.id}">${p.name}</option>`).join("");
    $("#pollutantMeta").textContent = `${pollutants[0].formula} · ${pollutants[0].cas}`;
    if (localStorage.getItem("amc-theme") === "dark") document.body.classList.add("dark");
    populateDataViews(); bindEvents(); syncRatio("alpha"); updateUnits(); calculate(true);
  }

  init();
})();
