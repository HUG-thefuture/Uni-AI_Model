/* global $ */
(function () {
  'use strict';
  const config = window.PortalConfig = Object.assign({ apiBase: 'http://127.0.0.1:8000', demoMode: false, loginUrl: 'auth.html' }, window.PortalConfig || {});
  const SMS_PHONE_PATTERN = /^1[3-9]\d{9}$/;
  let mode = 'login';
  let smsCooldownLeft = 0;
  let smsCooldownTimer = null;
  function setError(message) { $('#auth-error').text(message || '').prop('hidden', !message); }
  function setBusy(busy) { $('#auth-submit').prop('disabled', busy).text(busy ? '正在提交…' : (mode === 'login' ? '登录并进入门户' : '创建账号')); }
  function setMode(nextMode) { const registering = nextMode === 'register'; mode = nextMode; $('#auth-title').text(registering ? '创建你的账号' : '欢迎回来'); $('#auth-subtitle').text(registering ? '完成后可使用统一门户中的创作工具。' : '登录后即可继续你的创作任务。'); $('.auth-register-only').prop('hidden', !registering); $('#auth-password').attr('autocomplete', registering ? 'new-password' : 'current-password'); $('#auth-password-confirm').prop('required', registering); $('#auth-submit').text(registering ? '创建账号' : '登录并进入门户'); $('#auth-switch-label').text(registering ? '已有账号？' : '还没有账号？'); $('#auth-switch').text(registering ? '返回登录' : '创建账号'); setError(''); }
  function setAuthChannel(channel) { const password = channel === 'password'; $('#password-tab').toggleClass('active', password).attr('aria-selected', String(password)); $('#sms-tab').toggleClass('active', !password).attr('aria-selected', String(!password)); $('#password-pane').prop('hidden', !password); $('#sms-pane').prop('hidden', password); if (password) $('#auth-username').trigger('focus'); else $('#sms-phone').trigger('focus'); }
  function returnToPortal() { const target = new URLSearchParams(location.search).get('return_to') || 'index.html'; try { const parsed = new URL(target, location.href); const page = parsed.pathname.split('/').pop(); return parsed.origin === location.origin && ['index.html', 'models.html', 'chat.html', 'image.html', 'audio.html', 'video.html', 'tasks.html', 'profile.html'].includes(page) ? target : 'index.html'; } catch (error) { return 'index.html'; } }
  function completeLogin(data) { if (!data || !data.token) throw new Error('登录响应未包含有效令牌。'); const persistent = $('#auth-remember').prop('checked'); window.PortalApi.setToken(data.token, persistent); window.PortalApi.setCurrentUser(data.user, persistent); window.location.assign(returnToPortal()); }
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
          completeLogin(data); }).catch(error => setError(error && error.message ? error.message : '提交失败，请稍后再试。')).finally(() => setBusy(false)); }

  // ===== 短信验证码登录 =====
  function setSmsError(message) { $('#sms-error').text(message || '').prop('hidden', !message); }
  function setSmsBusy(busy) { $('#sms-submit').prop('disabled', busy).text(busy ? '正在登录…' : '登录并进入门户'); }
  function stopSmsCooldown() { if (smsCooldownTimer) { clearInterval(smsCooldownTimer); smsCooldownTimer = null; } smsCooldownLeft = 0; $('#sms-send-btn').prop('disabled', false).text('获取验证码'); }
  function startSmsCooldown(seconds) { stopSmsCooldown(); smsCooldownLeft = seconds > 0 ? seconds : 60; const button = $('#sms-send-btn').prop('disabled', true); const render = () => button.text(`${smsCooldownLeft} s 后重发`); render(); smsCooldownTimer = setInterval(() => { smsCooldownLeft -= 1; if (smsCooldownLeft <= 0) stopSmsCooldown(); else render(); }, 1000); }
  function sendSmsCode() {
      const phone = String($('#sms-phone').val() || '').trim();
      if (!SMS_PHONE_PATTERN.test(phone)) return setSmsError('请输入正确的11位手机号。');
      if (config.demoMode) return setSmsError('当前是演示模式，未连接真实认证服务。请在联调配置中关闭 demoMode 后使用短信登录。');
      setSmsError('');
      $('#sms-send-btn').prop('disabled', true).text('发送中…');
      window.PortalApi.request({ url: '/api/auth/sms/send', method: 'POST', data: { phone, purpose: 'login' }, auth: false })
          .then(data => { if (data && data.debug_code) $('#sms-debug-hint').text(`开发模式验证码：${data.debug_code}（已回显，未自动填入）`).prop('hidden', false); startSmsCooldown(data && data.cooldown ? Number(data.cooldown) : 60); })
          .catch(error => { setSmsError(error && error.message ? error.message : '验证码发送失败，请稍后再试。'); stopSmsCooldown(); });
  }
  function submitSmsForm(event) {
      event.preventDefault();
      const phone = String($('#sms-phone').val() || '').trim();
      const code = String($('#sms-code').val() || '').trim();
      if (!SMS_PHONE_PATTERN.test(phone)) return setSmsError('请输入正确的11位手机号。');
      if (!/^\d{6}$/.test(code)) return setSmsError('请输入6位数字验证码。');
      if (config.demoMode) return setSmsError('当前是演示模式，未连接真实认证服务。请在联调配置中关闭 demoMode 后使用短信登录。');
      setSmsError('');
      setSmsBusy(true);
      window.PortalApi.request({ url: '/api/auth/sms/login', method: 'POST', data: { phone, code }, auth: false })
          .then(data => completeLogin(data))
          .catch(error => setSmsError(error && error.message ? error.message : '登录失败，请稍后再试。'))
          .finally(() => setSmsBusy(false));
  }
  $(function () { $('#auth-form').on('submit', submitForm); $('#auth-switch').on('click', () => setMode(mode === 'login' ? 'register' : 'login')); $('#password-tab, [data-return-password]').on('click', () => setAuthChannel('password')); $('#sms-tab').on('click', () => setAuthChannel('sms')); $('#sms-form').on('submit', submitSmsForm); $('#sms-send-btn').on('click', sendSmsCode); $('#sms-phone').on('input', () => $('#sms-debug-hint').prop('hidden', true)); $('[data-toggle-password]').on('click', function () { const input = $(`#${$(this).data('toggle-password')}`); const hidden = input.attr('type') === 'password'; input.attr('type', hidden ? 'text' : 'password'); $(this).attr('aria-label', hidden ? '隐藏密码' : '显示密码'); }); });
}());
