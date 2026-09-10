(function (global) {
  'use strict';

  const now = () => new Date().toLocaleString('zh-CN', { hour12: false });
  const clone = (value) => JSON.parse(JSON.stringify(value));
  const requestId = () => `req_${Date.now()}_${Math.random().toString(16).slice(2, 8)}`;
  const ok = (data, message = 'success') => ({ code: 0, message, data: clone(data), requestId: requestId() });
  const fail = (code, message) => ({ code, message, data: null, requestId: requestId() });

  const baseInput = { c0: 10, g: 1.5, etaMau: 0.72, covMau: 1, etaCeil: 0.55, covCeil: 0.92, etaAru: 0.35, covAru: 0.8, alpha: 0.3, beta: 0.7 };
  const schemes = [
    { id: 1, cleanroomId: 1, name: 'A栋核心区基准方案', version: 1, concUnit: 'ug', molarMassM: 30.03, molarVolumeVm: 24.04, stdSource: 'enterprise', stdPollutantId: 1, targetValue: 3.2, input: clone(baseInput), deleted: false },
    { id: 2, cleanroomId: 1, name: 'MAU增强过滤方案', version: 2, concUnit: 'ug', molarMassM: 30.03, molarVolumeVm: 24.04, stdSource: 'enterprise', stdPollutantId: 1, targetValue: 3.2, input: { ...clone(baseInput), etaMau: 0.88, etaCeil: 0.62 }, deleted: false },
    { id: 3, cleanroomId: 2, name: '回风优化验证方案', version: 1, concUnit: 'ug', molarMassM: 30.03, molarVolumeVm: 24.04, stdSource: 'manual', stdPollutantId: 1, targetValue: 2.5, input: { ...clone(baseInput), etaAru: 0.55, covAru: 0.9, alpha: 0.35, beta: 0.65 }, deleted: false }
  ];

  const db = {
    users: [
      { id: 1, username: 'engineer01', password: 'demo123', realName: '张工', role: 'engineer' },
      { id: 2, username: 'admin', password: 'admin123', realName: '系统管理员', role: 'admin' },
      { id: 3, username: 'viewer', password: 'viewer123', realName: '访客', role: 'viewer' }
    ],
    customers: [{ id: 1, name: '华东芯片制造有限公司', contact: '李经理', deleted: false }, { id: 2, name: '先进材料科技集团', contact: '王工', deleted: false }],
    projects: [{ id: 1, customerId: 1, name: '12英寸晶圆厂 AMC 改造', location: '上海', deleted: false }, { id: 2, customerId: 2, name: '研发中心洁净室验证', location: '苏州', deleted: false }],
    cleanrooms: [{ id: 1, projectId: 1, name: 'A栋核心工艺区', code: 'CR-A01', deleted: false }, { id: 2, projectId: 1, name: 'A栋辅助区', code: 'CR-A02', deleted: false }, { id: 3, projectId: 2, name: '研发洁净室', code: 'CR-R01', deleted: false }],
    schemes,
    pollutants: [{ id: 1, name: '甲醛', formula: 'CH₂O', cas: '50-00-0', molarMassM: 30.03 }, { id: 2, name: '氨', formula: 'NH₃', cas: '7664-41-7', molarMassM: 17.03 }, { id: 3, name: '异丙醇', formula: 'C₃H₈O', cas: '67-63-0', molarMassM: 60.10 }, { id: 4, name: '乙酸', formula: 'C₂H₄O₂', cas: '64-19-7', molarMassM: 60.05 }],
    standards: [{ id: 1, pollutantId: 1, sourceType: 'enterprise', targetValue: 3.2, unit: 'ug', scope: '核心工艺区', version: '2026.1' }, { id: 2, pollutantId: 2, sourceType: 'industry', targetValue: 5, unit: 'ug', scope: '洁净室', version: '2025' }],
    calcResults: [], reportRecords: [], backupRecords: [{ id: 1, name: 'phase1_baseline_20260910', createdAt: '2026/09/10 08:30:00', status: 'success' }],
    operationLogs: [{ id: 1, operator: '系统管理员', action: '完成一期基准数据初始化', createdAt: '2026/09/10 08:30:00' }]
  };

  function calculateScheme(scheme) {
    const result = global.AMCEngine.calculate(scheme);
    const id = db.calcResults.length + 1;
    const record = { id, schemeId: scheme.id, ...result, calcTime: now(), createdBy: '张工' };
    db.calcResults.unshift(record);
    db.reportRecords.unshift({ id, name: `AMC-${new Date().getFullYear()}-${String(id).padStart(4, '0')}`, schemeId: scheme.id, calcResultId: id, conclusion: result.conclusion, createdAt: record.calcTime, createdBy: record.createdBy });
    db.operationLogs.unshift({ id: db.operationLogs.length + 1, operator: record.createdBy, action: `执行方案计算：${scheme.name}`, createdAt: record.calcTime });
    return record;
  }

  schemes.forEach(calculateScheme);

  async function request(method, path, body = {}) {
    await new Promise((resolve) => setTimeout(resolve, 180));
    try {
      if (method === 'POST' && path === '/api/auth/login') {
        const user = db.users.find((item) => item.username === body.username && item.password === body.password);
        return user ? ok({ token: `demo-token-${user.id}`, userId: user.id, realName: user.realName, role: user.role }) : fail(401, '账号或密码错误');
      }
      if (method === 'POST' && path === '/api/auth/logout') return ok(true);
      if (method === 'POST' && path === '/api/schemes') {
        global.AMCEngine.validate(body.input);
        const item = { ...clone(body), id: Math.max(...db.schemes.map((s) => s.id), 0) + 1, version: 1, deleted: false };
        db.schemes.push(item); return ok(item);
      }
      const schemeMatch = path.match(/^\/api\/schemes\/(\d+)$/);
      if (schemeMatch && method === 'PUT') {
        const index = db.schemes.findIndex((s) => s.id === Number(schemeMatch[1]));
        if (index < 0) return fail(404, '方案不存在');
        global.AMCEngine.validate(body.input); db.schemes[index] = { ...db.schemes[index], ...clone(body) }; return ok(db.schemes[index]);
      }
      if (schemeMatch && method === 'DELETE') {
        const item = db.schemes.find((s) => s.id === Number(schemeMatch[1])); if (!item) return fail(404, '方案不存在'); item.deleted = true; return ok(true);
      }
      const copyMatch = path.match(/^\/api\/schemes\/(\d+)\/copy$/);
      if (copyMatch && method === 'POST') {
        const source = db.schemes.find((s) => s.id === Number(copyMatch[1])); if (!source) return fail(404, '方案不存在');
        const copy = clone(source); copy.id = Math.max(...db.schemes.map((s) => s.id)) + 1; copy.name += '（副本）'; copy.version = 1; db.schemes.push(copy); return ok(copy);
      }
      const calcMatch = path.match(/^\/api\/schemes\/(\d+)\/calc$/);
      if (calcMatch && method === 'POST') {
        const scheme = db.schemes.find((s) => s.id === Number(calcMatch[1])); if (!scheme) return fail(404, '方案不存在');
        const result = calculateScheme(scheme); return result.converged ? ok(result) : fail(2001, '在最大迭代次数内未收敛');
      }
      if (method === 'POST' && path === '/api/schemes/compare') {
        if (!Array.isArray(body.schemeIds) || body.schemeIds.length > 3) return fail(1002, '最多选择 3 个方案');
        const result = body.schemeIds.map((id) => { const scheme = db.schemes.find((s) => s.id === id); const calc = db.calcResults.find((r) => r.schemeId === id) || calculateScheme(scheme); return { schemeId: id, name: scheme.name, cr: calc.nodes.cr, conclusion: calc.conclusion, nodes: calc.nodes, input: scheme.input }; });
        return ok({ schemes: result });
      }
      return fail(404, `未实现接口：${method} ${path}`);
    } catch (error) { return fail(error.code || 1001, error.message); }
  }

  global.AMCMockApi = { db, request };
})(window);
