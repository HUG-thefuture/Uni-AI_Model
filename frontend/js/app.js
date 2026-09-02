/* global $ */
(function () {
  'use strict';

  // 联调时由成员2、4提供真实地址；演示模式不会向任何第三方模型厂商发送请求。
  window.PortalConfig = Object.assign({ apiBase: 'http://127.0.0.1:8000', demoMode: false, loginUrl: 'auth.html' }, window.PortalConfig || {});
  const DEMO_STORAGE_KEY = 'ai_portal_demo_state_v1';
  const taskTimers = new Map();
  const routeTitles = {
    home: '首页', models: '模型广场', text: '文本交互舱', image: '图像生成室',
    audio: '声音创作坊', video: '视频合成站', tasks: '创作历史', profile: '个人中心'
  };

  const state = {
    route: '',
    modelType: '全部',
    modelGroup: '全部分组',
    modelSource: '云端模型',
    keyword: '',
    currentChatModel: 'qwen3.7-plus',
    selectedModelIds: { image: null, audio: null, video: null },
    chatSessionId: null,
    chatMessages: [{ role: 'assistant', content: '你好！我是你的 AI 创意助手。你可以让我协助优化文案、解释知识点，或开始一次创作。' }],
    chatHistory: [{ title: '欢迎使用 AI 助手', date: '今天' }],
    imageMode: '文生图',
    imageRatio: '1:1 1024×1024',
    imageHistory: [],
    audioMode: '声音合成',
    selectedVoice: '龙安洋',
    videoDuration: '5秒',
    audioHistory: [],
    videoHistory: [],
    tasks: [],
    busy: { text: false, image: false, audio: false, video: false, profile: false, recharge: false }
  };

  let user = { name: '用户', initial: 'U', balance: '—', school: '未加载学校', realName: '未认证', role: 'user' };
  const navItems = [
    ['home', '首页', 'layui-icon-home'], ['models', '模型广场', 'layui-icon-app'],
    ['text', '文本交互舱', 'layui-icon-dialogue'], ['image', '图像生成室', 'layui-icon-picture'],
    ['audio', '声音创作坊', 'layui-icon-voice'], ['video', '视频合成站', 'layui-icon-video'],
    ['tasks', '创作历史', 'layui-icon-list'], ['profile', '个人中心', 'layui-icon-user']
  ];
  let models = [
    { name: 'qwen3.7-plus', type: '语言模型', group: '国产顶级模型', source: '云端模型', tag: '深度思考', discount: '6折', desc: '适合问答、写作、代码与复杂任务规划的高质量语言模型。', tone: 'linear-gradient(135deg,#386ee5,#7951d4)' },
    { name: 'qwen-plus', type: '语言模型', group: '阿里系列模型', source: '云端模型', tag: '文本生成', discount: '6折', desc: '面向日常文本创作和多语言理解的通用对话模型。', tone: 'linear-gradient(135deg,#1684af,#2eaf91)' },
    { name: 'qwen-image', type: '生图模型', group: '国产顶级模型', source: '云端模型', tag: '图像生成', discount: '8折', desc: '支持文生图与图生图，适合视觉概念、海报与插画创作。', tone: 'linear-gradient(135deg,#ff825d,#bd4caf)' },
    { name: 'cosyvoice-v3-plus', type: 'TTS模型', group: '阿里系列模型', source: '云端模型', tag: '语音生成', discount: '9折', desc: '可将文字转换为自然流畅的多音色语音。', tone: 'linear-gradient(135deg,#7e57dc,#3d8ff0)' },
    { name: 'wanx2.1-vace-plus', type: '生视频模型', group: '首推旗舰模型', source: '云端模型', tag: '视频生成', discount: '9折', desc: '支持文本、图像和视频条件控制的视频生成与编辑。', tone: 'linear-gradient(135deg,#176d9a,#283d91)' },
    { name: 'campus-knowledge-rag', type: '本地模型', group: '私域知识模型', source: '私域模型', tag: '本地部署', discount: '校内', desc: '校内知识库检索增强模型，适合规章制度与课程资料问答。', tone: 'linear-gradient(135deg,#34875b,#1f5f6b)' }
  ];

  const api = {
    delay(value, ms) { return new Promise(resolve => setTimeout(() => resolve(value), ms || 400)); },
    models() { return window.PortalConfig.demoMode ? this.delay(models) : window.PortalApi.models({ page: 1, page_size: 100 }).then(result => result.items || []); },
    text(payload) {
      if (!window.PortalConfig.demoMode) return Promise.reject({ message: '请使用流式文本接口。' });
      if (shouldSimulateFailure(payload.prompt)) {
        return new Promise((resolve, reject) => setTimeout(() => reject({ message: '演示模式已按指令模拟一次文本任务失败。' }), 760));
      }
      return this.delay({ answer: `这是“${payload.prompt}”的演示回答。接入成员2的 /api/tasks/text 后，这里会显示真实模型的流式或完整结果。` }, 760);
    },
    createTask(payload) {
      if (!window.PortalConfig.demoMode) return Promise.reject({ message: '请使用任务接口。' });
      return this.delay({ id: `TASK-${Date.now().toString().slice(-6)}`, status: 'pending', ...payload }, 380);
    }
  };

  function shouldSimulateFailure(value) {
    return window.PortalConfig.demoMode && String(value || '').includes('#失败');
  }

  function currentModel(type) {
    if (type === 'text') return models.find(item => item.name === state.currentChatModel && item.modelType === 'text') || models.find(item => item.modelType === 'text');
    return models.find(item => item.id === state.selectedModelIds[type]) || models.find(item => item.modelType === type);
  }

  function remoteRecord(kind, response, title, mode, meta) {
    const record = {
      id: response.task_id, title, mode, meta,
      createdAt: new Date().toLocaleString('zh-CN', { hour12: false }),
      status: response.status || 'pending', kind, attempts: 1, error: ''
    };
    state[`${kind}History`].unshift(record);
    state.tasks.unshift(Object.assign({}, record));
    pollTask(record);
    return record;
  }

  function applyTaskDetail(record, detail) {
    record.status = detail.status || record.status;
    record.error = detail.error_message || '';
    record.resultText = detail.result_text || '';
    record.resultUrls = detail.result_urls || (detail.result_url ? [detail.result_url] : []);
    const mirror = state.tasks.find(item => String(item.id) === String(record.id));
    if (mirror) Object.assign(mirror, record);
  }

  function pollTask(record, retries) {
    const remaining = retries == null ? 120 : retries;
    if (window.PortalConfig.demoMode || remaining <= 0 || ['succeeded', 'failed'].includes(record.status)) return;
    window.setTimeout(() => {
      window.PortalApi.taskDetail(record.id).then(detail => {
        applyTaskDetail(record, detail);
        if (['pending', 'processing'].includes(record.status)) pollTask(record, remaining - 1);
        if (['image', 'audio', 'video', 'tasks'].includes(state.route)) render();
      }).catch(error => {
        record.error = error && error.message ? error.message : '无法读取任务状态';
        if (state.route === record.kind || state.route === 'tasks') render();
      });
    }, 2000);
  }

  function loadModels() {
    if (window.PortalConfig.demoMode || !window.PortalApi || !window.PortalApi.token()) return Promise.resolve();
    return api.models().then(items => {
      const typeNames = { text: '语言模型', image: '生图模型', audio: 'TTS模型', video: '生视频模型' };
      models = items.filter(item => item.available !== false).map((item, index) => ({
        id: item.id, name: item.name, modelType: item.model_type,
        type: typeNames[item.model_type] || '其他模型',
        group: item.provider_type === 'local' ? '私域知识模型' : '云端模型',
        source: item.provider_type === 'local' ? '私域模型' : '云端模型',
        tag: Array.isArray(item.capability_tags) ? item.capability_tags[0] || item.model_type : item.model_type,
        discount: item.price_per_call ? `¥${item.price_per_call}/次` : '免费',
        desc: item.description || '已接入平台模型服务。',
        tone: ['#386ee5', '#7951d4', '#2eaf91', '#bd4caf'][index % 4]
      }));
      const selected = currentModel('text');
      if (selected) state.currentChatModel = selected.name;
    }).catch(error => {
      toast(error && error.message ? `模型列表加载失败：${error.message}` : '模型列表加载失败，请稍后刷新。', 'error');
    });
  }

  function normalizeText(value, fallback, maxLength) {
    if (typeof value !== 'string') return fallback;
    const normalized = value.replace(/[\u0000-\u001f\u007f]/g, '').trim().slice(0, maxLength);
    return normalized || fallback;
  }


  function applyCurrentUser(profile) {
    if (!profile || typeof profile !== 'object') return;
    const source = profile.user && typeof profile.user === 'object' ? profile.user : profile;
    const details = profile.profile && typeof profile.profile === 'object' ? profile.profile : {};
    const wallet = profile.wallet && typeof profile.wallet === 'object' ? profile.wallet : {};
    const name = normalizeText(details.nickname || source.username, '用户', 30);
    user = {
      name,
      initial: Array.from(name)[0].toUpperCase(),
      balance: Number.isFinite(Number(wallet.balance)) ? (Number(wallet.balance) / 100).toFixed(2) : '—',
      school: normalizeText(source.school, '未填写学校', 100),
      realName: Number(source.real_auth_status) === 1 ? '已认证' : '未认证',
      role: source.role === 'admin' ? 'admin' : 'user'
    };
  }
  function hydrateDemoState() {
    if (!window.PortalConfig.demoMode) return;
    try {
      const saved = JSON.parse(localStorage.getItem(DEMO_STORAGE_KEY) || 'null');
      if (!saved || typeof saved !== 'object') return;
      ['chatMessages', 'chatHistory', 'imageHistory', 'audioHistory', 'videoHistory', 'tasks'].forEach(key => {
        if (Array.isArray(saved[key])) state[key] = saved[key].filter(item => item && typeof item === 'object').slice(0, 100);
      });
      ['modelType', 'modelGroup', 'modelSource', 'keyword', 'currentChatModel', 'imageMode', 'imageRatio', 'audioMode', 'selectedVoice', 'videoDuration'].forEach(key => {
        if (typeof saved[key] === 'string') state[key] = normalizeText(saved[key], state[key], 100);
      });
      if (saved.user && typeof saved.user === 'object') {
        user = {
          name: normalizeText(saved.user.name, user.name, 30),
          initial: normalizeText(saved.user.initial, user.initial, 4),
          balance: normalizeText(saved.user.balance, user.balance, 24),
          school: normalizeText(saved.user.school, user.school, 50),
          realName: normalizeText(saved.user.realName, user.realName, 20)
        };
      }
    } catch (error) {
      localStorage.removeItem(DEMO_STORAGE_KEY);
    }
  }

  function persistDemoState() {
    if (!window.PortalConfig.demoMode) return;
    const snapshot = {
      chatMessages: state.chatMessages.slice(-100),
      chatHistory: state.chatHistory.slice(0, 100),
      imageHistory: state.imageHistory.slice(0, 100),
      audioHistory: state.audioHistory.slice(0, 100),
      videoHistory: state.videoHistory.slice(0, 100),
      tasks: state.tasks.slice(0, 100),
      modelType: state.modelType,
      modelGroup: state.modelGroup,
      modelSource: state.modelSource,
      keyword: state.keyword,
      currentChatModel: state.currentChatModel,
      imageMode: state.imageMode,
      imageRatio: state.imageRatio,
      audioMode: state.audioMode,
      selectedVoice: state.selectedVoice,
      videoDuration: state.videoDuration,
      user
    };
    try {
      localStorage.setItem(DEMO_STORAGE_KEY, JSON.stringify(snapshot));
    } catch (error) {
      toast('浏览器无法保存演示记录，请检查存储空间。', 'error');
    }
  }

  function clearTaskTimers(id) {
    const timers = taskTimers.get(id) || [];
    timers.forEach(timer => clearTimeout(timer));
    taskTimers.delete(id);
  }

  function scheduleDemoTask(record, forceSuccess) {
    clearTaskTimers(record.id);
    const timers = [
      setTimeout(() => updateTask(record.id, 'processing'), 650),
      setTimeout(() => updateTask(record.id, forceSuccess || !record.shouldFail ? 'succeeded' : 'failed'), 1750)
    ];
    taskTimers.set(record.id, timers);
  }

  function resumeDemoTasks() {
    ['imageHistory', 'audioHistory', 'videoHistory'].forEach(key => {
      state[key].filter(item => ['pending', 'processing'].includes(item.status)).forEach(item => scheduleDemoTask(item));
    });
  }

  function escapeHtml(value) {
    return String(value || '').replace(/[&<>'"]/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' })[char]);
  }
  function safeNavigationUrl(value) {
    const raw = String(value || '').trim();
    if (!raw) return '';
    try {
      const parsed = new URL(raw, location.href);
      return ['http:', 'https:'].includes(parsed.protocol) ? raw : '';
    } catch (error) {
      return '';
    }
  }
  function icon(name) { return `<i class="layui-icon ${name}"></i>`; }
  function currentRoute() {
    if (location.hash) return location.hash.replace(/^#\/?/, '').split('?')[0] || 'home';
    const page = location.pathname.split('/').pop().toLowerCase() || 'index.html';
    const physicalPages = {
      'index.html': 'home', 'models.html': 'models', 'chat.html': 'text',
      'image.html': 'image', 'audio.html': 'audio', 'video.html': 'video',
      'tasks.html': 'tasks', 'profile.html': 'profile'
    };
    return physicalPages[page] || 'home';
  }
  function setRoute(route) { location.hash = '#/' + route; }
  function toast(message, type) {
    const node = $(`<div class="toast ${type || ''}" role="status" aria-live="polite">${icon(type === 'error' ? 'layui-icon-close-fill' : 'layui-icon-ok-circle')} ${escapeHtml(message)}</div>`);
    $('body').append(node); setTimeout(() => node.fadeOut(220, () => node.remove()), 2600);
  }
  function statusLabel(status) {
    const labels = { pending: '待处理', processing: '处理中', succeeded: '已完成', failed: '失败' };
    const normalized = status === 'success' ? 'succeeded' : status;
    const label = labels[normalized] || '状态未知';
    const style = normalized === 'succeeded' ? 'success' : (labels[normalized] ? normalized : 'pending');
    return `<span class="status-tag ${style}" aria-label="任务状态：${label}">${label}</span>`;
  }
  function pageHead(title, subtitle, action) {
    return `<div class="page-head"><div><h1 class="page-title">${title}</h1><p class="page-subtitle">${subtitle}</p></div>${action || ''}</div>`;
  }
  function navTemplate(route) {
    return navItems.map(([id, label, iconName]) => `<a class="side-link ${route === id ? 'active' : ''}" href="#/${id}"${route === id ? ' aria-current="page"' : ''}>${icon(iconName)}<span>${label}</span></a>`).join('');
  }
  function shell(route, content) {
    return `
      <a class="skip-link" href="#main-content">跳到主要内容</a>
      <header class="topbar">
        <div style="display:flex;align-items:center;gap:10px">
          <button class="mobile-nav-toggle" type="button" aria-label="打开导航" aria-controls="primary-sidebar" aria-expanded="false">${icon('layui-icon-spread-left')}</button>
          <a class="brand" href="#/home"><span class="brand-mark">${icon('layui-icon-light')}</span><span>四川高校大模型门户</span></a>
        </div>
        <div class="top-actions">
          ${window.PortalConfig.demoMode ? '<span class="demo-badge">演示模式</span>' : ''}
          <div class="identity">${icon('layui-icon-vercode')}<span>${escapeHtml(user.realName)}</span></div>
          <div class="wallet">${icon('layui-icon-rmb')}<span>余额 ¥${escapeHtml(user.balance)}</span></div>
          <div class="account-menu-wrap">
            <button class="user-menu" id="account-menu-button" type="button" aria-label="打开账户菜单" aria-haspopup="menu" aria-controls="account-menu-popup" aria-expanded="false"><span class="avatar">${escapeHtml(user.initial)}</span><span>${escapeHtml(user.name)}</span>${icon('layui-icon-down')}</button>
            <div class="account-menu" id="account-menu-popup" role="menu" aria-labelledby="account-menu-button" hidden>
              <div class="account-menu-summary" role="presentation"><span class="avatar account-menu-avatar">${escapeHtml(user.initial)}</span><span class="account-menu-copy"><strong>${escapeHtml(user.name)}</strong><small>${escapeHtml(user.school)} · 学生用户</small></span></div>
                            <div class="account-menu-meta" role="presentation"><span>${icon('layui-icon-vercode')} ${escapeHtml(user.realName)}</span><span>余额 ¥${escapeHtml(user.balance)}</span></div>
              <div class="account-menu-divider" role="separator"></div>
              <button class="account-menu-item" type="button" role="menuitem" data-route="profile">${icon('layui-icon-user')}<span>个人中心</span></button>
              <button class="account-menu-item" type="button" role="menuitem" data-route="tasks">${icon('layui-icon-list')}<span>创作历史</span></button>
              <div class="account-menu-divider" role="separator"></div>
              ${window.PortalConfig.demoMode
                ? `<button class="account-menu-item account-menu-item-disabled" type="button" role="menuitem" aria-disabled="true" disabled title="演示模式未建立真实登录状态">${icon('layui-icon-logout')}<span>退出登录</span><small>演示模式</small></button>`
                : `<button class="account-menu-item" type="button" role="menuitem" data-logout>${icon('layui-icon-logout')}<span>退出登录</span></button>`}
            </div>
          </div>
        </div>
      </header>
      <aside class="sidebar" id="primary-sidebar"><nav class="side-nav" aria-label="主导航">${navTemplate(route)}</nav><div class="side-footer">© 2026 四川高校大模型门户<br>课程项目演示版</div></aside>
      <button class="nav-scrim" type="button" aria-label="关闭导航"></button>
      <main class="workspace" id="main-content" tabindex="-1"><div class="page">${content}</div></main>`;
  }

  function authRequiredView() {
    const loginUrl = safeNavigationUrl(window.PortalConfig.loginUrl);
    const loginAction = loginUrl
      ? `<a class="btn-primary auth-link" href="${escapeHtml(loginUrl)}">前往登录</a>`
      : '<p class="state-note">登录入口尚未配置或配置无效，请联系项目集成人员。</p>';
    return `<main class="auth-required"><section class="panel panel-pad"><span class="auth-icon">${icon('layui-icon-password')}</span><h1>请先登录</h1><p>当前页面需要有效登录状态。登录后可继续使用模型和创作任务。</p>${loginAction}</section></main>`;
  }

  function modelCard(model) {
    const rawName = String(model.name || '');
    const initials = rawName.split(/[-.]/).map(item => item[0]).join('').slice(0, 2).toUpperCase();
    const tone = /^#[0-9a-f]{6}$/i.test(String(model.tone || '')) ? model.tone : '#2f6fe8';
    return `<article class="model-card">
      <div class="model-card-top"><span class="model-logo" style="background:${tone}">${escapeHtml(initials)}</span><span class="discount">${escapeHtml(model.discount)}</span></div>
      <h3 class="model-name">${escapeHtml(rawName)}</h3><p class="model-desc">${escapeHtml(model.desc)}</p>
      <div class="model-meta"><span class="tag">${escapeHtml(model.tag)}</span><button class="btn-quiet" type="button" data-use-model="${escapeHtml(rawName)}">立即使用</button></div>
    </article>`;
  }

  function homeView() {
    const feature = models.slice(0, 3).map(modelCard).join('');
    const quick = [
      ['audio', 'layui-icon-voice', '声音合成', '将文字转换为自然语音'],
      ['video', 'layui-icon-video', '视频合成', '从灵感到动态成片'], ['image', 'layui-icon-picture', '图像生成', '把文字变成视觉表达'],
      ['models', 'layui-icon-app', '私域模型', '查看校内模型能力']
    ].map(([route, iconName, title, desc]) => `<button class="quick-entry" data-route="${route}"><span class="quick-icon">${icon(iconName)}</span><strong>${title}</strong><span>${desc}</span></button>`).join('');
    return `${pageHead('首页', '为四川高校学生准备的一站式多模态 AI 创作空间')}
      <section class="hero panel"><div class="hero-copy"><p class="hero-overline">AI MULTIMODAL</p><h2>AI 多模态创作工具</h2><p>从一段灵感到可用的文字、图像、声音和视频，在同一个工作区完成模型选择、创作与结果管理。</p><button class="btn-primary" data-route="models">立即体验 ${icon('layui-icon-right')}</button></div></section>
      <section style="margin-top:24px"><div class="page-head"><div><h2 class="section-title">${icon('layui-icon-star')}精选模型</h2></div><button class="btn-secondary" data-route="models">进入模型广场</button></div><div class="feature-grid">${feature}</div></section>
      <section style="margin-top:28px"><h2 class="section-title">${icon('layui-icon-template-1')}常用功能入口</h2><div class="quick-grid">${quick}</div></section>`;
  }

  function filteredModels() {
    return models.filter(item => (state.modelSource === '全部' || item.source === state.modelSource) && (state.modelGroup === '全部分组' || item.group === state.modelGroup) && (state.modelType === '全部' || item.type === state.modelType) && item.name.toLowerCase().includes(state.keyword.toLowerCase()));
  }

  function modelResultsHtml() {
    const visible = filteredModels();
    return visible.length ? visible.map(modelCard).join('') : `<div class="empty-state" style="grid-column:1/-1">${icon('layui-icon-search')}<div>没有找到匹配的模型<br><small>尝试清空筛选条件后重试</small></div></div>`;
  }

  function modelsView() {
    const groups = ['全部分组', '国产顶级模型', '阿里系列模型', '首推旗舰模型', '私域知识模型'];
    const types = ['全部', '语言模型', '多模态模型', 'TTS模型', '生图模型', '生视频模型', '本地模型'];
    return `${pageHead('模型广场', '探索可用于创作与开发的模型能力，按场景快速筛选。')}
      <section class="panel panel-pad"><div class="filters" style="margin-bottom:12px"><button type="button" class="filter-btn ${state.modelSource === '云端模型' ? 'active' : ''}" data-source="云端模型" aria-pressed="${state.modelSource === '云端模型'}">云端模型</button><button type="button" class="filter-btn ${state.modelSource === '私域模型' ? 'active' : ''}" data-source="私域模型" aria-pressed="${state.modelSource === '私域模型'}">私域模型</button></div>
      <div class="filters" style="margin-bottom:12px">${groups.map(item => `<button type="button" class="filter-btn ${state.modelGroup === item ? 'active' : ''}" data-group="${item}" aria-pressed="${state.modelGroup === item}">${item}</button>`).join('')}</div>
      <div class="models-toolbar"><div class="filters">${types.map(item => `<button type="button" class="filter-btn ${state.modelType === item ? 'active' : ''}" data-type="${item}" aria-pressed="${state.modelType === item}">${item}</button>`).join('')}</div><label class="search-field">${icon('layui-icon-search')}<input class="field" id="model-search" value="${escapeHtml(state.keyword)}" placeholder="搜索模型名称" aria-label="搜索模型名称" /></label></div>
      <div class="models-grid" aria-live="polite">${modelResultsHtml()}</div></section>`;
  }

  function textView() {
    const chatModels = models.filter(item => item.type === '语言模型' || item.type === '本地模型');
    const messages = state.chatMessages.map(item => `<div class="message ${item.role === 'user' ? 'user' : ''}"><span class="message-avatar">${item.role === 'user' ? escapeHtml(user.initial) : 'AI'}</span><div class="bubble">${item.loading ? '<span class="typing-dots"><i></i><i></i><i></i></span>' : escapeHtml(item.content)}</div></div>`).join('');
    return `${pageHead('文本交互舱', '选择模型，开始一次专注的对话与创作。')}
      <section class="panel chat-layout">
        <aside class="chat-models"><strong style="font-size:14px">可用模型</strong><div class="chat-list">${chatModels.map(model => `<button type="button" class="chat-model-option ${state.currentChatModel === model.name ? 'active' : ''}" data-chat-model="${escapeHtml(model.name)}" aria-pressed="${state.currentChatModel === model.name}">${escapeHtml(model.name)}<small>${escapeHtml(model.tag)}</small></button>`).join('')}</div></aside>
        <div class="chat-main"><div class="chat-toolbar"><div><strong>${escapeHtml(state.currentChatModel)}</strong><span> · 已准备就绪</span></div><button class="btn-secondary" id="new-chat" type="button">${icon('layui-icon-add-1')} 新建会话</button></div><div class="messages" id="message-list" role="log" aria-live="polite" aria-label="对话消息">${messages}</div><div class="chat-compose"><textarea id="chat-input" class="textarea-field" maxlength="2000" placeholder="输入你的问题或指令…" aria-label="对话内容，按 Ctrl 加 Enter 发送"></textarea><div class="compose-foot"><div class="chip-row"><button type="button" class="prompt-chip" data-prompt="请帮我优化下面这段文案：">文案优化</button><button type="button" class="prompt-chip" data-prompt="请把下面内容翻译成英文：">翻译</button><button type="button" class="prompt-chip" data-prompt="请用 Python 写一个函数：">代码编写</button></div><button class="btn-primary" id="send-chat" type="button" ${state.busy.text ? 'disabled' : ''}>${state.busy.text ? '生成中…' : '发送'} ${icon('layui-icon-release')}</button></div></div></div>
        <aside class="chat-history"><div style="display:flex;justify-content:space-between;align-items:center"><strong style="font-size:14px">历史会话</strong><button class="btn-quiet" id="new-chat-side" type="button" aria-label="新建会话" title="新建会话">${icon('layui-icon-add-1')}</button></div><div style="margin-top:14px">${state.chatHistory.map(item => `<div class="history-row">${escapeHtml(item.title)}<small>${escapeHtml(item.date)}</small></div>`).join('')}</div></aside>
      </section>`;
  }

  function historyRows(history, kind) {
    if (!history.length) return `<tr><td class="table-empty" colspan="6">暂无${kind}历史，完成一次创作后将在此显示。</td></tr>`;
    return history.map(item => {
      const error = item.error ? `<small class="task-error">${escapeHtml(item.error)}</small>` : '';
      const action = item.status === 'failed'
        ? `<button type="button" class="btn-quiet" data-retry="${escapeHtml(item.id)}">重新提交</button>`
        : `<button type="button" class="btn-quiet" data-view-task="${escapeHtml(item.id)}">查看</button>`;
      return `<tr><td><span class="task-title">${escapeHtml(item.title)}</span>${error}</td><td>${escapeHtml(item.mode)}</td><td>${escapeHtml(item.meta)}</td><td>${escapeHtml(item.createdAt)}</td><td>${statusLabel(item.status)}</td><td>${action}</td></tr>`;
    }).join('');
  }

  function imageView() {
    const hasResult = state.imageHistory[0] && ['succeeded', 'success'].includes(state.imageHistory[0].status);
    return `${pageHead('图像生成室', '选择模型并输入描述词，把灵感转成可用的视觉素材。')}
      <section class="studio-layout"><div class="panel preview-stage"><div class="panel-pad" style="padding-bottom:12px"><h2 class="section-title">${icon('layui-icon-picture')}图像预览</h2></div><div class="preview-art ${hasResult ? 'demo-image' : ''}"><div class="preview-art-inner">${icon(hasResult ? 'layui-icon-picture' : 'layui-icon-upload-drag')}<strong>${hasResult ? '演示生成结果' : '等待生成图像'}</strong><span>${hasResult ? '接入真实图像接口后将显示服务端返回的图片。' : '提交提示词后，生成结果会在这里展示。'}</span></div></div><div class="preview-caption">${hasResult ? escapeHtml(state.imageHistory[0].title) : '尚未提交任务'}</div></div>
        <form class="panel panel-pad" id="image-form"><div class="inline-model"><span>${icon('layui-icon-light')} qwen-image <small>文生图 / 图生图</small></span><button class="btn-quiet" type="button" data-route="models">更换模型</button></div><div class="tab-row" role="group" aria-label="图像生成模式"><button type="button" class="tab-btn ${state.imageMode === '文生图' ? 'active' : ''}" data-image-mode="文生图" aria-pressed="${state.imageMode === '文生图'}">文生图</button><button type="button" class="tab-btn" disabled aria-disabled="true" title="文件字段确认后开放">图生图 · 待开放</button></div><div class="form-block"><label class="field-label" for="image-prompt">输入描述词 <span class="required">*</span></label><textarea class="textarea-field" id="image-prompt" required placeholder="例如：一只可爱的橘猫在阳光下睡觉，写实风格，8K 分辨率…"></textarea></div><div class="form-block"><span class="field-label" id="image-ratio-label">图像尺寸</span><div class="ratio-row" role="group" aria-labelledby="image-ratio-label">${['1:1 1024×1024', '9:16 720×1280', '16:9 1280×720'].map(item => `<button type="button" class="duration-btn ${state.imageRatio === item ? 'active' : ''}" data-ratio="${item}" aria-pressed="${state.imageRatio === item}">${item}</button>`).join('')}</div></div><div class="advanced"><div class="form-grid"><div><label class="field-label" for="image-count">生成数量</label><select class="select-field" id="image-count"><option value="1">1 张</option><option value="2">2 张</option><option value="4">4 张</option></select></div><div><label class="field-label" for="image-negative">负面提示词</label><input id="image-negative" class="field" placeholder="模糊、低质量、变形…" /></div></div></div><button class="btn-primary wide-action" id="image-submit" type="submit" ${state.busy.image || !window.PortalConfig.demoMode ? 'disabled' : ''}>${icon('layui-icon-release')} ${state.busy.image ? '正在提交…' : (window.PortalConfig.demoMode ? '立即生成' : '接口待接入')}</button><p class="state-note">${icon('layui-icon-tips')} ${window.PortalConfig.demoMode ? '演示记录会保存在本机；提示词包含“#失败”可验证失败与重试。' : '真实图像接口尚未挂载，当前不会提交或生成本地假任务。'}</p></form></section>
      <section class="panel panel-pad history-panel"><h2 class="section-title">${icon('layui-icon-list')}生成历史</h2><div class="table-wrap" role="region" aria-label="创作记录表格" tabindex="0"><table class="data-table"><thead><tr><th scope="col">提示词</th><th scope="col">类型</th><th scope="col">尺寸</th><th scope="col">创建时间</th><th scope="col">状态</th><th scope="col">操作</th></tr></thead><tbody>${historyRows(state.imageHistory, '生成')}</tbody></table></div></section>`;
  }

  function audioView() {
    const running = state.audioHistory[0] && ['pending', 'processing'].includes(state.audioHistory[0].status);
    const complete = state.audioHistory[0] && ['succeeded', 'success'].includes(state.audioHistory[0].status);
    const voices = [['龙安洋', '阳光大男孩 · 中英双语'], ['龙安欢', '欢脱元气女 · 中英双语'], ['清雅老师', '知性女声 · 普通话'], ['星河少年', '沉稳男声 · 普通话']];
    return `${pageHead('声音创作坊', '将文字转成自然语音，并保留每一次创作的任务记录。')}
      <section class="studio-layout"><div class="panel preview-stage"><div class="panel-pad" style="padding-bottom:12px"><h2 class="section-title">${icon('layui-icon-voice')}音频预览</h2></div><div class="preview-art" style="min-height:250px;background:linear-gradient(140deg,#182545,#283c77)"><div class="preview-art-inner">${icon(complete ? 'layui-icon-headset' : 'layui-icon-voice')}<strong>${complete ? '音频已生成' : running ? '正在生成音频' : '未开始生成'}</strong><span>${complete ? '演示任务已完成；真实音频接入后可播放。' : '提交文本后可查看任务状态。'}</span></div></div><div class="preview-caption">${complete ? `<div class="audio-player"><button class="player-button" type="button" disabled title="真实音频地址接入后可播放">${icon('layui-icon-play')}</button><div class="wave">${Array.from({length:42}, () => '<i></i>').join('')}</div><span>00:18</span></div>` : '声音任务通常以异步方式处理，请勿重复提交。'}</div></div>
        <form class="panel panel-pad" id="audio-form"><div class="inline-model"><span>${icon('layui-icon-light')} cosyvoice-v3-plus <small>¥1.2 / 万字符</small></span><button class="btn-quiet" type="button" data-route="models">更换模型</button></div><div class="tab-row" role="group" aria-label="声音创作模式">${['声音合成', '声音克隆', '语音识别', '长文本转音频'].map(item => `<button type="button" class="tab-btn ${state.audioMode === item ? 'active' : ''}" aria-pressed="${state.audioMode === item}" ${item === '声音合成' ? `data-audio-mode="${item}"` : 'disabled aria-disabled="true" title="接口字段确认后开放"'}>${item}${item === '声音合成' ? '' : ' · 待开放'}</button>`).join('')}</div><div class="form-block"><label class="field-label" for="audio-text">输入文本 <span class="required">*</span></label><textarea class="textarea-field" id="audio-text" aria-describedby="audio-count" maxlength="2000" required placeholder="输入您想转换成声音的文本内容…"></textarea><div class="state-note" style="margin-top:6px">${icon('layui-icon-note')} <span id="audio-count" aria-live="polite">0 / 2000 字符</span></div></div><div class="form-grid"><div><label class="field-label" for="audio-speed">语速</label><input class="field" id="audio-speed" type="number" step="0.1" min="0.5" max="2" value="1" /></div><div><label class="field-label" for="audio-format">音频格式</label><select class="select-field" id="audio-format"><option>MP3（默认）</option><option>WAV</option><option>PCM</option><option>OPUS</option></select></div></div><div class="form-block" style="margin-top:18px"><span class="field-label" id="voice-label">选择配音员</span><div class="audio-voice-grid" role="group" aria-labelledby="voice-label">${voices.map(([name, detail]) => `<button type="button" class="voice-card ${state.selectedVoice === name ? 'active' : ''}" data-voice="${name}" aria-pressed="${state.selectedVoice === name}"><strong>${name}</strong><span>${detail}</span></button>`).join('')}</div></div><button class="btn-primary wide-action" id="audio-submit" type="submit" ${state.busy.audio || !window.PortalConfig.demoMode ? 'disabled' : ''}>${icon('layui-icon-release')} ${state.busy.audio ? '正在提交…' : (window.PortalConfig.demoMode ? '生成音频' : '接口待接入')}</button><p class="state-note">${icon('layui-icon-tips')} ${window.PortalConfig.demoMode ? '文本包含“#失败”可验证失败任务和重新提交。' : '真实声音接口尚未挂载，当前不会提交或生成本地假任务。'}</p></form></section>
      <section class="panel panel-pad history-panel"><h2 class="section-title">${icon('layui-icon-list')}创作历史</h2><div class="table-wrap" role="region" aria-label="创作记录表格" tabindex="0"><table class="data-table"><thead><tr><th scope="col">作品名称</th><th scope="col">模式</th><th scope="col">时长/字数</th><th scope="col">完成时间</th><th scope="col">状态</th><th scope="col">操作</th></tr></thead><tbody>${historyRows(state.audioHistory, '创作')}</tbody></table></div></section>`;
  }

  function videoView() {
    const current = state.videoHistory[0];
    const running = current && ['pending', 'processing'].includes(current.status);
    const complete = current && ['succeeded', 'success'].includes(current.status);
    return `${pageHead('视频合成站', '以文本、图片或音频条件组合成一段可控的短视频。')}
      <section class="studio-layout"><div class="panel preview-stage"><div class="panel-pad" style="padding-bottom:12px"><h2 class="section-title">${icon('layui-icon-video')}视频预览</h2></div><div class="video-preview"><div class="preview-art-inner">${icon(complete ? 'layui-icon-play' : 'layui-icon-video')}<strong>${complete ? '视频生成完成' : running ? '正在渲染视频' : '视频预览区域'}</strong><span>${complete ? '演示模式下可展示预生成素材；正式接口会返回视频地址。' : '生成完成后将在此显示结果。'}</span></div></div><div class="preview-caption">${running ? '渲染过程可能需要 3–5 分钟，请耐心等待。' : complete ? escapeHtml(current.title) : '无首帧时将采用文生视频模型。'}</div></div>
        <form class="panel panel-pad" id="video-form"><div class="inline-model"><span>${icon('layui-icon-light')} wanx2.1-vace-plus <small>视频生成</small></span><button class="btn-quiet" type="button" data-route="models">更换模型</button></div><div class="form-block"><label class="field-label" for="video-prompt">视频描述提示词 <span class="required">*</span></label><textarea class="textarea-field" maxlength="500" id="video-prompt" required placeholder="描述您想要生成的视频内容…"></textarea></div><div class="form-block"><label class="field-label" for="video-negative">反向提示词（可选）</label><input class="field" id="video-negative" value="模糊、失真、低质量、变形、扭曲、水印、文字" /></div><div class="form-block"><span class="field-label" id="video-duration-label">视频时长</span><div class="duration-row" role="group" aria-labelledby="video-duration-label">${['5秒', '10秒', '15秒'].map(item => `<button type="button" class="duration-btn ${state.videoDuration === item ? 'active' : ''}" data-video-duration="${item}" aria-pressed="${state.videoDuration === item}">${item}</button>`).join('')}</div></div><div class="form-grid"><div><label class="field-label" for="video-resolution">分辨率</label><select class="select-field" id="video-resolution"><option>720P（高清）</option><option>1080P（超清）</option></select></div><div><span class="field-label">音频设置</span><button class="upload-drop" type="button" disabled aria-disabled="true" title="上传字段确认后开放">${icon('layui-icon-upload')} 音频上传 · 待开放</button></div></div><button class="btn-primary wide-action" id="video-submit" type="submit" ${state.busy.video || !window.PortalConfig.demoMode ? 'disabled' : ''}>${icon('layui-icon-release')} ${state.busy.video ? '正在提交…' : (window.PortalConfig.demoMode ? '文生视频' : '接口待接入')}</button><p class="state-note">${icon('layui-icon-tips')} ${window.PortalConfig.demoMode ? '提示词包含“#失败”可验证失败任务和重新提交。' : '真实视频接口尚未挂载，当前不会提交或生成本地假任务。'}</p><div class="tip-box"><strong>${icon('layui-icon-tips')} 温馨提示</strong>有首帧时可改用图生视频；尾帧可选，用于控制视频结束画面。长任务提交后请在创作历史中查看状态。</div></form></section>
      <section class="panel panel-pad history-panel"><h2 class="section-title">${icon('layui-icon-list')}创作历史</h2><div class="table-wrap" role="region" aria-label="创作记录表格" tabindex="0"><table class="data-table"><thead><tr><th scope="col">作品名称</th><th scope="col">合成模式</th><th scope="col">时长</th><th scope="col">创建时间</th><th scope="col">状态</th><th scope="col">操作</th></tr></thead><tbody>${historyRows(state.videoHistory, '创作')}</tbody></table></div></section>`;
  }

  function tasksView() {
    const all = [...state.videoHistory, ...state.audioHistory, ...state.imageHistory].sort((a, b) => b.createdAt.localeCompare(a.createdAt));
    const action = window.PortalConfig.demoMode && all.length ? '<button type="button" class="btn-secondary" id="clear-demo-history">清空演示记录</button>' : '';
    return `${pageHead('创作历史', '集中查看你提交过的图像、声音和视频任务。', action)}
      <section class="panel panel-pad"><div class="notice">${icon('layui-icon-tips')}<div>${window.PortalConfig.demoMode ? '这里只展示当前登录用户的任务。任务失败时可以重新提交；正式系统会由后端保证失败任务不扣费。' : '任务列表接口尚未挂载，当前不展示服务端任务。接入后将从后端加载当前用户的任务。'}</div></div><div class="table-wrap" style="margin-top:18px" role="region" aria-label="全部创作任务表格" tabindex="0"><table class="data-table"><thead><tr><th scope="col">任务名称</th><th scope="col">类型</th><th scope="col">参数</th><th scope="col">创建时间</th><th scope="col">状态</th><th scope="col">操作</th></tr></thead><tbody>${historyRows(all, '任务')}</tbody></table></div></section>`;
  }

  function profileView() {
    const verified = user.realName === '已认证';
    const roleLabel = user.role === 'admin' ? '管理员' : '普通用户';
    const modelCount = window.PortalConfig.demoMode ? '3' : '—';
    const rechargeDisabled = window.PortalConfig.demoMode ? 'disabled aria-disabled="true" title="演示模式未连接充值接口"' : '';
    return `${pageHead('个人中心', '查看实名认证状态、账户概况和个人资料。')}
      <section class="profile-grid">
        <article class="panel panel-pad profile-card">
          <div class="profile-avatar">${escapeHtml(user.initial)}</div>
          <h2 class="profile-name">${escapeHtml(user.name)}</h2>
          <p>${escapeHtml(user.school)} · ${escapeHtml(roleLabel)}</p>
          <span class="status-tag ${verified ? 'success' : 'pending'}">${icon('layui-icon-vercode')} ${escapeHtml(user.realName)}</span>
          <div class="metric-row">
            <div class="metric"><strong>¥${escapeHtml(user.balance)}</strong><span>账户余额</span></div>
            <div class="metric"><strong>${state.imageHistory.length + state.audioHistory.length + state.videoHistory.length}</strong><span>创作次数</span></div>
            <div class="metric"><strong>${modelCount}</strong><span>可用模型</span></div>
          </div>
          <div class="profile-actions">
            <button class="btn-primary" id="recharge-open" type="button" ${rechargeDisabled}>${icon('layui-icon-rmb')}充值</button>
          </div>
          <div class="recharge-panel" id="recharge-panel" hidden>
            <form id="recharge-form">
              <div class="form-block">
                <label class="field-label" for="recharge-amount">充值金额（元）</label>
                <div class="recharge-input-wrap"><input class="field" id="recharge-amount" type="number" min="0.01" max="10000" step="0.01" inputmode="decimal" required placeholder="请输入金额" /><span class="recharge-unit">元</span></div>
              </div>
              <div class="recharge-presets" role="group" aria-label="快捷充值金额">
                ${[10, 50, 100].map(amount => `<button type="button" class="btn-secondary recharge-preset" data-recharge-amount="${amount}">${amount} 元</button>`).join('')}
              </div>
              <p class="state-note">${icon('layui-icon-tips')} 模拟充值按“分”提交，到账后余额自动更新。</p>
              <div class="recharge-actions"><button class="btn-quiet" id="recharge-cancel" type="button">取消</button><button class="btn-primary" id="recharge-submit" type="submit" ${state.busy.recharge ? 'disabled' : ''}>${state.busy.recharge ? '正在提交…' : '确认充值'}</button></div>
            </form>
          </div>
        </article>
        <section class="panel panel-pad"><h2 class="section-title">${icon('layui-icon-user')}基础资料</h2><form id="profile-form"><div class="form-grid"><div class="form-block"><label class="field-label" for="profile-name">昵称</label><input class="field" id="profile-name" autocomplete="nickname" maxlength="30" value="${escapeHtml(user.name)}" /></div><div class="form-block"><label class="field-label" for="profile-school">学校</label><input class="field" id="profile-school" autocomplete="organization" maxlength="50" value="${escapeHtml(user.school)}" /></div><div class="form-block"><label class="field-label" for="profile-verification">实名认证状态</label><input class="field" id="profile-verification" value="${escapeHtml(user.realName)}" disabled /></div><div class="form-block"><label class="field-label" for="profile-role">账号角色</label><input class="field" id="profile-role" value="${escapeHtml(roleLabel)}" disabled /></div></div><button class="btn-primary" id="profile-submit" type="submit" ${state.busy.profile ? 'disabled' : ''}>${state.busy.profile ? '正在保存…' : '保存资料'}</button></form><div class="notice" style="margin-top:20px">${icon('layui-icon-tips')}<div>钱包余额与充值结果来自后端接口，账单和发票功能将在对应模块接入后开放。</div></div></section>
      </section>`;
  }

  function viewFor(route) {
    const views = { home: homeView, models: modelsView, text: textView, image: imageView, audio: audioView, video: videoView, tasks: tasksView, profile: profileView };
    return (views[route] || homeView)();
  }
  function loadCurrentUser() {
    if (!window.PortalApi || window.PortalApi.config.demoMode) return Promise.resolve();
    const cached = window.PortalApi.currentUserSnapshot();
    if (cached) applyCurrentUser(cached);
    if (!window.PortalApi.token()) return Promise.resolve();
    return window.PortalApi.currentUser().then(profile => {
      applyCurrentUser(profile);
      const persistent = Boolean(localStorage.getItem(window.PortalApi.config.tokenKey));
      window.PortalApi.setCurrentUser(profile, persistent);
    }).catch(() => cached || null);
  }
  function render() {
    state.route = currentRoute();
    document.title = `${routeTitles[state.route] || routeTitles.home} - 四川高校大模型门户`;
    if (window.PortalApi && !window.PortalApi.ensureAuthenticated()) {
      $('#app').html(authRequiredView());
      return;
    }
    $('#app').html(shell(state.route, viewFor(state.route)));
    bindEvents();
    if (state.route === 'text') $('#message-list').scrollTop($('#message-list')[0].scrollHeight);
  }

  function createRecord(kind, payload) {
    if (!window.PortalConfig.demoMode) { toast('真实创作接口尚未接入，请联系项目集成人员。', 'error'); return null; }
    const now = new Date();
    const createdAt = now.toLocaleString('zh-CN', { hour12: false });
    const record = { id: `TASK-${Date.now()}`, title: payload.title, mode: payload.mode, meta: payload.meta, createdAt, status: 'pending', kind, attempts: 1, shouldFail: Boolean(payload.shouldFail), error: '' };
    state[`${kind}History`].unshift(record);
    state.tasks.unshift(Object.assign({}, record));
    persistDemoState();
    scheduleDemoTask(record);
    return record;
  }
  function updateTask(id, nextStatus) {
    ['imageHistory', 'audioHistory', 'videoHistory'].forEach(key => { const target = state[key].find(item => item.id === id); if (target) target.status = nextStatus; });
    const task = state.tasks.find(item => item.id === id); if (task) task.status = nextStatus;
    if (nextStatus === 'failed') {
      ['imageHistory', 'audioHistory', 'videoHistory'].forEach(key => { const target = state[key].find(item => item.id === id); if (target) target.error = '演示任务执行失败，可点击重新提交。'; });
      if (task) task.error = '演示任务执行失败，可点击重新提交。';
    }
    if (['succeeded', 'failed'].includes(nextStatus)) clearTaskTimers(id);
    persistDemoState();
    if (['image', 'audio', 'video', 'tasks', 'profile'].includes(state.route)) render();
  }
  function sendChat() {
    const input = $('#chat-input'); const prompt = input.val().trim();
    if (!prompt) return toast('请输入问题或指令后再发送。', 'error');
    if (state.busy.text) return toast('上一条消息仍在处理中，请稍候。', 'error');
    const model = currentModel('text');
    if (!window.PortalConfig.demoMode && !model) return toast('当前没有可用的文本模型，请先在模型广场确认模型状态。', 'error');
    state.busy.text = true;
    state.chatMessages.push({ role: 'user', content: prompt }); state.chatMessages.push({ role: 'assistant', loading: true }); render();
    const stream = window.PortalConfig.demoMode
      ? api.text({ model: state.currentChatModel, prompt }).then(result => ({ answer: result.answer }))
      : (state.chatSessionId ? Promise.resolve({ session_id: state.chatSessionId }) : window.PortalApi.chatSession({ model_id: model.id }))
        .then(session => {
          state.chatSessionId = session.session_id;
          let answer = '';
          return window.PortalApi.streamText({ session_id: session.session_id, model_id: model.id, message: prompt }, event => {
            if (event.error) throw { message: event.error.message };
            if (event.delta) {
              answer += event.delta;
              state.chatMessages[state.chatMessages.length - 1] = { role: 'assistant', content: answer };
              const list = $('#message-list'); if (list[0]) list.scrollTop(list[0].scrollHeight);
            }
          }).then(() => ({ answer }));
        });
    stream.then(result => {
      state.chatMessages[state.chatMessages.length - 1] = { role: 'assistant', content: result.answer || '模型未返回文本内容。' };
      state.chatHistory.unshift({ title: prompt.slice(0, 18) + (prompt.length > 18 ? '…' : ''), date: '刚刚' });
    }).catch(error => {
      state.chatMessages[state.chatMessages.length - 1] = { role: 'assistant', content: error && error.message ? error.message : '当前模型暂时无法响应，请稍后重试。' };
      toast('文本任务请求失败，可修改内容后重试。', 'error');
    }).finally(() => {
      state.busy.text = false;
      persistDemoState();
      render();
    });
  }
  function bindEvents() {
    const mobileQuery = window.matchMedia('(max-width: 900px)');
    const syncMobileNav = open => {
      const isOpen = Boolean(open && mobileQuery.matches);
      const sidebar = $('.sidebar');
      sidebar.toggleClass('open', isOpen).attr('aria-hidden', mobileQuery.matches && !isOpen ? 'true' : 'false');
      if (sidebar[0]) sidebar[0].inert = Boolean(mobileQuery.matches && !isOpen);
      $('.nav-scrim').toggleClass('open', isOpen).attr('aria-hidden', isOpen ? 'false' : 'true');
      $('.mobile-nav-toggle').attr('aria-expanded', String(isOpen)).attr('aria-label', isOpen ? '关闭导航' : '打开导航');
      $('body').toggleClass('nav-open', isOpen);
    };
    const closeMobileNav = () => syncMobileNav(false);
    const accountMenuItems = () => $('#account-menu-popup [role="menuitem"]:not(:disabled)');
    const syncAccountMenu = (open, focusIndex) => {
      const isOpen = Boolean(open);
      const menu = $('#account-menu-popup');
      $('.account-menu-wrap').toggleClass('open', isOpen);
      $('.user-menu').attr('aria-expanded', String(isOpen)).attr('aria-label', isOpen ? '关闭账户菜单' : '打开账户菜单');
      menu.prop('hidden', !isOpen);
      if (isOpen && typeof focusIndex === 'number') {
        const items = accountMenuItems();
        if (items.length) items.eq((focusIndex + items.length) % items.length).trigger('focus');
      }
    };
    const closeAccountMenu = restoreFocus => {
      const wasOpen = !$('#account-menu-popup').prop('hidden');
      syncAccountMenu(false);
      if (restoreFocus && wasOpen) $('.user-menu').trigger('focus');
    };
    $('.side-link').on('click', closeMobileNav);
    $('[data-route]').on('click', function (event) { event.preventDefault(); closeMobileNav(); closeAccountMenu(); setRoute($(this).data('route')); });
    $('.user-menu').on('click', function (event) {
      event.stopPropagation();
      const shouldOpen = $('#account-menu-popup').prop('hidden');
      closeMobileNav();
      const detail = event.originalEvent && event.originalEvent.detail;
      syncAccountMenu(shouldOpen, shouldOpen && detail === 0 ? 0 : undefined);
    }).on('keydown', function (event) {
      if (!['ArrowDown', 'ArrowUp'].includes(event.key)) return;
      event.preventDefault();
      closeMobileNav();
      syncAccountMenu(true, event.key === 'ArrowDown' ? 0 : -1);
    });
    $('#account-menu-popup').on('keydown', function (event) {
      const items = accountMenuItems();
      const current = items.index(document.activeElement);
      if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        event.preventDefault();
        syncAccountMenu(true, current + (event.key === 'ArrowDown' ? 1 : -1));
      } else if (event.key === 'Home' || event.key === 'End') {
        event.preventDefault();
        syncAccountMenu(true, event.key === 'Home' ? 0 : -1);
      } else if (event.key === 'Escape') {
        event.preventDefault();
        event.stopPropagation();
        closeAccountMenu(true);
      } else if (event.key === 'Tab') {
        closeAccountMenu();
      }
    });
    $(document).off('pointerdown.accountMenu').on('pointerdown.accountMenu', event => { if (!$(event.target).closest('.account-menu-wrap').length) closeAccountMenu(); });
    $(document).off('keydown.accountMenu').on('keydown.accountMenu', event => { if (event.key === 'Escape' && !$('#account-menu-popup').prop('hidden')) { event.preventDefault(); closeAccountMenu(true); } });
    $('.mobile-nav-toggle').on('click', () => { closeAccountMenu(); syncMobileNav(!$('.sidebar').hasClass('open')); });
    $('.nav-scrim').on('click', closeMobileNav);
    $(window).off('resize.mobileNav').on('resize.mobileNav', () => syncMobileNav($('.sidebar').hasClass('open')));
    $(window).off('resize.accountMenu').on('resize.accountMenu', () => closeAccountMenu());
    $(document).off('keydown.mobileNav').on('keydown.mobileNav', event => { if (event.key === 'Escape' && $('.sidebar').hasClass('open')) { closeMobileNav(); $('.mobile-nav-toggle').trigger('focus'); } });
    syncMobileNav(false);
    syncAccountMenu(false);
    $('[data-logout]').on('click', function () {
      const button = $(this);
      button.prop('disabled', true).attr('aria-disabled', 'true');
      closeAccountMenu();
      window.PortalApi.logout().catch(error => {
        toast(error && error.message ? `服务端退出失败：${error.message}，已清除本机登录状态。` : '服务端退出失败，已清除本机登录状态。', 'error');
      }).finally(() => {
        window.PortalApi.clearToken();
        const loginUrl = safeNavigationUrl(window.PortalConfig.loginUrl) || 'auth.html';
        window.location.assign(loginUrl);
      });
    });
    $('[data-use-model]').on('click', function () { const model = $(this).data('use-model'); const found = models.find(item => item.name === model); if (!found) return; if (found.modelType === 'text' || found.type === '语言模型' || found.type === '本地模型') { state.currentChatModel = model; state.chatSessionId = null; setRoute('text'); } else if (found.modelType === 'image' || found.type === '生图模型') { state.selectedModelIds.image = found.id; setRoute('image'); } else if (found.modelType === 'audio' || found.type === 'TTS模型') { state.selectedModelIds.audio = found.id; setRoute('audio'); } else if (found.modelType === 'video' || found.type === '生视频模型') { state.selectedModelIds.video = found.id; setRoute('video'); } else toast('该模型的应用入口正在准备中。'); });
    $('[data-source]').on('click', function () { state.modelSource = $(this).data('source'); render(); });
    $('[data-group]').on('click', function () { state.modelGroup = $(this).data('group'); render(); });
    $('[data-type]').on('click', function () { state.modelType = $(this).data('type'); render(); });
    $('#model-search').on('input', function () { state.keyword = $(this).val(); $('.models-grid').html(modelResultsHtml()); });
    $('[data-chat-model]').on('click', function () { state.currentChatModel = $(this).data('chat-model'); state.chatSessionId = null; render(); });
    $('#send-chat').on('click', sendChat); $('#chat-input').on('keydown', event => { if (event.ctrlKey && event.key === 'Enter') sendChat(); });
    $('[data-prompt]').on('click', function () { $('#chat-input').val($(this).data('prompt')).focus(); });
    $('#new-chat, #new-chat-side').on('click', () => { state.chatSessionId = null; state.chatMessages = [{ role: 'assistant', content: '已创建新会话。告诉我你想完成什么，我会从这里开始协助。' }]; persistDemoState(); render(); });
    $('[data-image-mode]').on('click', function () { state.imageMode = $(this).data('image-mode'); render(); });
    $('[data-ratio]').on('click', function () { state.imageRatio = $(this).data('ratio'); render(); });
    $('#image-form').on('submit', function (event) { event.preventDefault(); const prompt = $('#image-prompt').val().trim(); if (!prompt) return toast('请先填写图像描述词。', 'error'); if (state.busy.image) return; state.busy.image = true; const title = prompt.slice(0, 22) + (prompt.length > 22 ? '…' : ''); const model = currentModel('image'); const submit = window.PortalConfig.demoMode ? Promise.resolve(createRecord('image', { title, mode: state.imageMode, meta: state.imageRatio, shouldFail: shouldSimulateFailure(prompt) })) : (model ? window.PortalApi.task('image', { model_id: model.id, prompt, params: { image_size: state.imageRatio.split(' ')[1].replace('×', 'x'), num: Number($('#image-count').val()) } }).then(result => remoteRecord('image', result, title, state.imageMode, state.imageRatio)) : Promise.reject({ message: '当前没有可用的图像模型。' })); submit.then(() => toast('图像任务已提交，正在生成。', 'success')).catch(error => toast(error && error.message ? error.message : '图像任务提交失败。', 'error')).finally(() => { state.busy.image = false; render(); }); });
    $('[data-audio-mode]').on('click', function () { state.audioMode = $(this).data('audio-mode'); render(); });
    $('[data-voice]').on('click', function () { state.selectedVoice = $(this).data('voice'); render(); });
    $('#audio-text').on('input', function () { $('#audio-count').text(`${$(this).val().length} / 2000 字符`); });
    $('#audio-form').on('submit', function (event) { event.preventDefault(); const text = $('#audio-text').val().trim(); if (!text) return toast('请先输入需要合成的文本。', 'error'); if (state.busy.audio) return; state.busy.audio = true; const record = createRecord('audio', { title: text.slice(0, 20) + (text.length > 20 ? '…' : ''), mode: state.audioMode, meta: `${text.length} 字符`, shouldFail: shouldSimulateFailure(text) }); if (!record) { state.busy.audio = false; return; } state.busy.audio = false; toast('声音任务已提交，请在历史中查看进度。', 'success'); render(); });
    $('[data-video-duration]').on('click', function () { state.videoDuration = $(this).data('video-duration'); render(); });
    $('#video-form').on('submit', function (event) { event.preventDefault(); const prompt = $('#video-prompt').val().trim(); if (!prompt) return toast('请先描述要生成的视频内容。', 'error'); if (state.busy.video) return; state.busy.video = true; const record = createRecord('video', { title: prompt.slice(0, 20) + (prompt.length > 20 ? '…' : ''), mode: '文生视频', meta: state.videoDuration, shouldFail: shouldSimulateFailure(prompt) }); if (!record) { state.busy.video = false; return; } state.busy.video = false; toast('视频任务已提交，渲染可能需要几分钟。', 'success'); render(); });
    if (!window.PortalConfig.demoMode) {
      $('#image-submit, #audio-submit, #video-submit').prop('disabled', false).removeAttr('aria-disabled').each(function () {
        $(this).html(`${icon('layui-icon-release')} ${this.id === 'video-submit' ? '文生视频' : this.id === 'audio-submit' ? '生成音频' : '立即生成'}`);
      });
      $('#audio-form').off('submit').on('submit', function (event) {
        event.preventDefault();
        const text = $('#audio-text').val().trim(); const model = currentModel('audio');
        if (!text) return toast('请先输入需要合成的文本。', 'error');
        if (!model) return toast('当前没有可用的音频模型。', 'error');
        state.busy.audio = true;
        window.PortalApi.request({ url: '/api/tasks/audio/clone', method: 'POST', data: { model_id: model.id, voice_name: state.selectedVoice, text } })
          .then(result => { remoteRecord('audio', result, text.slice(0, 20), state.audioMode, `${text.length} 字符`); toast('声音任务已提交。', 'success'); })
          .catch(error => toast(error && error.message ? error.message : '声音任务提交失败。', 'error'))
          .finally(() => { state.busy.audio = false; render(); });
      });
      $('#video-form').off('submit').on('submit', function (event) {
        event.preventDefault();
        const text = $('#video-prompt').val().trim(); const model = currentModel('video');
        if (!text) return toast('请先描述要生成的视频内容。', 'error');
        if (!model) return toast('当前没有可用的视频模型。', 'error');
        state.busy.video = true;
        window.PortalApi.task('video', { model_id: model.id, text, params: { duration_sec: Number.parseInt(state.videoDuration, 10), resolution: $('#video-resolution').val().startsWith('1080') ? '1920x1080' : '1280x720' } })
          .then(result => { remoteRecord('video', result, text.slice(0, 20), '文生视频', state.videoDuration); toast('视频任务已提交。', 'success'); })
          .catch(error => toast(error && error.message ? error.message : '视频任务提交失败。', 'error'))
          .finally(() => { state.busy.video = false; render(); });
      });
    }
    $('[data-retry]').on('click', function () { const id = String($(this).data('retry')); if (!window.PortalConfig.demoMode) { return window.PortalApi.taskRetry(id).then(result => { const record = [...state.imageHistory, ...state.audioHistory, ...state.videoHistory].find(item => String(item.id) === id); if (record) { record.status = result.status; record.error = ''; pollTask(record); } toast('任务已重新提交。', 'success'); render(); }).catch(error => toast(error && error.message ? error.message : '任务重试失败。', 'error')); } let record; ['imageHistory', 'audioHistory', 'videoHistory'].some(key => { record = state[key].find(item => String(item.id) === id); return Boolean(record); }); if (!record) return toast('没有找到需要重试的任务。', 'error'); record.status = 'pending'; record.error = ''; record.shouldFail = false; record.attempts = (record.attempts || 1) + 1; const mirror = state.tasks.find(item => String(item.id) === id); if (mirror) Object.assign(mirror, record); persistDemoState(); scheduleDemoTask(record, true); toast('任务已重新提交，本次演示将正常完成。', 'success'); render(); });
    $('[data-view-task]').on('click', function () {
      const id = String($(this).data('view-task'));
      const record = [...state.imageHistory, ...state.audioHistory, ...state.videoHistory].find(item => String(item.id) === id);
      if (!record) return toast('没有找到该任务，可能已被清理。', 'error');
      if (state.route === record.kind) return toast('当前页面已经显示该任务的最新状态。');
      setRoute(record.kind);
    });
    $('#clear-demo-history').on('click', function () { if (!window.confirm('确定清空全部演示任务记录吗？此操作无法撤销。')) return; state.imageHistory = []; state.audioHistory = []; state.videoHistory = []; state.tasks = []; taskTimers.forEach(timers => timers.forEach(timer => clearTimeout(timer))); taskTimers.clear(); persistDemoState(); toast('演示任务记录已清空。', 'success'); render(); });
    $('#recharge-open').on('click', function () {
      if (window.PortalConfig.demoMode) return;
      $('#recharge-panel').prop('hidden', false);
      $('#recharge-amount').trigger('focus');
    });
    $('#recharge-cancel').on('click', () => $('#recharge-panel').prop('hidden', true));
    $('[data-recharge-amount]').on('click', function () {
      $('#recharge-amount').val($(this).data('recharge-amount')).trigger('focus');
    });
    $('#recharge-form').on('submit', function (event) {
      event.preventDefault();
      if (window.PortalConfig.demoMode || state.busy.recharge) return;
      const yuan = Number($('#recharge-amount').val());
      if (!Number.isFinite(yuan) || yuan <= 0 || yuan > 10000) return toast('请输入 0.01–10000 元的充值金额。', 'error');
      const cents = Math.round(yuan * 100);
      if (cents <= 0) return toast('充值金额必须大于 0.01 元。', 'error');
      state.busy.recharge = true;
      $('#recharge-submit').prop('disabled', true).text('正在提交…');
      window.PortalApi.recharge({ amount: cents, payment_method: 'mock' }).then(result => {
        return window.PortalApi.wallet().then(wallet => {
          const balance = Number(wallet && wallet.balance);
          if (Number.isFinite(balance)) user.balance = (balance / 100).toFixed(2);
          return { result, refreshed: true };
        }).catch(() => ({ result, refreshed: false }));
      }).then(({ result, refreshed }) => {
        state.busy.recharge = false;
        $('#recharge-panel').prop('hidden', true);
        const order = result && result.order_no ? `订单号：${result.order_no}` : '';
        toast(refreshed ? `充值成功，余额已更新。${order}` : `充值成功，请刷新余额。${order}`, 'success');
        render();
      }).catch(error => {
        state.busy.recharge = false;
        $('#recharge-submit').prop('disabled', false).text('确认充值');
        toast(error && error.message ? error.message : '充值失败，请稍后重试。', 'error');
      });
    });
    $('#profile-form').on('submit', function (event) {
      event.preventDefault();
      const name = normalizeText($('#profile-name').val(), '', 30);
      const school = normalizeText($('#profile-school').val(), '', 100);
      if (!name || !school) return toast('昵称和学校不能为空。', 'error');
      if (window.PortalConfig.demoMode) {
        user.name = name;
        user.initial = Array.from(name)[0].toUpperCase();
        user.school = school;
        persistDemoState();
        toast('个人资料已保存到本机演示数据。', 'success');
        render();
        return;
      }
      if (state.busy.profile) return;
      state.busy.profile = true;
      $('#profile-submit').prop('disabled', true).text('正在保存…');
      window.PortalApi.updateProfile({ nickname: name, school }).then(profile => {
        const savedName = normalizeText(profile && profile.nickname, name, 30);
        const savedSchool = normalizeText(profile && profile.school, school, 100);
        user.name = savedName;
        user.initial = Array.from(savedName)[0].toUpperCase();
        user.school = savedSchool;
        const cached = window.PortalApi.currentUserSnapshot();
        if (cached && typeof cached === 'object') {
          const cachedProfile = cached.profile && typeof cached.profile === 'object' ? cached.profile : {};
          const nextProfile = Object.assign({}, cachedProfile, profile || {}, { nickname: savedName });
          const nextSnapshot = cached.user && typeof cached.user === 'object'
            ? Object.assign({}, cached, { user: Object.assign({}, cached.user, { school: savedSchool }), profile: nextProfile })
            : Object.assign({}, cached, { school: savedSchool, profile: nextProfile });
          const persistent = Boolean(localStorage.getItem(window.PortalApi.config.tokenKey));
          window.PortalApi.setCurrentUser(nextSnapshot, persistent);
        }
        state.busy.profile = false;
        toast('昵称和学校已保存。', 'success');
        render();
      }).catch(error => {
        state.busy.profile = false;
        $('#profile-submit').prop('disabled', false).text('保存资料');
        toast(error && error.message ? error.message : '个人资料保存失败，请稍后重试。', 'error');
      });
    });
  }

  window.addEventListener('portal:unauthorized', event => {
    const suffix = event.detail && event.detail.requestId ? `（请求ID：${event.detail.requestId}）` : '';
    toast(`登录状态已失效，请重新登录。${suffix}`, 'error');
  });
  hydrateDemoState();
  resumeDemoTasks();
  $(window).on('hashchange', render);
  $(function () { loadCurrentUser().then(loadModels).finally(render); });
}());
