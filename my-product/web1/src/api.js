(function () {
  'use strict';

  const TOKEN_KEY = 'amcAccessToken';
  const API_BASE = String(
    window.AMC_API_BASE_URL || localStorage.getItem('amcApiBaseUrl') || 'http://127.0.0.1:8000'
  ).replace(/\/$/, '');
  const collectionNames = [
    'customers', 'projects', 'cleanrooms', 'schemes', 'pollutants', 'standards',
    'calcResults', 'reportRecords', 'backupRecords', 'operationLogs'
  ];
  const db = Object.fromEntries(collectionNames.map((name) => [name, []]));

  function failure(message, code = 5000, data = null) {
    return { code, message, data, requestId: `web_${Date.now()}` };
  }

  function upsert(collection, item) {
    const index = collection.findIndex((row) => Number(row.id) === Number(item.id));
    if (index === -1) collection.unshift(item);
    else collection.splice(index, 1, item);
  }

  async function request(method, path, body) {
    const headers = { Accept: 'application/json' };
    const token = localStorage.getItem(TOKEN_KEY);
    if (token) headers.Authorization = `Bearer ${token}`;
    if (body !== undefined) headers['Content-Type'] = 'application/json';

    try {
      const response = await fetch(`${API_BASE}${path}`, {
        method,
        headers,
        body: body === undefined ? undefined : JSON.stringify(body)
      });
      let payload;
      try {
        payload = await response.json();
      } catch (_error) {
        return failure(`后端返回了无法解析的响应（HTTP ${response.status}）`);
      }
      if (!payload || typeof payload.code !== 'number') {
        return failure(`后端响应格式不符合接口约定（HTTP ${response.status}）`);
      }
      if (path === '/api/auth/login' && payload.code === 0 && payload.data?.token) {
        localStorage.setItem(TOKEN_KEY, payload.data.token);
      }
      if ((response.status === 401 || payload.code === 1002) && path !== '/api/auth/login') {
        localStorage.removeItem(TOKEN_KEY);
      }
      if (payload.code === 0) applyMutation(method, path, payload.data);
      return payload;
    } catch (_error) {
      return failure(`无法连接后端服务 ${API_BASE}，请确认 FastAPI 已启动`);
    }
  }

  function applyMutation(method, path, data) {
    if (!data) return;
    if ((method === 'POST' && path === '/api/schemes') || method === 'PUT' && /^\/api\/schemes\/\d+$/.test(path)) {
      upsert(db.schemes, data);
    } else if (method === 'POST' && /^\/api\/schemes\/\d+\/copy$/.test(path)) {
      upsert(db.schemes, data);
    } else if (method === 'DELETE' && /^\/api\/schemes\/\d+$/.test(path)) {
      const id = Number(path.split('/')[3]);
      const row = db.schemes.find((item) => Number(item.id) === id);
      if (row) row.deleted = true;
    } else if (method === 'POST' && /^\/api\/schemes\/\d+\/calc$/.test(path)) {
      upsert(db.calcResults, data);
      db.calcResults.sort((a, b) => String(b.calcTime).localeCompare(String(a.calcTime)) || b.id - a.id);
    }
  }

  async function requireData(path) {
    const response = await request('GET', path);
    if (response.code !== 0) throw new Error(response.message);
    return response.data;
  }

  async function refreshSupporting() {
    try {
      const [operationLogs, reportRecords, backupRecords] = await Promise.all([
        requireData('/api/operation-logs'), requireData('/api/reports'), requireData('/api/backups')
      ]);
      db.operationLogs = operationLogs;
      db.reportRecords = reportRecords;
      db.backupRecords = backupRecords;
      return { code: 0, message: 'success', data: db };
    } catch (error) {
      return failure(error.message);
    }
  }

  async function hydrate() {
    try {
      const [customers, projects, cleanrooms, pollutants, standards] = await Promise.all([
        requireData('/api/customers'), requireData('/api/projects'), requireData('/api/cleanrooms'),
        requireData('/api/pollutants'), requireData('/api/standards')
      ]);
      const schemeLists = await Promise.all(
        cleanrooms.map((room) => requireData(`/api/cleanrooms/${room.id}/schemes`))
      );
      const schemes = schemeLists.flat();
      const resultLists = await Promise.all(
        schemes.map((scheme) => requireData(`/api/schemes/${scheme.id}/results`))
      );
      const latestResults = await Promise.all(
        schemes.map((scheme, index) => resultLists[index].length
          ? requireData(`/api/schemes/${scheme.id}/result`)
          : Promise.resolve(null))
      );
      const results = resultLists.flat();
      latestResults.filter(Boolean).forEach((item) => upsert(results, item));
      db.customers = customers;
      db.projects = projects;
      db.cleanrooms = cleanrooms;
      db.pollutants = pollutants;
      db.standards = standards;
      db.schemes = schemes;
      db.calcResults = results.sort(
        (a, b) => String(b.calcTime).localeCompare(String(a.calcTime)) || b.id - a.id
      );
      const supporting = await refreshSupporting();
      if (supporting.code !== 0) return supporting;
      return { code: 0, message: 'success', data: db };
    } catch (error) {
      return failure(error.message);
    }
  }

  async function uploadPollutants(file) {
    const token = localStorage.getItem(TOKEN_KEY);
    const headers = {
      Accept: 'application/json',
      'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    };
    if (token) headers.Authorization = `Bearer ${token}`;
    try {
      const response = await fetch(
        `${API_BASE}/api/pollutants/import?filename=${encodeURIComponent(file.name)}`,
        { method: 'POST', headers, body: file }
      );
      const payload = await response.json();
      if (response.status === 401 || payload.code === 1002) localStorage.removeItem(TOKEN_KEY);
      if (payload.code === 0) db.pollutants = await requireData('/api/pollutants');
      return payload;
    } catch (_error) {
      return failure(`无法连接后端服务 ${API_BASE}，请确认 FastAPI 已启动`);
    }
  }

  function clearSession() {
    localStorage.removeItem(TOKEN_KEY);
  }

  function reset() {
    collectionNames.forEach((name) => { db[name] = []; });
  }

  window.AMCApi = {
    baseUrl: API_BASE,
    db,
    request,
    hydrate,
    refreshSupporting,
    uploadPollutants,
    getStoredToken: () => localStorage.getItem(TOKEN_KEY) || '',
    clearSession,
    reset
  };
})();
