(function () {
  'use strict';

  const { createApp } = Vue;
  const api = window.AMCApi;
  const clone = (value) => JSON.parse(JSON.stringify(value));
  const defaultForm = (cleanroomId = null, pollutantId = null) => ({
    id: null, cleanroomId, name: '新建稳态模拟方案', version: 1, concUnit: 'ug', molarMassM: 30.03,
    molarVolumeVm: 24.04, stdSource: 'manual', stdPollutantId: pollutantId, stdLibraryId: null, targetValue: null,
    input: { c0: 10, g: 1.5, etaMau: 0.72, covMau: 1, etaCeil: 0.55, covCeil: 0.92, etaAru: 0.35, covAru: 0.8, alpha: 0.3, beta: 0.7 }
  });

  const PanelTitle = {
    props: ['eyebrow', 'title', 'subtitle'],
    template: '<div class="panel-title"><div><span>{{ eyebrow }}</span><h2>{{ title }}</h2><p v-if="subtitle">{{ subtitle }}</p></div><div class="panel-tools"><slot></slot></div></div>'
  };
  const PageHead = {
    props: ['eyebrow', 'title', 'subtitle'],
    template: '<div class="page-head"><div><span>{{ eyebrow }}</span><h1>{{ title }}</h1><p>{{ subtitle }}</p></div><div class="head-actions"><slot></slot></div></div>'
  };

  const app = createApp({
    components: { PanelTitle, PageHead },
    data() {
      const initial = defaultForm();
      return {
        db: api.db,
        session: { token: api.getStoredToken(), realName: '', role: '' },
        loginForm: { username: '', password: '' },
        loginLoading: false, workspaceLoading: false, apiOnline: false, importingPollutants: false,
        calculating: false, isDark: localStorage.getItem('amcTheme') === 'dark', mobileNavOpen: false,
        desktopNavOpen: false, desktopNavCloseTimer: null,
        view: 'dashboard', currentSchemeId: null, form: initial,
        alphaPercent: Math.round(initial.input.alpha * 100),
        filterValues: { etaMau: 72, covMau: 100, etaCeil: 55, covCeil: 92, etaAru: 35, covAru: 80 },
        validationMessage: '', resultTab: 'chart', pollutantKeyword: '', simulationPollutantKeyword: '', compareResult: { schemes: [] },
        unitOptions: [{ label: 'μg/m³', value: 'ug' }, { label: 'ppb', value: 'ppb' }],
        navItems: [
          { key: 'dashboard', label: '工作台', icon: '⌂' }, { key: 'archive', label: '业务档案', icon: '◇' },
          { key: 'simulation', label: '稳态模拟', icon: '∿' }, { key: 'compare', label: '方案对比', icon: '⇄' },
          { key: 'library', label: '资料与标准', icon: '◎' }, { key: 'reports', label: '报告中心', icon: '▤' },
          { key: 'admin', label: '系统管理', icon: '⚙' }
        ],
        filters: [
          { key: 'mau', name: 'MAU 新风机组', desc: '新风预处理段', eta: 'etaMau', cov: 'covMau' },
          { key: 'ceiling', name: 'Ceiling 顶部过滤', desc: 'Cout2 不含覆盖率', eta: 'etaCeil', cov: 'covCeil' },
          { key: 'aru', name: 'ARU 回风机组', desc: '回风循环处理段', eta: 'etaAru', cov: 'covAru' }
        ],
        flowNodes: [
          { key: 'c0', label: '室外', position: 'pos-c0' }, { key: 'c1', label: 'MAU 后', position: 'pos-c1' },
          { key: 'cmix', label: '混风', position: 'pos-mix' }, { key: 'cout2', label: 'Ceiling 后', position: 'pos-out' },
          { key: 'cReturn', label: 'ARU 后', position: 'pos-return' }
        ],
        dbTables: ['sys_user', 'customer', 'project', 'cleanroom', 'scheme', 'scheme_input', 'calc_input_snapshot', 'calc_result', 'calc_iter', 'pollutant', 'std_library', 'import_record', 'export_record', 'report_record', 'backup_record', 'operation_log', 'system_config']
      };
    },
    computed: {
      today() { return new Intl.DateTimeFormat('zh-CN', { year: 'numeric', month: 'long', day: 'numeric' }).format(new Date()); },
      activeTitle() { return this.navItems.find((item) => item.key === this.view)?.label || '工作台'; },
      roleLabel() { return ({ admin: '系统管理员', engineer: '计算工程师', sales: '销售人员', manager: '管理人员', customer: '客户用户' })[this.session.role] || '访客'; },
      betaPercent() { return 100 - Number(this.alphaPercent || 0); },
      activeSchemes() { return this.db.schemes.filter((item) => !item.deleted); },
      activeCleanrooms() { return this.db.cleanrooms.filter((item) => !item.deleted); },
      latestResult() { return this.db.calcResults.find((item) => item.schemeId === this.currentSchemeId) || this.db.calcResults[0] || null; },
      dashboardMetrics() {
        return [
          { label: '活跃客户', value: this.db.customers.filter((i) => !i.deleted).length, note: '客户业务档案', icon: '◌' },
          { label: '洁净室', value: this.activeCleanrooms.length, note: '纳入模拟范围', icon: '▦' },
          { label: '有效方案', value: this.activeSchemes.length, note: '支持版本复制', icon: '◈' },
          { label: '计算记录', value: this.db.calcResults.length, note: '结果永久留痕', icon: '↗' }
        ];
      },
      recentResults() { return this.db.calcResults.slice(0, 5).map((r) => ({ ...r, schemeName: this.schemeName(r.schemeId), cr: r.nodes.cr })); },
      archiveTree() {
        return this.db.customers.filter((c) => !c.deleted).map((customer) => ({
          key: `c-${customer.id}`, label: customer.name, meta: customer.contact,
          children: this.db.projects.filter((p) => p.customerId === customer.id && !p.deleted).map((project) => ({
            key: `p-${project.id}`, label: project.name, meta: project.location,
            children: this.db.cleanrooms.filter((r) => r.projectId === project.id && !r.deleted).map((room) => ({ key: `r-${room.id}`, label: room.name, meta: room.code }))
          }))
        }));
      },
      filteredPollutants() {
        const keyword = this.pollutantKeyword.trim().toLowerCase();
        return this.db.pollutants.filter((item) => {
          const haystack = [item.name, item.nameEn, item.cas, item.formula, item.molecularFormula, ...(item.aliases || [])]
            .filter(Boolean).join(' ').toLowerCase();
          return !keyword || haystack.includes(keyword);
        });
      },
      simulationPollutants() {
        const keyword = this.simulationPollutantKeyword.trim().toLowerCase();
        if (!keyword) return this.db.pollutants;
        return this.db.pollutants.filter((item) => [
          item.name, item.nameEn, item.cas, item.formula, item.molecularFormula, ...(item.aliases || [])
        ].filter(Boolean).join(' ').toLowerCase().includes(keyword));
      },
      chartSvg() {
        const rows = this.latestResult?.iterations || [];
        if (rows.length < 2) return '<text x="360" y="120" text-anchor="middle" fill="#8b94a7">执行计算后显示收敛曲线</text>';
        const values = rows.map((row) => Number(row.crNew));
        const min = Math.min(...values); const max = Math.max(...values); const spread = max - min || 1;
        const points = values.map((value, index) => `${36 + index * (648 / Math.max(values.length - 1, 1))},${190 - ((value - min) / spread) * 145}`).join(' ');
        const dots = values.map((value, index) => `<circle cx="${36 + index * (648 / Math.max(values.length - 1, 1))}" cy="${190 - ((value - min) / spread) * 145}" r="3" fill="#2f6bff"/>`).join('');
        return `<defs><linearGradient id="area" x1="0" y1="0" x2="0" y2="1"><stop stop-color="#2f6bff" stop-opacity=".3"/><stop offset="1" stop-color="#2f6bff" stop-opacity="0"/></linearGradient></defs><line x1="36" y1="190" x2="684" y2="190" stroke="#dbe1eb"/><polyline points="${points}" fill="none" stroke="#2f6bff" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>${dots}<text x="36" y="215" fill="#8b94a7">1</text><text x="684" y="215" text-anchor="end" fill="#8b94a7">${rows.length} 次迭代</text>`;
      }
    },
    watch: {
      isDark() { this.applyTheme(); },
      'session.token'(token) { if (token) this.$nextTick(() => this.setupAirflowVisual()); }
    },
    methods: {
      setupAirflowVisual() {
        const svg = document.querySelector('.airflow > svg');
        if (!svg || svg.querySelector('.duct-air-streams')) return;
        svg.insertAdjacentHTML('beforeend', `
          <g class="duct-air-streams" aria-hidden="true">
            <path class="air-stream fresh-stream stream-a" pathLength="100" d="M75 98 C92 88 108 108 126 98 S160 88 178 98 S212 108 230 98 S264 88 282 98 S316 108 334 98 S368 88 386 98 S420 108 438 98 S472 88 490 98 S524 108 542 98 S578 90 610 98 Q681 98 681 172"/>
            <path class="air-stream fresh-stream stream-b" pathLength="100" d="M75 104 C87 96 102 112 118 104 S148 95 165 104 S197 113 214 104 S246 95 264 104 S298 113 316 104 S350 95 368 104 S402 113 420 104 S454 95 472 104 S506 113 524 104 S566 97 610 104 Q689 104 689 172"/>
            <path class="air-stream return-stream stream-c" pathLength="100" d="M685 248 Q685 282 610 282 C592 272 574 292 556 282 S520 272 502 282 S466 292 448 282 S412 272 394 282 S358 292 340 282 S304 272 286 282 S250 292 230 282 Q159 282 159 238"/>
            <path class="air-stream return-stream stream-d" pathLength="100" d="M681 248 Q681 290 610 290 C590 300 570 280 550 290 S510 300 490 290 S450 280 430 290 S390 300 370 290 S330 280 310 290 S270 300 230 290 Q151 290 151 238"/>
          </g>`);
      },
      openDesktopNav() {
        window.clearTimeout(this.desktopNavCloseTimer);
        if (window.innerWidth > 820) this.desktopNavOpen = true;
      },
      scheduleDesktopNavClose() {
        window.clearTimeout(this.desktopNavCloseTimer);
        this.desktopNavCloseTimer = window.setTimeout(() => { this.desktopNavOpen = false; }, 260);
      },
      applyTheme() {
        const root = document.getElementById('app');
        root?.classList.toggle('is-dark', this.isDark);
        document.documentElement.style.colorScheme = this.isDark ? 'dark' : 'light';
        localStorage.setItem('amcTheme', this.isDark ? 'dark' : 'light');
      },
      async login() {
        this.loginLoading = true;
        try {
          const response = await api.request('POST', '/api/auth/login', this.loginForm);
          if (response.code) return this.notify(response.message, 'error');
          this.session = response.data;
          const loaded = await this.loadWorkspace();
          if (loaded) this.notify('登录成功，欢迎进入 AMC 工作台', 'success');
        } finally { this.loginLoading = false; }
      },
      async restoreSession() {
        if (!api.getStoredToken()) { this.session = { token: '', realName: '', role: '' }; return; }
        const response = await api.request('GET', '/api/auth/me');
        if (response.code) {
          api.clearSession(); this.session = { token: '', realName: '', role: '' }; return;
        }
        this.session = { token: api.getStoredToken(), ...response.data };
        await this.loadWorkspace();
      },
      async loadWorkspace() {
        this.workspaceLoading = true;
        const response = await api.hydrate();
        this.workspaceLoading = false;
        if (response.code) {
          this.apiOnline = false;
          this.notify(response.message, 'error');
          return false;
        }
        this.apiOnline = true;
        this.refreshCollections('customers', 'projects', 'cleanrooms', 'schemes', 'pollutants', 'standards', 'calcResults', 'reportRecords', 'backupRecords', 'operationLogs');
        const current = this.activeSchemes.find((item) => item.id === this.currentSchemeId) || this.activeSchemes[0];
        if (current) this.loadScheme(current);
        else this.newScheme(false);
        return true;
      },
      async logout() {
        await api.request('POST', '/api/auth/logout'); api.clearSession(); api.reset();
        this.refreshCollections('customers', 'projects', 'cleanrooms', 'schemes', 'pollutants', 'standards', 'calcResults', 'reportRecords', 'backupRecords', 'operationLogs');
        this.apiOnline = false; this.currentSchemeId = null; this.form = defaultForm();
        this.session = { token: '', realName: '', role: '' };
      },
      switchView(key) { this.view = key; this.mobileNavOpen = false; if (key === 'compare') this.compareSchemes(); },
      format(value, digits = 4) { return Number.isFinite(Number(value)) ? Number(value).toFixed(digits) : '—'; },
      pct(value) { return `${Math.round(Number(value) * 100)}%`; },
      unitLabel(unit) { return unit === 'ppb' ? 'ppb' : 'μg/m³'; },
      conclusionLabel(value) { return ({ pass: '达标', fail: '未达标', no_standard: '无标准', not_converged: '未收敛', error: '计算异常' })[value] || '待计算'; },
      tagType(value) { return ({ pass: 'success', fail: 'danger', no_standard: 'info', not_converged: 'warning', error: 'danger' })[value] || 'info'; },
      cleanroomName(id) { return this.db.cleanrooms.find((item) => item.id === Number(id))?.name || '未选择'; },
      schemeName(id) { return this.db.schemes.find((item) => item.id === Number(id))?.name || `方案 ${id}`; },
      pollutantName(id) { return this.db.pollutants.find((item) => item.id === Number(id))?.name || '未知'; },
      nodeText(key) { return `${this.format(this.latestResult?.nodes?.[key], 4)} ${this.unitLabel(this.latestResult?.unit)}`; },
      notify(message, type = 'info') { ElementPlus.ElMessage({ message, type, duration: 2400 }); },
      refreshCollections(...names) { names.forEach((name) => { this.db[name] = [...api.db[name]]; }); },
      filterSimulationPollutants(query) { this.simulationPollutantKeyword = String(query || ''); },
      pollutantOptionLabel(item) { return item.cas ? `${item.name} · ${item.cas}` : item.name; },
      syncRatio() { this.alphaPercent = Math.max(0, Math.min(100, Number(this.alphaPercent || 0))); },
      syncPollutant() {
        this.simulationPollutantKeyword = '';
        const item = this.db.pollutants.find((p) => p.id === this.form.stdPollutantId);
        if (item) this.form.molarMassM = item.molarMassM;
        const standard = this.db.standards.find((row) => row.pollutantId === this.form.stdPollutantId);
        if (standard) {
          this.form.stdSource = standard.sourceType;
          this.form.stdLibraryId = standard.id;
          this.form.targetValue = standard.targetValue;
        } else {
          this.form.stdSource = 'manual';
          this.form.stdLibraryId = null;
          this.form.targetValue = null;
        }
      },
      syncInput() {
        this.form.input.alpha = Number(this.alphaPercent) / 100; this.form.input.beta = this.betaPercent / 100;
        Object.keys(this.filterValues).forEach((key) => { this.form.input[key] = Number(this.filterValues[key]) / 100; });
      },
      loadScheme(scheme) {
        this.form = clone(scheme); this.currentSchemeId = scheme.id; this.alphaPercent = Math.round(scheme.input.alpha * 100);
        Object.keys(this.filterValues).forEach((key) => { this.filterValues[key] = Math.round(scheme.input[key] * 100); });
      },
      openScheme(scheme) { this.loadScheme(scheme); this.view = 'simulation'; },
      newScheme(changeView = true) {
        this.form = defaultForm(this.activeCleanrooms[0]?.id || null, this.db.pollutants[0]?.id || null);
        if (this.db.pollutants[0]?.molarMassM) this.form.molarMassM = this.db.pollutants[0].molarMassM;
        if (this.form.stdPollutantId) this.syncPollutant();
        this.currentSchemeId = null; this.alphaPercent = 30;
        this.filterValues = { etaMau: 72, covMau: 100, etaCeil: 55, covCeil: 92, etaAru: 35, covAru: 80 };
        if (changeView) this.view = 'simulation';
      },
      resetDemo() {
        const scheme = this.activeSchemes[0];
        if (scheme) { this.loadScheme(scheme); this.notify('已恢复已保存的方案参数'); }
        else { this.newScheme(); this.notify('当前尚无已保存方案', 'warning'); }
      },
      async saveScheme(showToast = true) {
        this.validationMessage = ''; this.syncInput();
        if (this.form.stdSource === 'manual') this.form.stdLibraryId = null;
        else {
          const standard = this.db.standards.find((row) => row.pollutantId === this.form.stdPollutantId && row.sourceType === this.form.stdSource);
          this.form.stdLibraryId = standard?.id || null;
          if (standard) this.form.targetValue = standard.targetValue;
        }
        const method = this.currentSchemeId ? 'PUT' : 'POST'; const path = this.currentSchemeId ? `/api/schemes/${this.currentSchemeId}` : '/api/schemes';
        const response = await api.request(method, path, this.form);
        if (response.code) { this.validationMessage = response.message; this.notify(response.message, 'error'); return false; }
        this.refreshCollections('schemes'); this.loadScheme(response.data); if (showToast) this.notify('方案已保存', 'success'); return true;
      },
      async runCalculation() {
        this.calculating = true;
        try {
          const saved = await this.saveScheme(false);
          if (!saved) return;
          const response = await api.request('POST', `/api/schemes/${this.currentSchemeId}/calc`);
          if (response.code) { this.validationMessage = response.message; return this.notify(response.message, 'error'); }
          await api.refreshSupporting();
          this.refreshCollections('calcResults', 'reportRecords', 'operationLogs');
          this.resultTab = 'chart'; this.notify(`计算完成，共迭代 ${response.data.iterCount} 次`, 'success');
        } finally { this.calculating = false; }
      },
      async copyScheme(id) { const response = await api.request('POST', `/api/schemes/${id}/copy`); if (!response.code) { this.refreshCollections('schemes'); this.loadScheme(response.data); this.notify('方案副本已创建', 'success'); } },
      async deleteScheme(id) {
        const response = await api.request('DELETE', `/api/schemes/${id}`);
        if (!response.code) {
          this.refreshCollections('schemes');
          if (Number(id) === Number(this.currentSchemeId)) {
            const next = this.activeSchemes[0]; if (next) this.loadScheme(next); else this.newScheme(false);
          }
          this.notify('方案已逻辑删除', 'success');
        }
      },
      async compareSchemes() {
        const calculated = new Set(this.db.calcResults.map((item) => Number(item.schemeId)));
        const base = this.activeSchemes.find((item) => calculated.has(Number(item.id)));
        const candidates = base ? this.activeSchemes.filter((item) => item.cleanroomId === base.cleanroomId && calculated.has(Number(item.id))).slice(0, 5) : [];
        if (!candidates.length) { this.compareResult = { schemes: [] }; return; }
        const response = await api.request('POST', '/api/schemes/compare', { schemeIds: candidates.map((item) => item.id) });
        if (!response.code) this.compareResult = response.data; else this.notify(response.message, 'error');
      },
      importPollutantExcel() {
        const input = document.createElement('input');
        input.type = 'file'; input.accept = '.xlsx';
        input.addEventListener('change', async () => {
          const file = input.files?.[0]; if (!file) return;
          this.importingPollutants = true;
          try {
            const response = await api.uploadPollutants(file);
            if (response.code) return this.notify(response.message, 'error');
            this.refreshCollections('pollutants');
            this.syncPollutant();
            const data = response.data;
            this.notify(`导入完成：${data.uniqueRows} 条污染物，合并 ${data.duplicateRows} 条重复项`, 'success');
          } finally { this.importingPollutants = false; }
        }, { once: true });
        input.click();
      },
      comparePercent(value) { const max = Math.max(...this.compareResult.schemes.map((item) => item.cr), 1); return Math.round((Number(value) / max) * 100); },
      exportCsv() {
        const rows = [['报告编号', '方案', '计算结果ID', '结论', '生成时间', '操作人'], ...this.db.reportRecords.map((r) => [r.name, this.schemeName(r.schemeId), r.calcResultId, this.conclusionLabel(r.conclusion), r.createdAt, r.createdBy])];
        const csv = '\ufeff' + rows.map((row) => row.map((cell) => `"${String(cell).replaceAll('"', '""')}"`).join(',')).join('\r\n');
        const link = document.createElement('a'); link.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' })); link.download = 'AMC计算报告记录.csv'; link.click(); URL.revokeObjectURL(link.href);
      },
      printReport() { window.print(); }
    },
    mounted() { this.applyTheme(); this.restoreSession(); this.$nextTick(() => this.setupAirflowVisual()); },
    updated() { this.setupAirflowVisual(); }
  });

  app.use(ElementPlus, { locale: window.ElementPlusLocaleZhCn });
  app.mount('#app');
})();
