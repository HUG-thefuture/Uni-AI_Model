/* global $ */
(function () {
  'use strict';
  const config = window.PortalConfig = Object.assign({ apiBase: 'http://127.0.0.1:8000', demoMode: false, loginUrl: 'auth.html' }, window.PortalConfig || {});
  let mode = 'login';
  function setError(message) { $('#auth-error').text(message || '').prop('hidden', !message); }
  function setBusy(busy) { $('#auth-submit').prop('disabled', busy).text(busy ? '正在提交…' : (mode === 'login' ? '登录并进入门户' : '创建账号')); }
  function setMode(nextMode) { const registering = nextMode === 'register'; mode = nextMode; $('#auth-title').text(registering ? '创建你的账号' : '欢迎回来'); $('#auth-subtitle').text(registering ? '完成后可使用统一门户中的创作工具。' : '登录后即可继续你的创作任务。'); $('.auth-register-only').prop('hidden', !registering); $('#auth-password').attr('autocomplete', registering ? 'new-password' : 'current-password'); $('#auth-password-confirm').prop('required', registering); $('#auth-submit').text(registering ? '创建账号' : '登录并进入门户'); $('#auth-switch-label').text(registering ? '已有账号？' : '还没有账号？'); $('#auth-switch').text(registering ? '返回登录' : '创建账号'); setError(''); }
  function setAuthChannel(channel) { const password = channel === 'password'; $('#password-tab').toggleClass('active', password).attr('aria-selected', String(password)); $('#sms-tab').toggleClass('active', !password).attr('aria-selected', String(!password)); $('#password-pane').prop('hidden', !password); $('#sms-pane').prop('hidden', password); if (password) $('#auth-username').trigger('focus'); }
  function returnToPortal() { const target = new URLSearchParams(location.search).get('return_to') || 'index.html'; try { const parsed = new URL(target, location.href); const page = parsed.pathname.split('/').pop(); return parsed.origin === location.origin && ['index.html', 'models.html', 'chat.html', 'image.html', 'audio.html', 'video.html', 'tasks.html', 'profile.html'].includes(page) ? target : 'index.html'; } catch (error) { return 'index.html'; } }
  function submitForm(event) { event.preventDefault();
      const username = String($('#auth-username').val() || '').trim(); const password = String($('#auth-password').val() || '');
      const nickname = String($('#auth-nickname').val() || '').trim(); const school = String($('#auth-school').val() || '').trim();
      const confirm = String($('#auth-password-confirm').val() || '');
      if (!/^[A-Za-z0-9_]{3,32}$/.test(username))
          return setError('用户名需为3-32位字母、数字或下划线。');
      if (password.length < 8 || password.length > 64)
          return setError('密码长度应为8-64位。');
      if (mode === 'register' && password !== confirm)
          return setError('两次输入的密码不一致。');
      if (config.demoMode)
          return setError('当前是演示模式，未连接真实认证服务。请在联调配置中关闭 demoMode 后使用账号密码登录。');
      setError('');
      setBusy(true);
      const request = mode === 'register' ? window.PortalApi.register({ username, password, nickname: nickname || null, school: school || null }) :
          window.PortalApi.login({ username, password }); request.then(data => { if (mode === 'register') { setMode('login'); $('#auth-username').val(username); $('#auth-password').val('').trigger('focus'); $('#auth-subtitle').text('账号创建成功，请使用新账号登录。'); return; }
          if (!data || !data.token) throw new Error('登录响应未包含有效令牌。'); const persistent = $('#auth-remember').prop('checked');
      window.PortalApi.setToken(data.token, persistent);
      window.PortalApi.setCurrentUser(data.user, persistent);
      window.location.assign(returnToPortal()); }).catch(error => setError(error && error.message ? error.message : '提交失败，请稍后再试。')).finally(() => setBusy(false)); }
  $(function () { $('#auth-form').on('submit', submitForm); $('#auth-switch').on('click', () => setMode(mode === 'login' ? 'register' : 'login')); $('#password-tab, [data-return-password]').on('click', () => setAuthChannel('password')); $('#sms-tab').on('click', () => setAuthChannel('sms')); $('[data-toggle-password]').on('click', function () { const input = $(`#${$(this).data('toggle-password')}`); const hidden = input.attr('type') === 'password'; input.attr('type', hidden ? 'text' : 'password'); $(this).attr('aria-label', hidden ? '隐藏密码' : '显示密码'); }); });
}());
