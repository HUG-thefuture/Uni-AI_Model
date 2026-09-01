/* global $ */
(function () {
  'use strict';

  const config = window.PortalConfig = Object.assign({
    apiBase: 'http://127.0.0.1:8000',
    demoMode: false,
    tokenKey: 'ai_portal_token',
    loginUrl: 'auth.html'
  }, window.PortalConfig || {});

  function token() {
    return sessionStorage.getItem(config.tokenKey) || localStorage.getItem(config.tokenKey) || '';
  }

  function clearToken() {
    sessionStorage.removeItem(config.tokenKey);
    localStorage.removeItem(config.tokenKey);
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
    updateProfile(payload) {
      return request({ url: '/api/user/profile', method: 'PUT', data: payload });
    },
    models(params) {
      return request({ url: `/api/models${params ? `?${$.param(params)}` : ''}` });
    },
    task(type, payload) {
      return request({ url: `/api/tasks/${type}`, method: 'POST', data: payload, timeout: type === 'text' ? 120000 : 30000 });
    },
    taskDetail(id) {
      return request({ url: `/api/tasks/${encodeURIComponent(id)}` });
    }
  };
}());
