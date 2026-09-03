/* global $ */
(function () {
  'use strict';

  const config = window.PortalConfig = Object.assign({
    apiBase: 'http://127.0.0.1:8000',
    demoMode: false,
    tokenKey: 'ai_portal_token',
    userKey: 'ai_portal_user',
    loginUrl: 'auth.html'
  }, window.PortalConfig || {});

  function token() {
    return sessionStorage.getItem(config.tokenKey) || localStorage.getItem(config.tokenKey) || '';
  }

  function clearUserSnapshot() {
    sessionStorage.removeItem(config.userKey);
    localStorage.removeItem(config.userKey);
  }

  function currentUserSnapshot() {
    try {
      const raw = sessionStorage.getItem(config.userKey) || localStorage.getItem(config.userKey) || '';
      const value = raw ? JSON.parse(raw) : null;
      return value && typeof value === 'object' ? value : null;
    } catch (error) {
      clearUserSnapshot();
      return null;
    }
  }

  function setCurrentUser(value, persistent) {
    if (!value || typeof value !== 'object') return;
    clearUserSnapshot();
    (persistent ? localStorage : sessionStorage).setItem(config.userKey, JSON.stringify(value));
  }

  function clearToken() {
    sessionStorage.removeItem(config.tokenKey);
    localStorage.removeItem(config.tokenKey);
    clearUserSnapshot();
  }

  function notifyUnauthorized(detail) {
    window.dispatchEvent(new CustomEvent('portal:unauthorized', { detail: detail || {} }));
    if (!config.demoMode && config.loginUrl) {
      const returnTo = `${location.pathname}${location.hash}`;
      const separator = config.loginUrl.includes('?') ? '&' : '?';
      location.assign(`${config.loginUrl}${separator}return_to=${encodeURIComponent(returnTo)}`);
    }
  }

  function errorMessage(status, fallback) {
    const messages = {
      400: '提交内容不符合要求，请检查后重试。',
      401: '登录状态已失效，请重新登录。',
      403: '当前账号没有执行此操作的权限。',
      404: '请求的内容不存在或已被移除。',
      409: '数据状态已发生变化，请刷新后重试。',
      429: '操作过于频繁，请稍后再试。',
      500: '服务暂时不可用，请稍后重试。'
    };
    return fallback || messages[status] || (status === 0 ? '无法连接后端服务，请检查网络和服务地址。' : '请求失败，请稍后重试。');
  }

  function request(options) {
    const settings = Object.assign({ method: 'GET', data: null, auth: true }, options || {});
    const headers = Object.assign({ 'X-Requested-With': 'XMLHttpRequest' }, settings.headers || {});
    const currentToken = token();

    if (settings.auth && currentToken) headers.Authorization = `Bearer ${currentToken}`;

    return new Promise((resolve, reject) => {
      $.ajax({
        url: `${config.apiBase}${settings.url}`,
        method: settings.method,
        headers,
        data: settings.data == null ? undefined : JSON.stringify(settings.data),
        contentType: settings.data == null ? undefined : 'application/json; charset=UTF-8',
        dataType: 'json',
        timeout: settings.timeout || 30000
      }).done(response => {
        if (response && response.code === 0) {
          resolve(response.data);
          return;
        }
        reject({
          status: 200,
          code: response && response.code,
          message: response && response.message ? response.message : '接口返回格式不符合约定',
          requestId: response && response.request_id
        });
      }).fail(xhr => {
        const response = xhr.responseJSON || {};
        if (xhr.status === 401) {
          clearToken();
          notifyUnauthorized({ requestId: response.request_id });
        }
        reject({
          status: xhr.status || 0,
          code: response.code,
          message: errorMessage(xhr.status, response.message),
          requestId: response.request_id
        });
      });
    });
  }

  window.PortalApi = {
    config,
    request,
    token,
    clearToken,
    currentUserSnapshot,
    setCurrentUser,
    isDemo() {
      return Boolean(config.demoMode);
    },
    ensureAuthenticated() {
      if (config.demoMode || token()) return true;
      notifyUnauthorized();
      return false;
    },
    setToken(value, persistent) {
      clearToken();
      (persistent ? localStorage : sessionStorage).setItem(config.tokenKey, value);
    },
    register(payload) {
      return request({ url: '/api/auth/register', method: 'POST', data: payload, auth: false });
    },
    login(payload) {
      return request({ url: '/api/auth/login', method: 'POST', data: payload, auth: false });
    },
    logout() {
      return request({ url: '/api/auth/logout', method: 'POST' });
    },
    health() {
      return request({ url: '/api/health', auth: false, timeout: 5000 });
    },
    currentUser() {
      return request({ url: '/api/auth/me' });
    },
    wallet() {
      return request({ url: '/api/wallet/me' });
    },
    walletRecords(params) {
      return request({ url: `/api/wallet/records${params ? `?${$.param(params)}` : ''}` });
    },
    recharge(payload) {
      return request({ url: '/api/wallet/recharge', method: 'POST', data: payload });
    },
    invoices(params) {
      return request({ url: `/api/wallet/invoices${params ? `?${$.param(params)}` : ''}` });
    },
    createInvoice(payload) {
      return request({ url: '/api/wallet/invoices', method: 'POST', data: payload });
    },
    updateProfile(payload) {
      return request({ url: '/api/user/profile', method: 'PUT', data: payload });
    },
    models(params) {
      return request({ url: `/api/models${params ? `?${$.param(params)}` : ''}` });
    },
    chatSession(payload) {
      return request({ url: '/api/chat/sessions', method: 'POST', data: payload });
    },
    streamText(payload, onEvent) {
      const currentToken = token();
      const headers = { 'Content-Type': 'application/json', Accept: 'text/event-stream' };
      if (currentToken) headers.Authorization = `Bearer ${currentToken}`;
      return fetch(`${config.apiBase}/api/tasks/text`, {
        method: 'POST', headers, body: JSON.stringify(payload)
      }).then(async response => {
        if (!response.ok) {
          let body = {};
          try { body = await response.json(); } catch (error) { /* 保留统一错误提示 */ }
          if (response.status === 401) { clearToken(); notifyUnauthorized({ requestId: body.request_id }); }
          throw { status: response.status, code: body.code, message: errorMessage(response.status, body.message), requestId: body.request_id };
        }
        if (!response.body) throw { message: '浏览器不支持流式响应，请升级浏览器后重试。' };
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let pending = '';
        while (true) {
          const chunk = await reader.read();
          if (chunk.done) break;
          pending += decoder.decode(chunk.value, { stream: true });
          const frames = pending.split('\n\n');
          pending = frames.pop();
          for (const frame of frames) {
            const line = frame.split('\n').find(item => item.startsWith('data:'));
            if (!line) continue;
            let event;
            try { event = JSON.parse(line.slice(5).trim()); } catch (error) { continue; }
            if (event.error) throw { code: event.error.code, message: event.error.message || '模型生成失败。' };
            onEvent(event);
          }
        }
        if (pending.trim()) {
          const line = pending.split('\n').find(item => item.startsWith('data:'));
          if (line) {
            const event = JSON.parse(line.slice(5).trim());
            if (event.error) throw { code: event.error.code, message: event.error.message || '模型生成失败。' };
            onEvent(event);
          }
        }
      });
    },
    task(type, payload) {
      return request({ url: `/api/tasks/${type}`, method: 'POST', data: payload, timeout: type === 'text' ? 120000 : 30000 });
    },
    upload(file) {
      const currentToken = token();
      const headers = {};
      if (currentToken) headers.Authorization = `Bearer ${currentToken}`;
      const form = new FormData();
      form.append('file', file);
      return new Promise((resolve, reject) => {
        $.ajax({
          url: `${config.apiBase}/api/uploads`, method: 'POST', headers, data: form,
          processData: false, contentType: false, dataType: 'json', timeout: 60000
        }).done(response => {
          if (response && response.code === 0) return resolve(response.data);
          reject({ status: 200, message: response && response.message ? response.message : '上传接口返回格式不符合约定' });
        }).fail(xhr => {
          const response = xhr.responseJSON || {};
          if (xhr.status === 401) { clearToken(); notifyUnauthorized({ requestId: response.request_id }); }
          reject({ status: xhr.status || 0, message: errorMessage(xhr.status, response.message) });
        });
      });
    },
    taskList(params) {
      return request({ url: `/api/tasks` + (params ? `?${$.param(params)}` : '') });
    },
    taskDetail(id) {
      return request({ url: `/api/tasks/${encodeURIComponent(id)}` });
    },
    taskRetry(id) {
      return request({ url: `/api/tasks/${encodeURIComponent(id)}/retry`, method: 'POST' });
    },

    // ===== 个人中心 · 用量统计 =====
    usageStats() {
      return request({ url: '/api/stats/usage' });
    },

    // ===== 个人中心 · API Key 管理 =====
    apiKeys() {
      return request({ url: '/api/api_keys' });
    },
    createApiKey(payload) {
      return request({ url: '/api/api_keys', method: 'POST', data: payload });
    },
    updateApiKeyStatus(id, status) {
      return request({ url: `/api/api_keys/${encodeURIComponent(id)}/status`, method: 'PUT', data: { status } });
    },

    // ===== 管理后台 · 用户管理 =====
    adminUsers(params) {
      return request({ url: `/api/admin/users${params ? `?${$.param(params)}` : ''}` });
    },
    adminUserDetail(id) {
      return request({ url: `/api/admin/users/${encodeURIComponent(id)}` });
    },
    adminUpdateUser(id, payload) {
      return request({ url: `/api/admin/users/${encodeURIComponent(id)}`, method: 'PUT', data: payload });
    },
    adminUpdateUserStatus(id, status) {
      return request({ url: `/api/admin/users/${encodeURIComponent(id)}/status`, method: 'PUT', data: { status } });
    },
    adminAdjustBalance(id, amount, reason) {
      return request({ url: `/api/admin/users/${encodeURIComponent(id)}/balance`, method: 'PUT', data: { amount, reason } });
    },
    adminResetPassword(id, password) {
      return request({ url: `/api/admin/users/${encodeURIComponent(id)}/password`, method: 'PUT', data: { password } });
    },
    adminDeleteUser(id) {
      return request({ url: `/api/admin/users/${encodeURIComponent(id)}`, method: 'DELETE' });
    },

    // ===== 管理后台 · 钱包/订单/消费 =====
    adminWallets(params) {
      return request({ url: `/api/admin/wallets${params ? `?${$.param(params)}` : ''}` });
    },
    adminOrders(params) {
      return request({ url: `/api/admin/orders${params ? `?${$.param(params)}` : ''}` });
    },
    adminConsumptions(params) {
      return request({ url: `/api/admin/consumption-records${params ? `?${$.param(params)}` : ''}` });
    },

    // ===== 管理后台 · 发票审核 =====
    adminInvoices(params) {
      return request({ url: `/api/admin/invoices${params ? `?${$.param(params)}` : ''}` });
    },
    adminReviewInvoice(id, status) {
      return request({ url: `/api/admin/invoices/${encodeURIComponent(id)}/status`, method: 'PUT', data: { status } });
    },

    // ===== 管理后台 · 全站统计 =====
    adminUsageStats() {
      return request({ url: '/api/admin/stats/usage' });
    },

    // ===== 管理后台 · 模型管理 =====
    adminModels(params) {
      return request({ url: `/api/admin/models${params ? `?${$.param(params)}` : ''}` });
    },
    adminModelDetail(id) {
      return request({ url: `/api/admin/models/${encodeURIComponent(id)}` });
    },
    adminCreateModel(payload) {
      return request({ url: '/api/admin/models', method: 'POST', data: payload });
    },
    adminUpdateModel(id, payload) {
      return request({ url: `/api/admin/models/${encodeURIComponent(id)}`, method: 'PUT', data: payload });
    },
    adminUpdateModelStatus(id, status) {
      return request({ url: `/api/admin/models/${encodeURIComponent(id)}/status`, method: 'PUT', data: { status } });
    },
    adminDeleteModel(id) {
      return request({ url: `/api/admin/models/${encodeURIComponent(id)}`, method: 'DELETE' });
    },
    adminFetchModels(baseUrl, apiKey) {
      return request({ url: '/api/admin/models/fetch', method: 'POST', data: { base_url: baseUrl, api_key: apiKey } });
    }
  };
}());
