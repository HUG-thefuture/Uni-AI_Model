/* global $ */
(function () {
  'use strict';

  // 联调时由成员2、4提供真实地址；演示模式不会向任何第三方模型厂商发送请求。
  window.PortalConfig = Object.assign({ apiBase: 'http://127.0.0.1:8000', demoMode: false, loginUrl: 'auth.html' }, window.PortalConfig || {});
  const DEMO_STORAGE_KEY = 'ai_portal_demo_state_v1';
  const taskTimers = new Map();
  let taskMonitor = null;
  const routeTitles = {
    home: '首页', models: '模型广场', text: '文本交互舱', image: '图像生成室',
    audio: '声音创作坊', video: '视频合成站', tasks: '创作历史', profile: '个人中心',
    billing: '个人账单', invoice: '发票管理', 'admin-models': '模型管理'
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
    // 预览应跟随最近一次提交，而不能依赖服务端列表的字符串时间排序。
    activeImageTaskId: null,
    audioMode: '声音合成',
    selectedVoice: '龙安洋',
    videoDuration: '5秒',
    videoImage: null,
    activeVideoTaskId: null,
    audioHistory: [],
    activeAudioTaskId: null,
    videoHistory: [],
    tasks: [],
    busy: { text: false, image: false, audio: false, video: false, profile: false, recharge: false },
    billing: { loaded: false, loading: false, error: '', wallet: null, records: [], page: 1, pageSize: 10, tab: 'usage', period: 'all', month: new Date().toISOString().slice(0, 7), type: 'all' },
    invoice: { loaded: false, loading: false, error: '', wallet: null, records: [], page: 1, pageSize: 10, period: 'all', month: new Date().toISOString().slice(0, 7), formOpen: false, formBusy: false },
    adminModels: { loaded: false, loading: false, error: '', items: [], page: 1, pageSize: 10, total: 0, formOpen: false, editingId: null, formBusy: false, fetchBusy: false, fetchModels: [] }
  };

  let user = { name: '用户', initial: 'U', balance: '—', school: '未加载学校', realName: '未认证', role: 'user' };
  const navItems = [
    ['home', '首页', 'layui-icon-home'], ['models', '模型广场', 'layui-icon-app'],
    ['text', '文本交互舱', 'layui-icon-dialogue'], ['image', '图像生成室', 'layui-icon-picture'],
    ['audio', '声音创作坊', 'layui-icon-voice'], ['video', '视频合成站', 'layui-icon-video'],
    ['tasks', '创作历史', 'layui-icon-list'], ['profile', '个人中心', 'layui-icon-user'],
    ['billing', '个人账单', 'layui-icon-rmb'], ['invoice', '发票管理', 'layui-icon-file'],
    ['admin-models', '模型管理', 'layui-icon-set']
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

  function taskKind(taskType) {
    if (taskType === 'image') return 'image';
    if (taskType === 'video') return 'video';
    if (taskType === 'audio' || taskType === 'audio_clone' || taskType === 'asr') return 'audio';
    return taskType || '';
  }

  function remoteRecord(kind, response, title, mode, meta) {
    const record = {
      id: response.task_id, title, mode, meta,
      createdAt: new Date().toLocaleString('zh-CN', { hour12: false }),
      status: response.status || 'pending', kind, attempts: 1, error: ''
    };
    state[`${kind}History`].unshift(record);
    state.tasks.unshift(Object.assign({}, record));
    if (kind === 'image') state.activeImageTaskId = String(record.id);
    if (kind === 'video') state.activeVideoTaskId = String(record.id);
    if (kind === 'audio') state.activeAudioTaskId = String(record.id);
    pollTask(record);
    return record;
  }

  function applyTaskDetail(record, detail) {
    record.status = detail.status || record.status;
    record.error = detail.error_message || '';
    record.resultText = detail.result_text || '';
    let urls = detail.result_urls;
    if (!urls && detail.result_url) {
      try { urls = JSON.parse(detail.result_url); } catch (error) { urls = [detail.result_url]; }
    }
    record.resultUrls = Array.isArray(urls) ? urls : [];
    const mirror = state.tasks.find(item => String(item.id) === String(record.id));
    if (mirror) Object.assign(mirror, record);
  }

  function resultUrl(value) {
    if (!value) return '';
    return /^https?:\/\//i.test(value) ? value : `${window.PortalConfig.apiBase}${value}`;
  }

  function pollTask(record, retries) {
    const remaining = retries == null ? 120 : retries;
    if (window.PortalConfig.demoMode || remaining <= 0 || ['succeeded', 'failed'].includes(record.status)) return;
    window.setTimeout(() => {
      window.PortalApi.taskDetail(record.id).then(detail => {
        applyTaskDetail(record, detail);
        if (['pending', 'processing'].includes(record.status)) pollTask(record, remaining - 1);
        const formEditing = document.activeElement && document.activeElement.closest && document.activeElement.closest('#image-form, #audio-form, #video-form');
        if (['image', 'audio', 'video', 'tasks'].includes(state.route) && !formEditing) render();
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
        id: item.id, name: item.name, modelType: item.model_type, vendor: item.vendor,
        type: typeNames[item.model_type] || '其他模型',
        group: item.provider_type === 'local' ? '私域知识模型' : '云端模型',
        source: item.provider_type === 'local' ? '私域模型' : '云端模型',
        tag: Array.isArray(item.capability_tags) ? item.capability_tags[0] || item.model_type : item.model_type,
        tags: Array.isArray(item.capability_tags) ? item.capability_tags : [],
        discount: item.price_per_call ? `¥${item.price_per_call}/次` : '免费',
        desc: item.description || '已接入平台模型服务。',
        tone: ['#386ee5', '#7951d4', '#2eaf91', '#bd4caf'][index % 4]
      }));
      // 媒体模型默认选中可用云端模型:优先 dashscope(百炼已配 key),否则取第一个
      ['image', 'audio', 'video'].forEach(type => {
        if (state.selectedModelIds[type] == null) {
          const preferred = models.find(m => m.modelType === type && m.vendor === 'dashscope') || models.find(m => m.modelType === type);
          if (preferred) state.selectedModelIds[type] = preferred.id;
        }
      });
      const selected = currentModel('text');
      if (selected) state.currentChatModel = selected.name;
    }).catch(error => {
      toast(error && error.message ? `模型列表加载失败：${error.message}` : '模型列表加载失败，请稍后刷新。', 'error');
    });
  }

  function loadChatHistory() {
    if (window.PortalConfig.demoMode || !window.PortalApi || !window.PortalApi.token()) return Promise.resolve();
    return window.PortalApi.listSessions(1, 50).then(data => {
      const rows = Array.isArray(data && data.items) ? data.items : [];
      state.chatHistory = rows.map(item => ({
        id: item.session_id,
        title: item.title || '新会话',
        date: item.updated_at ? String(item.updated_at).slice(5, 16).replace('T', ' ') : ''
      }));
    }).catch(() => undefined);
  }

  function loadTaskHistory() {
    if (window.PortalConfig.demoMode || !window.PortalApi || !window.PortalApi.token()) return Promise.resolve();
    return loadAllTaskPages().then(rows => {
      state.tasks = rows.map(item => { const record = { id: item.id, title: item.prompt || `任务 #${item.id}`, kind: taskKind(item.task_type), mode: item.task_type, meta: '', createdAt: item.created_at || '', status: item.status, error: item.error_message || '', resultText: item.result_text || '', resultUrls: [] }; applyTaskDetail(record, item); return record; });
      state.imageHistory = state.tasks.filter(item => item.kind === 'image');
      if (!state.activeImageTaskId && state.imageHistory[0]) state.activeImageTaskId = String(state.imageHistory[0].id);
      state.audioHistory = state.tasks.filter(item => item.kind === 'audio');
      if (!state.activeAudioTaskId && state.audioHistory[0]) state.activeAudioTaskId = String(state.audioHistory[0].id);
      state.videoHistory = state.tasks.filter(item => item.kind === 'video');
      if (!state.activeVideoTaskId && state.videoHistory[0]) state.activeVideoTaskId = String(state.videoHistory[0].id);
      startTaskMonitor();
    }).catch(() => undefined);
  }

  function loadAllTaskPages(page, collected) {
    const currentPage = page || 1;
    const results = collected || [];
    return window.PortalApi.taskList({ page: currentPage, page_size: 100 }).then(data => {
      const rows = Array.isArray(data && data.items) ? data.items : [];
      const all = results.concat(rows);
      const total = Number(data && data.total) || all.length;
      return all.length < total && rows.length ? loadAllTaskPages(currentPage + 1, all) : all;
    });
  }

  function startTaskMonitor() {
    if (taskMonitor || window.PortalConfig.demoMode || !window.PortalApi || !window.PortalApi.token()) return;
    taskMonitor = window.setInterval(() => {
      window.PortalApi.taskList({ page: 1, page_size: 100 }).then(data => {
        const rows = Array.isArray(data && data.items) ? data.items : [];
        const previous = new Map(state.tasks.map(item => [String(item.id), item]));
        rows.forEach(item => {
          const record = previous.get(String(item.id)) || { id: item.id, title: item.prompt || `任务 #${item.id}`, kind: taskKind(item.task_type), mode: item.task_type, meta: '', createdAt: item.created_at || '' };
          applyTaskDetail(record, item);
          record.status = item.status || record.status;
          record.error = item.error_message || '';
          record.title = record.title || item.prompt || `任务 #${item.id}`;
          record.kind = taskKind(item.task_type);
          previous.set(String(item.id), record);
        });
        state.tasks = Array.from(previous.values()).sort((a, b) => String(b.createdAt).localeCompare(String(a.createdAt)));
        state.imageHistory = state.tasks.filter(item => item.kind === 'image');
        if (!state.activeImageTaskId && state.imageHistory[0]) state.activeImageTaskId = String(state.imageHistory[0].id);
        state.audioHistory = state.tasks.filter(item => item.kind === 'audio');
        if (!state.activeAudioTaskId && state.audioHistory[0]) state.activeAudioTaskId = String(state.audioHistory[0].id);
        state.videoHistory = state.tasks.filter(item => item.kind === 'video');
        if (!state.activeVideoTaskId && state.videoHistory[0]) state.activeVideoTaskId = String(state.videoHistory[0].id);
        const editing = document.activeElement && document.activeElement.closest && document.activeElement.closest('#image-form, #audio-form, #video-form, #recharge-form, #invoice-form');
        const rechargeOpen = $('#recharge-panel').length && !$('#recharge-panel').prop('hidden');
        const invoiceOpen = $('#invoice-form').length > 0;
        if (!editing && !rechargeOpen && !invoiceOpen && ['image', 'audio', 'video', 'tasks', 'profile'].includes(state.route)) render();
      }).catch(() => undefined);
    }, 3000);
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
  function money(value, signed) {
    const amount = Number(value);
    if (!Number.isFinite(amount)) return '—';
    const sign = signed && amount > 0 ? '+' : '';
    return `${sign}${amount < 0 ? '-' : ''}¥${Math.abs(amount / 100).toFixed(2)}`;
  }
  function dateKey(value) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return '';
    return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
  }
  function dateText(value) {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString('zh-CN', { hour12: false });
  }
  function periodMatches(value, period, month) {
    if (period === 'all') return true;
    const key = dateKey(value);
    if (!key) return false;
    if (period === 'year') return key.slice(0, 4) === String(new Date().getFullYear());
    if (period === 'day') return key === dateKey(new Date());
    return key.slice(0, 7) === month;
  }
  function walletStatusLabel(status) {
    const labels = {
      paid: ['success', '已支付'], success: ['success', '已扣费'], pending: ['pending', '处理中'],
      failed: ['failed', '失败'], refunded: ['pending', '已退款'], cancelled: ['failed', '已取消']
    };
    const [style, label] = labels[status] || ['pending', '状态未知'];
    return `<span class="status-tag ${style}">${label}</span>`;
  }
  function invoiceStatusLabel(status) {
    const labels = { pending: ['pending', '待审核'], issued: ['success', '已开具'], rejected: ['failed', '已驳回'] };
    const [style, label] = labels[status] || ['pending', '状态未知'];
    return `<span class="status-tag ${style}">${label}</span>`;
  }
  function invoiceTypeLabel(type) { return type === 'enterprise' ? '企业' : '个人'; }
  function billingFilteredRecords() {
    return state.billing.records.filter(record => {
      if (state.billing.tab === 'usage' && record.type !== 'consumption') return false;
      if (state.billing.tab === 'balance' && record.type !== 'recharge') return false;
      if (state.billing.type !== 'all' && record.type !== state.billing.type) return false;
      return periodMatches(record.created_at, state.billing.period, state.billing.month);
    });
  }
  function invoiceFilteredRecords() {
    return state.invoice.records.filter(record => periodMatches(record.created_at, state.invoice.period, state.invoice.month));
  }
  function invoiceAvailableMinor() {
    const wallet = state.invoice.wallet || {};
    const recharged = Number(wallet.total_recharged) || 0;
    const consumed = Number(wallet.total_consumed) || 0;
    const billed = state.invoice.records.reduce((sum, record) => record.status === 'rejected' ? sum : sum + (Number(record.amount) || 0), 0);
    return Math.max(recharged - consumed - billed, 0);
  }
  function billingRows(records) {
    if (!records.length) {
      const body = state.billing.error
        ? `${escapeHtml(state.billing.error)} <button class="btn-quiet" id="billing-retry" type="button">重试</button>`
        : (state.billing.loading ? '正在加载账单…' : '暂无符合条件的账单记录。');
      return `<tr><td class="table-empty" colspan="7">${body}</td></tr>`;
    }
    return records.map(record => {
      const isConsumption = record.type === 'consumption';
      const detail = record.order_no || (isConsumption ? '模型调用' : '充值订单');
      return `<tr><td>${escapeHtml(dateText(record.created_at))}</td><td>${escapeHtml(detail)}</td><td>${isConsumption ? '模型调用' : '余额充值'}</td><td>—</td><td>—</td><td class="${Number(record.amount) < 0 ? 'amount-negative' : 'amount-positive'}">${escapeHtml(money(record.amount, true))}</td><td>${walletStatusLabel(record.status)}</td></tr>`;
    }).join('');
  }
  function invoiceRows(records) {
    if (!records.length) {
      const body = state.invoice.error
        ? `${escapeHtml(state.invoice.error)} <button class="btn-quiet" id="invoice-retry" type="button">重试</button>`
        : (state.invoice.loading ? '正在加载发票记录…' : '暂无开票记录');
      return `<tr><td class="table-empty" colspan="7">${body}</td></tr>`;
    }
    return records.map(record => `<tr><td>${escapeHtml(dateText(record.created_at))}</td><td>${escapeHtml(record.title || '—')}</td><td>${invoiceTypeLabel(record.type)}</td><td>${escapeHtml(money(record.amount))}</td><td>${invoiceStatusLabel(record.status)}</td><td>${record.status === 'rejected' ? '—' : '—'}</td><td>${escapeHtml(record.tax_no || '—')}</td></tr>`).join('');
  }
  function pageHead(title, subtitle, action) {
    return `<div class="page-head"><div><h1 class="page-title">${title}</h1><p class="page-subtitle">${subtitle}</p></div>${action || ''}</div>`;
  }
  function navTemplate(route) {
    return navItems.filter(([id]) => id !== 'admin-models' || user.role === 'admin').map(([id, label, iconName]) => `<a class="side-link ${route === id ? 'active' : ''}" href="#/${id}"${route === id ? ' aria-current="page"' : ''}>${icon(iconName)}<span>${label}</span></a>`).join('');
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
        <div class="chat-main"><div class="chat-toolbar"><div><strong>${escapeHtml(state.currentChatModel)}</strong><span> · 已准备就绪</span></div><button class="btn-secondary" id="new-chat" type="button">${icon('layui-icon-add-1')} 新建会话</button></div><div class="messages" id="message-list" role="log" aria-live="polite" aria-label="对话消息">${messages}</div><div class="chat-compose"><textarea id="chat-input" class="textarea-field" maxlength="2000" placeholder="输入你的问题或指令…（Enter 发送，Shift + Enter 换行）" aria-label="对话内容，按 Enter 发送，Shift 加 Enter 换行"></textarea><div class="compose-foot"><div class="chip-row"><button type="button" class="prompt-chip" data-prompt="请帮我优化下面这段文案：">文案优化</button><button type="button" class="prompt-chip" data-prompt="请把下面内容翻译成英文：">翻译</button><button type="button" class="prompt-chip" data-prompt="请用 Python 写一个函数：">代码编写</button></div><button class="btn-primary" id="send-chat" type="button" ${state.busy.text ? 'disabled' : ''}>${state.busy.text ? '生成中…' : '发送'} ${icon('layui-icon-release')}</button></div></div></div>
        <aside class="chat-history"><div style="display:flex;justify-content:space-between;align-items:center"><strong style="font-size:14px">历史会话</strong><button class="btn-quiet" id="new-chat-side" type="button" aria-label="新建会话" title="新建会话">${icon('layui-icon-add-1')}</button></div><div style="margin-top:14px">${state.chatHistory.length ? state.chatHistory.map(item => `<div class="history-row" data-chat-session="${escapeHtml(item.id)}" role="button" tabindex="0">${escapeHtml(item.title)}<small>${escapeHtml(item.date)}</small></div>`).join('') : '<div class="history-row">暂无历史会话，发送消息后自动保存。</div>'}</div></aside>
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
    const currentImage = state.imageHistory.find(item => String(item.id) === String(state.activeImageTaskId)) || state.imageHistory[0];
    const hasResult = currentImage && ['succeeded', 'success'].includes(currentImage.status);
    const imageModels = models.filter(item => item.modelType === 'image');
    const activeImageModel = currentModel('image');
    const imageModelOptions = imageModels.map(item => `<option value="${item.id}" ${String(state.selectedModelIds.image) === String(item.id) ? 'selected' : ''}>${escapeHtml(item.name)}</option>`).join('');
    return `${pageHead('图像生成室', '选择模型并输入描述词，把灵感转成可用的视觉素材。')}
      <section class="studio-layout"><div class="panel preview-stage"><div class="panel-pad" style="padding-bottom:12px"><h2 class="section-title">${icon('layui-icon-picture')}图像预览</h2></div><div class="preview-art ${hasResult ? 'demo-image' : ''}">${hasResult && currentImage.resultUrls && currentImage.resultUrls.length ? currentImage.resultUrls.map(url => `<img src="${escapeHtml(resultUrl(url))}" alt="${escapeHtml(currentImage.title)}" style="max-width:100%;max-height:420px;object-fit:contain" />`).join('') : `<div class="preview-art-inner">${icon(hasResult ? 'layui-icon-picture' : 'layui-icon-upload-drag')}<strong>${hasResult ? '图像生成完成' : currentImage ? '正在生成图像' : '等待生成图像'}</strong><span>${hasResult ? '服务端图像结果已返回。' : currentImage ? '新任务正在处理，完成后会替换当前预览。' : '提交提示词后，生成结果会在这里展示。'}</span></div>`}</div><div class="preview-caption">${hasResult && currentImage.resultUrls && currentImage.resultUrls.length ? `已返回 ${currentImage.resultUrls.length} 张图像，可右键保存。` : hasResult ? '任务完成，但服务端未返回图像地址。' : currentImage ? escapeHtml(currentImage.title) : '尚未提交任务'}</div></div>
        <form class="panel panel-pad" id="image-form"><div class="inline-model"><span>${icon('layui-icon-light')} 图像模型 <small>${escapeHtml(activeImageModel ? activeImageModel.name : '未选择')}</small></span><select class="select-field" id="image-model-select" aria-label="选择图像模型" ${imageModels.length ? '' : 'disabled'}>${imageModelOptions || '<option>暂无图像模型</option>'}</select></div><div class="tab-row" role="group" aria-label="图像生成模式"><button type="button" class="tab-btn ${state.imageMode === '文生图' ? 'active' : ''}" data-image-mode="文生图" aria-pressed="${state.imageMode === '文生图'}">文生图</button><button type="button" class="tab-btn" disabled aria-disabled="true" title="文件字段确认后开放">图生图 · 待开放</button></div><div class="form-block"><label class="field-label" for="image-prompt">输入描述词 <span class="required">*</span></label><textarea class="textarea-field" id="image-prompt" required placeholder="例如：一只可爱的橘猫在阳光下睡觉，写实风格，8K 分辨率…"></textarea></div><div class="form-block"><span class="field-label" id="image-ratio-label">图像尺寸</span><div class="ratio-row" role="group" aria-labelledby="image-ratio-label">${['1:1 1024×1024', '9:16 720×1280', '16:9 1280×720'].map(item => `<button type="button" class="duration-btn ${state.imageRatio === item ? 'active' : ''}" data-ratio="${item}" aria-pressed="${state.imageRatio === item}">${item}</button>`).join('')}</div></div><div class="advanced"><div class="form-grid"><div><label class="field-label" for="image-count">生成数量</label><select class="select-field" id="image-count"><option value="1">1 张</option><option value="2">2 张</option><option value="4">4 张</option></select></div><div><label class="field-label" for="image-negative">负面提示词</label><input id="image-negative" class="field" placeholder="模糊、低质量、变形…" /></div></div></div><button class="btn-primary wide-action" id="image-submit" type="submit" ${state.busy.image || !window.PortalConfig.demoMode ? 'disabled' : ''}>${icon('layui-icon-release')} ${state.busy.image ? '正在提交…' : (window.PortalConfig.demoMode ? '立即生成' : '接口待接入')}</button><p class="state-note">${icon('layui-icon-tips')} ${window.PortalConfig.demoMode ? '演示记录会保存在本机；提示词包含“#失败”可验证失败与重试。' : '真实图像接口尚未挂载，当前不会提交或生成本地假任务。'}</p></form></section>
      <section class="panel panel-pad history-panel"><h2 class="section-title">${icon('layui-icon-list')}生成历史</h2><div class="table-wrap" role="region" aria-label="创作记录表格" tabindex="0"><table class="data-table"><thead><tr><th scope="col">提示词</th><th scope="col">类型</th><th scope="col">尺寸</th><th scope="col">创建时间</th><th scope="col">状态</th><th scope="col">操作</th></tr></thead><tbody>${historyRows(state.imageHistory, '生成')}</tbody></table></div></section>`;
  }

  function audioView() {
    const current = state.audioHistory.find(item => String(item.id) === String(state.activeAudioTaskId)) || state.audioHistory[0];
    const running = current && ['pending', 'processing'].includes(current.status);
    const complete = current && ['succeeded', 'success'].includes(current.status);
    const failed = current && current.status === 'failed';
    const voices = [['龙安洋', '阳光大男孩 · 中英双语'], ['龙安欢', '欢脱元气女 · 中英双语'], ['清雅老师', '知性女声 · 普通话'], ['星河少年', '沉稳男声 · 普通话']];
    const audioModels = models.filter(item => item.modelType === 'audio' && item.available !== false);
    const activeAudioModel = currentModel('audio');
    const audioModelOptions = audioModels.map(item => `<option value="${item.id}" ${String(state.selectedModelIds.audio) === String(item.id) ? 'selected' : ''}>${escapeHtml(item.name)}</option>`).join('');
    const isAsr = state.audioMode === '语音识别';
    const ttsControls = `<div class="form-block"><label class="field-label" for="audio-text">输入文本 <span class="required">*</span></label><textarea class="textarea-field" id="audio-text" aria-describedby="audio-count" maxlength="2000" required placeholder="输入您想转换成声音的文本内容…"></textarea><div class="state-note" style="margin-top:6px">${icon('layui-icon-note')} <span id="audio-count" aria-live="polite">0 / 2000 字符</span></div></div><div class="form-grid"><div><label class="field-label" for="audio-speed">语速</label><input class="field" id="audio-speed" type="number" step="0.1" min="0.5" max="2" value="1" /></div><div><label class="field-label" for="audio-format">音频格式</label><select class="select-field" id="audio-format"><option>MP3（默认）</option><option>WAV</option><option>PCM</option><option>OPUS</option></select></div></div><div class="form-block" style="margin-top:18px"><span class="field-label" id="voice-label">选择配音员</span><div class="audio-voice-grid" role="group" aria-labelledby="voice-label">${voices.map(([name, detail]) => `<button type="button" class="voice-card ${state.selectedVoice === name ? 'active' : ''}" data-voice="${name}" aria-pressed="${state.selectedVoice === name}"><strong>${name}</strong><span>${detail}</span></button>`).join('')}</div></div>`;
    const asrControls = `<div class="form-block"><label class="field-label" for="audio-file">上传音频文件 <span class="required">*</span></label><input class="field" id="audio-file" type="file" accept="audio/mpeg,audio/wav,audio/x-m4a,audio/mp4" /><p class="state-note" id="audio-file-status">支持 mp3 / wav / m4a，不超过 10MB。</p></div>`;
    return `${pageHead('声音创作坊', '将文字转成自然语音，并保留每一次创作的任务记录。')}
      <section class="studio-layout"><div class="panel preview-stage"><div class="panel-pad" style="padding-bottom:12px"><h2 class="section-title">${icon('layui-icon-voice')}音频预览</h2></div><div class="preview-art" style="min-height:250px;background:linear-gradient(140deg,#182545,#283c77)"><div class="preview-art-inner">${icon(failed ? 'layui-icon-error' : complete ? 'layui-icon-headset' : 'layui-icon-voice')}<strong>${failed ? '音频生成失败' : complete ? '音频已生成' : running ? '正在生成音频' : '未开始生成'}</strong><span>${failed ? escapeHtml(current.error || '任务失败，请检查后重试。') : complete ? '服务端音频结果已返回，可直接播放或下载。' : running ? '任务已提交，正在等待模型服务处理。' : '提交文本后可查看任务状态。'}</span></div></div><div class="preview-caption">${complete ? (current.resultUrls && current.resultUrls[0] ? `<audio controls preload="metadata" src="${escapeHtml(resultUrl(current.resultUrls[0]))}"></audio>` : '任务完成，但服务端未返回音频地址。') : failed ? escapeHtml(current.error || '可在下方历史记录中重新提交。') : running ? escapeHtml(current.title) : '声音任务通常以异步方式处理，请勿重复提交。'}</div></div>
        <form class="panel panel-pad" id="audio-form"><div class="inline-model"><span>${icon('layui-icon-light')} 语音模型 <small>${escapeHtml(activeAudioModel ? activeAudioModel.name : '未选择')}</small></span><select class="select-field" id="audio-model-select" aria-label="选择语音模型" ${audioModels.length ? '' : 'disabled'}>${audioModelOptions || '<option>暂无语音模型</option>'}</select></div><div class="tab-row" role="group" aria-label="声音创作模式">${['声音合成', '声音克隆', '语音识别', '长文本转音频'].map(item => `<button type="button" class="tab-btn ${state.audioMode === item ? 'active' : ''}" aria-pressed="${state.audioMode === item}" data-audio-mode="${item}">${item}</button>`).join('')}</div>${isAsr ? asrControls : ttsControls}<button class="btn-primary wide-action" id="audio-submit" type="submit" ${state.busy.audio || !window.PortalConfig.demoMode ? 'disabled' : ''}>${icon('layui-icon-release')} ${state.busy.audio ? '正在提交…' : (window.PortalConfig.demoMode ? '生成音频' : '接口待接入')}</button><p class="state-note">${icon('layui-icon-tips')} ${window.PortalConfig.demoMode ? '文本包含“#失败”可验证失败任务和重新提交。' : '真实声音接口尚未挂载，当前不会提交或生成本地假任务。'}</p></form></section>
      <section class="panel panel-pad history-panel"><h2 class="section-title">${icon('layui-icon-list')}创作历史</h2><div class="table-wrap" role="region" aria-label="创作记录表格" tabindex="0"><table class="data-table"><thead><tr><th scope="col">作品名称</th><th scope="col">模式</th><th scope="col">时长/字数</th><th scope="col">完成时间</th><th scope="col">状态</th><th scope="col">操作</th></tr></thead><tbody>${historyRows(state.audioHistory, '创作')}</tbody></table></div></section>`;
  }

  function videoView() {
    const current = state.videoHistory.find(item => String(item.id) === String(state.activeVideoTaskId)) || state.videoHistory[0];
    const running = current && ['pending', 'processing'].includes(current.status);
    const complete = current && ['succeeded', 'success'].includes(current.status);
    const failed = current && current.status === 'failed';
    const videoResults = complete && current && current.resultUrls ? current.resultUrls : [];
    const videoModels = models.filter(item => item.modelType === 'video');
    const activeVideoModel = currentModel('video');
    const videoModelOptions = videoModels.map(item => `<option value="${item.id}" ${String(state.selectedModelIds.video) === String(item.id) ? 'selected' : ''}>${escapeHtml(item.name)}</option>`).join('');
    return `${pageHead('视频合成站', '以文本、图片或音频条件组合成一段可控的短视频。')}
      <section class="studio-layout"><div class="panel preview-stage"><div class="panel-pad" style="padding-bottom:12px"><h2 class="section-title">${icon('layui-icon-video')}视频预览</h2></div><div class="video-preview">${videoResults.length ? videoResults.map((url, index) => `<figure style="margin:0 0 16px"><video controls preload="metadata" src="${escapeHtml(resultUrl(url))}" style="width:100%;max-height:420px"></video><figcaption class="preview-caption">结果 ${index + 1} · <a href="${escapeHtml(resultUrl(url))}" target="_blank" rel="noopener">在新窗口打开/下载</a></figcaption></figure>`).join('') : `<div class="preview-art-inner">${icon(failed ? 'layui-icon-error' : complete ? 'layui-icon-play' : 'layui-icon-video')}<strong>${failed ? '视频生成失败' : complete ? '视频生成完成' : running ? '正在渲染视频' : '视频预览区域'}</strong><span>${failed ? escapeHtml(current.error || '任务失败，请检查参数后重试。') : complete ? '服务端未返回可播放的视频地址。' : '生成完成后将在此显示结果。'}</span></div>`}</div><div class="preview-caption">${running ? '渲染过程可能需要 3–5 分钟，请耐心等待。' : complete ? `${escapeHtml(current.title)}${videoResults.length > 1 ? ` · 共 ${videoResults.length} 个结果` : ''}` : failed ? escapeHtml(current.error || '可在下方历史记录中重新提交。') : '无首帧时将采用文生视频模型。'}</div></div>
        <form class="panel panel-pad" id="video-form"><div class="inline-model"><span>${icon('layui-icon-light')} 视频模型 <small>${escapeHtml(activeVideoModel ? activeVideoModel.name : '未选择')}</small></span><select class="select-field" id="video-model-select" aria-label="选择视频模型" ${videoModels.length ? '' : 'disabled'}>${videoModelOptions || '<option>暂无视频模型</option>'}</select></div><div class="form-block"><label class="field-label" for="video-prompt">视频描述提示词 <span class="required">*</span></label><textarea class="textarea-field" maxlength="500" id="video-prompt" required placeholder="描述您想要生成的视频内容…"></textarea></div><div class="form-block"><label class="field-label" for="video-negative">反向提示词（可选）</label><input class="field" id="video-negative" value="模糊、失真、低质量、变形、扭曲、水印、文字" /></div><div class="form-block"><span class="field-label" id="video-duration-label">视频时长</span><div class="duration-row" role="group" aria-labelledby="video-duration-label">${['5秒', '10秒', '15秒'].map(item => `<button type="button" class="duration-btn ${state.videoDuration === item ? 'active' : ''}" data-video-duration="${item}" aria-pressed="${state.videoDuration === item}">${item}</button>`).join('')}</div></div><div class="form-grid"><div><label class="field-label" for="video-resolution">分辨率</label><select class="select-field" id="video-resolution"><option>720P（高清）</option><option>1080P（超清）</option></select></div><div><span class="field-label">音频设置</span><button class="upload-drop" type="button" disabled aria-disabled="true" title="上传字段确认后开放">${icon('layui-icon-upload')} 音频上传 · 待开放</button></div></div><button class="btn-primary wide-action" id="video-submit" type="submit" ${state.busy.video || !window.PortalConfig.demoMode ? 'disabled' : ''}>${icon('layui-icon-release')} ${state.busy.video ? '正在提交…' : (window.PortalConfig.demoMode ? '文生视频' : '接口待接入')}</button><p class="state-note">${icon('layui-icon-tips')} ${window.PortalConfig.demoMode ? '提示词包含“#失败”可验证失败任务和重新提交。' : '真实视频接口尚未挂载，当前不会提交或生成本地假任务。'}</p><div class="tip-box"><strong>${icon('layui-icon-tips')} 温馨提示</strong>有首帧时可改用图生视频；尾帧可选，用于控制视频结束画面。长任务提交后请在创作历史中查看状态。</div></form></section>
      <section class="panel panel-pad history-panel"><h2 class="section-title">${icon('layui-icon-list')}创作历史</h2><div class="table-wrap" role="region" aria-label="创作记录表格" tabindex="0"><table class="data-table"><thead><tr><th scope="col">作品名称</th><th scope="col">合成模式</th><th scope="col">时长</th><th scope="col">创建时间</th><th scope="col">状态</th><th scope="col">操作</th></tr></thead><tbody>${historyRows(state.videoHistory, '创作')}</tbody></table></div></section>`;
  }

  function tasksView() {
    const all = [...state.videoHistory, ...state.audioHistory, ...state.imageHistory].sort((a, b) => b.createdAt.localeCompare(a.createdAt));
    const action = window.PortalConfig.demoMode && all.length ? '<button type="button" class="btn-secondary" id="clear-demo-history">清空演示记录</button>' : '';
    return `${pageHead('创作历史', '集中查看你提交过的图像、声音和视频任务。', action)}
      <section class="panel panel-pad"><div class="notice">${icon('layui-icon-tips')}<div>${window.PortalConfig.demoMode ? '这里只展示当前登录用户的任务。任务失败时可以重新提交；正式系统会由后端保证失败任务不扣费。' : '任务列表会从服务端加载，并自动轮询处理中的任务；结果地址返回后可直接预览。'}</div></div><div class="table-wrap" style="margin-top:18px" role="region" aria-label="全部创作任务表格" tabindex="0"><table class="data-table"><thead><tr><th scope="col">任务名称</th><th scope="col">类型</th><th scope="col">参数</th><th scope="col">创建时间</th><th scope="col">状态</th><th scope="col">操作</th></tr></thead><tbody>${historyRows(all, '任务')}</tbody></table></div></section>`;
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
        <section class="panel panel-pad"><h2 class="section-title">${icon('layui-icon-user')}基础资料</h2><form id="profile-form"><div class="form-grid"><div class="form-block"><label class="field-label" for="profile-name">昵称</label><input class="field" id="profile-name" autocomplete="nickname" maxlength="30" value="${escapeHtml(user.name)}" /></div><div class="form-block"><label class="field-label" for="profile-school">学校</label><input class="field" id="profile-school" autocomplete="organization" maxlength="50" value="${escapeHtml(user.school)}" /></div><div class="form-block"><label class="field-label" for="profile-verification">实名认证状态</label><input class="field" id="profile-verification" value="${escapeHtml(user.realName)}" disabled /></div><div class="form-block"><label class="field-label" for="profile-role">账号角色</label><input class="field" id="profile-role" value="${escapeHtml(roleLabel)}" disabled /></div></div><button class="btn-primary" id="profile-submit" type="submit" ${state.busy.profile ? 'disabled' : ''}>${state.busy.profile ? '正在保存…' : '保存资料'}</button></form><div class="notice" style="margin-top:20px">${icon('layui-icon-tips')}<div>钱包余额、账单和发票记录均来自后端接口。金额按“分”保存，页面只负责格式化显示。</div></div></section>
      </section>`;
  }

  function billingView() {
    const records = billingFilteredRecords();
    const pageCount = Math.max(1, Math.ceil(records.length / state.billing.pageSize));
    const page = Math.min(state.billing.page, pageCount);
    if (state.billing.page !== page) state.billing.page = page;
    const start = (page - 1) * state.billing.pageSize;
    const pageRecords = records.slice(start, start + state.billing.pageSize);
    const wallet = state.billing.wallet || {};
    const month = escapeHtml(state.billing.month);
    const previousDisabled = page <= 1 ? 'disabled aria-disabled="true"' : '';
    const nextDisabled = page >= pageCount ? 'disabled aria-disabled="true"' : '';
    const action = `<button class="btn-primary" type="button" data-route="profile">${icon('layui-icon-rmb')} 立即充值</button>`;
    return `${pageHead('个人账单', '查看余额和使用记录。', action)}
      <section class="billing-summary">
        <article class="panel billing-card"><div class="billing-card-head"><span>当前余额</span><span class="status-tag success">可用</span></div><strong class="billing-amount">${escapeHtml(money(wallet.balance))}</strong><span class="billing-unit">人民币</span></article>
        <article class="panel billing-card"><div class="billing-card-head"><span>累计消费</span><span class="text-muted">钱包统计</span></div><strong class="billing-amount">${escapeHtml(money(wallet.total_consumed))}</strong><span class="billing-unit">人民币</span></article>
      </section>
      <section class="panel panel-pad">
        <div class="billing-section-head"><div><h2 class="section-title">${icon('layui-icon-list')}账单明细</h2><p class="text-muted">钱包流水按金额分单位展示，模型原始用量由服务端记录后显示。</p></div></div>
        <div class="billing-toolbar">
          <div class="tab-row" role="tablist" aria-label="账单记录类型"><button type="button" class="tab-btn ${state.billing.tab === 'usage' ? 'active' : ''}" data-billing-tab="usage" aria-selected="${state.billing.tab === 'usage'}">使用记录</button><button type="button" class="tab-btn ${state.billing.tab === 'balance' ? 'active' : ''}" data-billing-tab="balance" aria-selected="${state.billing.tab === 'balance'}">余额变更记录</button></div>
          <div class="filters" role="group" aria-label="账单时间范围">${[['all', '全部'], ['year', '年'], ['month', '月'], ['day', '日'], ['custom', '自定义']].map(([value, label]) => `<button type="button" class="filter-btn ${state.billing.period === value ? 'active' : ''}" data-billing-period="${value}" aria-pressed="${state.billing.period === value}">${label}</button>`).join('')}</div>
          <label class="billing-month"><span class="sr-only">账单月份</span><input class="field" id="billing-month" type="month" value="${month}" aria-label="账单月份" /></label>
          <select class="select-field billing-type" id="billing-type" aria-label="账单分类"><option value="all" ${state.billing.type === 'all' ? 'selected' : ''}>所有分类</option><option value="consumption" ${state.billing.type === 'consumption' ? 'selected' : ''}>模型调用</option><option value="recharge" ${state.billing.type === 'recharge' ? 'selected' : ''}>余额充值</option></select>
        </div>
        <div class="notice billing-notice">${icon('layui-icon-tips')}<div>当前接口提供充值和消费流水；模型名称、原始用量与单位暂未返回，因此用“—”标记，不生成虚假统计。</div></div>
        <div class="table-wrap billing-table-wrap" role="region" aria-label="个人账单表格" tabindex="0"><table class="data-table"><thead><tr><th scope="col">时间</th><th scope="col">模型/订单</th><th scope="col">分类</th><th scope="col">原始用量</th><th scope="col">用量单位</th><th scope="col">账单金额</th><th scope="col">状态</th></tr></thead><tbody>${billingRows(pageRecords)}</tbody></table></div>
        <div class="billing-pagination"><span>共 ${records.length} 条</span><div><button type="button" class="btn-quiet" data-billing-page="-1" ${previousDisabled}>上一页</button><span>第 ${page} / ${pageCount} 页</span><button type="button" class="btn-quiet" data-billing-page="1" ${nextDisabled}>下一页</button></div></div>
      </section>`;
  }

  function invoiceView() {
    const records = invoiceFilteredRecords();
    const pageCount = Math.max(1, Math.ceil(records.length / state.invoice.pageSize));
    const page = Math.min(state.invoice.page, pageCount);
    if (state.invoice.page !== page) state.invoice.page = page;
    const pageRecords = records.slice((page - 1) * state.invoice.pageSize, page * state.invoice.pageSize);
    const wallet = state.invoice.wallet || {};
    const available = invoiceAvailableMinor();
    const billed = state.invoice.records.reduce((sum, record) => record.status === 'rejected' ? sum : sum + (Number(record.amount) || 0), 0);
    const latest = state.invoice.records[0];
    const maxAmount = Math.max(available / 100, 0.01).toFixed(2);
    const form = state.invoice.formOpen ? `<section class="panel panel-pad invoice-form-panel"><div class="billing-section-head"><div><h2 class="section-title">${icon('layui-icon-edit')}提交开票申请</h2><p class="text-muted">申请金额按人民币元填写，服务端按分保存。</p></div><button class="btn-quiet" id="invoice-cancel" type="button">取消</button></div><form id="invoice-form"><div class="form-grid"><div class="form-block"><label class="field-label" for="invoice-amount">发票金额（元）<span class="required">*</span></label><input class="field" id="invoice-amount" type="number" min="0.01" max="${maxAmount}" step="0.01" inputmode="decimal" required placeholder="例如 10.00" /></div><div class="form-block"><label class="field-label" for="invoice-type">发票类型<span class="required">*</span></label><select class="select-field" id="invoice-type"><option value="personal">个人</option><option value="enterprise">企业</option></select></div></div><div class="form-block"><label class="field-label" for="invoice-title">发票抬头<span class="required">*</span></label><input class="field" id="invoice-title" maxlength="100" required placeholder="请输入发票抬头" /></div><div class="form-block"><label class="field-label" for="invoice-tax-no">企业税号</label><input class="field" id="invoice-tax-no" maxlength="50" placeholder="企业发票填写，个人发票可留空" /></div><p class="state-note">${icon('layui-icon-tips')} 当前可开票金额：${escapeHtml(money(available))}；申请后需等待管理员审核。</p><div class="invoice-form-actions"><button class="btn-quiet" id="invoice-cancel-bottom" type="button">取消</button><button class="btn-primary" id="invoice-submit" type="submit" ${state.invoice.formBusy ? 'disabled' : ''}>${state.invoice.formBusy ? '正在提交…' : '提交申请'}</button></div></form></section>` : '';
    const info = latest ? `<div class="invoice-info-card"><div><span>默认抬头</span><strong>${escapeHtml(latest.title || '—')}</strong></div><div><span>发票类型</span><strong>${invoiceTypeLabel(latest.type)}</strong></div><div><span>税号</span><strong>${escapeHtml(latest.tax_no || '—')}</strong></div></div>` : `<div class="empty-state invoice-empty">${icon('layui-icon-file')}<div>暂无发票信息<br><small>提交一次开票申请后会保留最近使用的抬头。</small></div></div>`;
    const previousDisabled = page <= 1 ? 'disabled aria-disabled="true"' : '';
    const nextDisabled = page >= pageCount ? 'disabled aria-disabled="true"' : '';
    const action = `<button class="btn-primary" id="invoice-open" type="button">${icon('layui-icon-add-1')} 去开票</button>`;
    return `${pageHead('发票管理', '管理开票信息与记录。', action)}
      <section class="invoice-grid">
        <article class="panel invoice-amount-card"><div class="billing-card-head"><span>可开票金额</span><span class="status-tag ${available > 0 ? 'success' : 'pending'}">${available > 0 ? '可申请' : '暂无额度'}</span></div><strong class="billing-amount">${escapeHtml(money(available))}</strong><span class="billing-unit">人民币</span><p class="invoice-formula">计算口径：累计充值 ${escapeHtml(money(wallet.total_recharged))} - 累计消费 ${escapeHtml(money(wallet.total_consumed))} - 已申请开票 ${escapeHtml(money(billed))}</p></article>
        <section class="panel panel-pad invoice-info-panel"><div class="billing-section-head"><div><h2 class="section-title">${icon('layui-icon-form')}发票信息</h2><p class="text-muted">保存最近一次申请使用的抬头与税号。</p></div><button class="btn-secondary" data-invoice-open type="button">${latest ? '编辑信息' : '去添加'}</button></div>${info}</section>
      </section>
      ${form}
      <section class="panel panel-pad invoice-records-panel"><div class="billing-section-head"><div><h2 class="section-title">${icon('layui-icon-list')}开票记录</h2></div><div class="filters" role="group" aria-label="发票时间范围">${[['all', '全部'], ['year', '年'], ['month', '月'], ['day', '日'], ['custom', '自定义']].map(([value, label]) => `<button type="button" class="filter-btn ${state.invoice.period === value ? 'active' : ''}" data-invoice-period="${value}" aria-pressed="${state.invoice.period === value}">${label}</button>`).join('')}<label class="billing-month"><span class="sr-only">发票月份</span><input class="field" id="invoice-month" type="month" value="${escapeHtml(state.invoice.month)}" aria-label="发票月份" /></label></div></div><div class="table-wrap" role="region" aria-label="开票记录表格" tabindex="0"><table class="data-table"><thead><tr><th scope="col">申请时间</th><th scope="col">发票抬头</th><th scope="col">发票类型</th><th scope="col">发票金额</th><th scope="col">发票状态</th><th scope="col">驳回原因</th><th scope="col">备注/税号</th></tr></thead><tbody>${invoiceRows(pageRecords)}</tbody></table></div><div class="billing-pagination"><span>共 ${records.length} 条</span><div><button type="button" class="btn-quiet" data-invoice-page="-1" ${previousDisabled}>上一页</button><span>第 ${page} / ${pageCount} 页</span><button type="button" class="btn-quiet" data-invoice-page="1" ${nextDisabled}>下一页</button></div></div></section>`;
  }
  function adminVendorIsBuiltin(vendor) {
    return ['siliconflow', 'dashscope', 'ollama', 'mock'].includes(String(vendor || '').trim().toLowerCase());
  }
  function adminProviderTypeLabel(value) {
    return value === 'local' ? '本地' : '云端';
  }
  function adminModelTypeLabel(value) {
    return { text: '文本', image: '图像', audio: '音频', video: '视频' }[value] || '其他';
  }
  function adminModelsAccessDeniedView() {
    return `${pageHead('模型管理', '配置模型供应商与可用模型。')}
      <section class="panel panel-pad"><div class="notice">${icon('layui-icon-password')}<div>该页面仅管理员可访问，当前账号没有权限。</div></div></section>`;
  }
  function adminModelsRows(items) {
    if (!items.length) return `<tr><td class="table-empty" colspan="8">暂无模型，点击右上角「新增模型」添加。</td></tr>`;
    return items.map(item => {
      const price = item.price_per_call == null || item.price_per_call === '' ? '免费' : `${escapeHtml(item.price_per_call)}/次`;
      const statusStyle = item.status === 'disabled' ? 'failed' : 'success';
      const statusText = item.status === 'disabled' ? '已停用' : item.status === 'enabled' ? '启用' : escapeHtml(item.status || '未知');
      return `<tr>
        <td>${escapeHtml(item.name || '—')}</td>
        <td>${escapeHtml(item.model_code || '—')}</td>
        <td>${escapeHtml(item.vendor || '—')}</td>
        <td>${escapeHtml(adminProviderTypeLabel(item.provider_type))}</td>
        <td>${escapeHtml(adminModelTypeLabel(item.model_type))}</td>
        <td>${escapeHtml(price)}</td>
        <td><span class="status-tag ${statusStyle}">${statusText}</span></td>
        <td>
          <button type="button" class="btn-quiet" data-admin-edit="${escapeHtml(item.id)}">编辑</button>
          <button type="button" class="btn-quiet" data-admin-toggle="${escapeHtml(item.id)}">${item.status === 'disabled' ? '启用' : '停用'}</button>
          <button type="button" class="btn-quiet" data-admin-delete="${escapeHtml(item.id)}">删除</button>
        </td>
      </tr>`;
    }).join('');
  }
  function adminModelsFormTemplate() {
    const editing = state.adminModels.editingId != null;
    const current = editing ? state.adminModels.items.find(item => String(item.id) === String(state.adminModels.editingId)) : null;
    const name = current ? current.name : '';
    const modelCode = current ? current.model_code : '';
    const providerType = current ? current.provider_type : 'online';
    const modelType = current ? current.model_type : 'text';
    const vendor = current ? current.vendor : '';
    const endpoint = current ? current.endpoint : '';
    const price = current ? current.price_per_call : '';
    const description = current ? current.description : '';
    const capabilityTags = Array.isArray(current && current.capability_tags) ? current.capability_tags.join(',') : (current && current.capability_tags ? String(current.capability_tags) : '');
    const fetchSelect = state.adminModels.fetchModels.length
      ? `<select class="select-field" id="admin-fetch-select" aria-label="获取到的模型"><option value="">— 选择模型 —</option>${state.adminModels.fetchModels.map(m => `<option value="${escapeHtml(m.id)}" data-name="${escapeHtml(m.name)}">${escapeHtml(m.name)}（${escapeHtml(m.id)}）</option>`).join('')}</select>`
      : '';
    return `<form id="admin-model-form">
      <div class="form-grid">
        <div class="form-block"><label class="field-label" for="admin-name">展示名 <span class="required">*</span></label><input class="field" id="admin-name" maxlength="60" required value="${escapeHtml(name)}" placeholder="例如 Qwen-Plus" /></div>
        <div class="form-block"><label class="field-label" for="admin-model-code">model_code <span class="required">*</span></label><input class="field" id="admin-model-code" maxlength="120" required value="${escapeHtml(modelCode)}" placeholder="例如 qwen-plus" /></div>
      </div>
      <div class="form-grid">
        <div class="form-block"><label class="field-label" for="admin-provider-type">供应商类型</label><select class="select-field" id="admin-provider-type"><option value="online" ${providerType === 'online' ? 'selected' : ''}>online（云端）</option><option value="local" ${providerType === 'local' ? 'selected' : ''}>local（本地）</option></select></div>
        <div class="form-block"><label class="field-label" for="admin-model-type">模型类型</label><select class="select-field" id="admin-model-type"><option value="text" ${modelType === 'text' ? 'selected' : ''}>文本（text）</option><option value="image" ${modelType === 'image' ? 'selected' : ''}>图像（image）</option><option value="audio" ${modelType === 'audio' ? 'selected' : ''}>音频（audio）</option><option value="video" ${modelType === 'video' ? 'selected' : ''}>视频（video）</option></select></div>
      </div>
      <div class="form-block"><label class="field-label" for="admin-vendor">供应商 vendor <span class="required">*</span></label><input class="field" id="admin-vendor" maxlength="60" required value="${escapeHtml(vendor)}" placeholder="内置 siliconflow / dashscope / ollama / mock，或自定义供应商名" /></div>
      <div class="form-block"><label class="field-label" for="admin-endpoint">base_url（endpoint）</label><input class="field" id="admin-endpoint" value="${escapeHtml(endpoint)}" placeholder="自定义供应商时建议填写，例如 http://127.0.0.1:11434/v1" /><p class="state-note" id="admin-endpoint-hint">${icon('layui-icon-tips')} 内置供应商可留空走默认地址；自定义供应商建议填写 base_url。</p></div>
      <div class="form-block"><label class="field-label" for="admin-api-key">api_key(自定义供应商用)</label><input class="field" id="admin-api-key" type="password" autocomplete="off" placeholder="${current && current.api_key ? '已配置（留空表示不修改）' : '自定义供应商填写密钥'}" /></div>
      <div class="form-grid">
        <div class="form-block"><label class="field-label" for="admin-price">price_per_call（单价）</label><input class="field" id="admin-price" type="number" min="0" step="0.0001" value="${escapeHtml(price)}" placeholder="留空或 0 表示免费" /></div>
        <div class="form-block"><label class="field-label" for="admin-max-duration">max_duration_sec(选填,秒)</label><input class="field" id="admin-max-duration" type="number" min="0" step="1" value="${escapeHtml(current && current.max_duration_sec != null ? current.max_duration_sec : '')}" placeholder="可选" /></div>
      </div>
      <div class="form-block"><label class="field-label" for="admin-description">描述</label><textarea class="textarea-field" id="admin-description" maxlength="500" placeholder="简要说明该模型用途">${escapeHtml(description)}</textarea></div>
      <div class="form-block"><label class="field-label" for="admin-capability-tags">能力标签（逗号分隔）</label><input class="field" id="admin-capability-tags" maxlength="300" value="${escapeHtml(capabilityTags)}" placeholder="例如 文本生成,深度思考" /></div>
      <div class="form-block">
        <span class="field-label">获取可用模型</span>
        <p class="state-note">${icon('layui-icon-tips')} 输入 base_url 与 api_key 后点击「获取可用模型」，从供应商 OpenAI 兼容接口拉取模型列表。</p>
        <div class="admin-fetch-row">
          <input class="field" id="admin-fetch-endpoint" value="${escapeHtml(endpoint)}" placeholder="base_url，例如 http://127.0.0.1:11434/v1" />
          <input class="field" id="admin-fetch-api-key" type="password" autocomplete="off" placeholder="api_key（可空）" />
          <button type="button" class="btn-secondary" id="admin-fetch-models" ${state.adminModels.fetchBusy ? 'disabled' : ''}>${state.adminModels.fetchBusy ? '拉取中…' : '获取可用模型'}</button>
        </div>
        ${fetchSelect}
      </div>
      <div class="invoice-form-actions">
        <button class="btn-quiet" id="admin-form-cancel" type="button">取消</button>
        <button class="btn-primary" id="admin-form-submit" type="submit" ${state.adminModels.formBusy ? 'disabled' : ''}>${state.adminModels.formBusy ? '提交中…' : (editing ? '保存修改' : '新增模型')}</button>
      </div>
    </form>`;
  }
  function adminModelsView() {
    const admin = state.adminModels;
    const items = admin.items || [];
    const pageCount = Math.max(1, Math.ceil((Number(admin.total) || items.length) / admin.pageSize));
    const page = Math.min(admin.page, pageCount);
    if (admin.page !== page) admin.page = page;
    const previousDisabled = page <= 1 ? 'disabled aria-disabled="true"' : '';
    const nextDisabled = page >= pageCount ? 'disabled aria-disabled="true"' : '';
    const action = `<button class="btn-primary" id="admin-model-open" type="button">${icon('layui-icon-add-1')} 新增模型</button>`;
    const form = admin.formOpen ? `<section class="panel panel-pad invoice-form-panel"><div class="billing-section-head"><div><h2 class="section-title">${icon('layui-icon-edit')}${admin.editingId != null ? '编辑模型' : '新增模型'}</h2><p class="text-muted">配置供应商、base_url 与密钥，保存后可在模型广场使用。</p></div></div>${adminModelsFormTemplate()}</section>` : '';
    const body = admin.loading
      ? `<tr><td class="table-empty" colspan="8">正在加载模型…</td></tr>`
      : admin.error
        ? `<tr><td class="table-empty" colspan="8">${escapeHtml(admin.error)} <button class="btn-quiet" id="admin-models-retry" type="button">重试</button></td></tr>`
        : adminModelsRows(items);
    return `${pageHead('模型管理', '自定义供应商、base_url、密钥并维护可用模型。', action)}
      <section class="panel panel-pad">
        <div class="notice">${icon('layui-icon-tips')}<div>此处管理后台模型配置，仅管理员可见。停用后模型将不再出现在模型广场。</div></div>
        <div class="table-wrap" style="margin-top:18px" role="region" aria-label="模型管理表格" tabindex="0"><table class="data-table"><thead><tr><th scope="col">展示名</th><th scope="col">model_code</th><th scope="col">供应商</th><th scope="col">类型</th><th scope="col">模型类型</th><th scope="col">单价</th><th scope="col">状态</th><th scope="col">操作</th></tr></thead><tbody>${body}</tbody></table></div>
        <div class="billing-pagination"><span>共 ${admin.total || items.length} 条</span><div><button type="button" class="btn-quiet" data-admin-page="-1" ${previousDisabled}>上一页</button><span>第 ${page} / ${pageCount} 页</span><button type="button" class="btn-quiet" data-admin-page="1" ${nextDisabled}>下一页</button></div></div>
      </section>${form}`;
  }
  function viewFor(route) {
    const views = { home: homeView, models: modelsView, text: textView, image: imageView, audio: audioView, video: videoView, tasks: tasksView, profile: profileView, billing: billingView, invoice: invoiceView, 'admin-models': adminModelsView };
    return (views[route] || homeView)();
  }
  function loadBillingData() {
    const billing = state.billing;
    if (billing.loading || billing.loaded) return;
    billing.loading = true;
    billing.error = '';
    if (window.PortalConfig.demoMode || !window.PortalApi || !window.PortalApi.token()) {
      billing.loaded = true;
      billing.loading = false;
      return;
    }
    Promise.all([
      window.PortalApi.wallet(),
      window.PortalApi.walletRecords({ page: 1, page_size: 100 })
    ]).then(([wallet, records]) => {
      billing.wallet = wallet || {};
      billing.records = Array.isArray(records && records.list) ? records.list : [];
      billing.page = 1;
    }).catch(error => {
      billing.error = error && error.message ? error.message : '账单加载失败，请稍后重试。';
    }).finally(() => {
      billing.loading = false;
      billing.loaded = true;
      if (state.route === 'billing') render();
    });
  }
  function loadInvoiceData() {
    const invoice = state.invoice;
    if (invoice.loading || invoice.loaded) return;
    invoice.loading = true;
    invoice.error = '';
    if (window.PortalConfig.demoMode || !window.PortalApi || !window.PortalApi.token()) {
      invoice.loaded = true;
      invoice.loading = false;
      return;
    }
    Promise.all([
      window.PortalApi.wallet(),
      window.PortalApi.invoices({ page: 1, page_size: 100 })
    ]).then(([wallet, invoices]) => {
      invoice.wallet = wallet || {};
      invoice.records = Array.isArray(invoices && invoices.list) ? invoices.list : [];
      invoice.page = 1;
    }).catch(error => {
      invoice.error = error && error.message ? error.message : '发票记录加载失败，请稍后重试。';
    }).finally(() => {
      invoice.loading = false;
      invoice.loaded = true;
      if (state.route === 'invoice') render();
    });
  }
  function loadAdminModelsData() {
    const admin = state.adminModels;
    if (admin.loading || admin.loaded) return;
    admin.loading = true;
    admin.error = '';
    if (window.PortalConfig.demoMode || !window.PortalApi || !window.PortalApi.token()) {
      admin.loaded = true;
      admin.loading = false;
      return;
    }
    window.PortalApi.request({ url: `/api/admin/models?page=${admin.page}&page_size=${admin.pageSize}` }).then(data => {
      admin.items = Array.isArray(data && data.items) ? data.items : [];
      admin.total = Number(data && data.total) || admin.items.length;
    }).catch(error => {
      admin.error = error && error.message ? error.message : '模型列表加载失败，请稍后重试。';
    }).finally(() => {
      admin.loading = false;
      admin.loaded = true;
      if (state.route === 'admin-models') render();
    });
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
    if (state.route === 'billing') loadBillingData();
    if (state.route === 'invoice') loadInvoiceData();
    if (state.route === 'admin-models' && user.role !== 'admin') {
      $('#app').html(shell(state.route, adminModelsAccessDeniedView()));
      bindEvents();
      return;
    }
    if (state.route === 'admin-models') loadAdminModelsData();
    if (state.route === 'text') loadChatHistory();
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
  function streamFailureMessage(error) {
    const detail = error && error.message ? String(error.message).trim() : '';
    if (!detail) return '文本任务请求失败，可修改内容后重试。';
    if (/积分不足|余额不足/.test(detail)) return `${detail}请到「个人中心 - 我的钱包」充值后再试。`;
    return `文本任务请求失败：${detail}`;
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
      toast(streamFailureMessage(error), 'error');
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
    $(document).off('click.chatHistory').on('click.chatHistory', '[data-chat-session]', function () {
      const sid = Number($(this).data('chat-session'));
      if (!sid || window.PortalConfig.demoMode) return;
      state.chatSessionId = sid;
      window.PortalApi.listSessionMessages(sid).then(data => {
        const rows = Array.isArray(data && data.items) ? data.items : [];
        state.chatMessages = rows.length ? rows.map(m => ({ role: m.role, content: m.content })) : [{ role: 'assistant', content: '该会话暂无消息。' }];
        render();
      }).catch(error => toast(error && error.message ? error.message : '历史消息加载失败。', 'error'));
    });
    $('#send-chat').on('click', sendChat);
    $('#chat-input').on('keydown', event => {
      if (event.key !== 'Enter') return;
      if (event.isComposing || event.keyCode === 229) return; // 输入法候选态:回车用于选词,不发送
      if (event.shiftKey) return; // Shift + Enter 换行
      event.preventDefault();
      sendChat();
    });
    $('[data-prompt]').on('click', function () { $('#chat-input').val($(this).data('prompt')).focus(); });
    $('#new-chat, #new-chat-side').on('click', () => { state.chatSessionId = null; state.chatMessages = [{ role: 'assistant', content: '已创建新会话。告诉我你想完成什么，我会从这里开始协助。' }]; persistDemoState(); render(); });
    $('[data-image-mode]').on('click', function () { state.imageMode = $(this).data('image-mode'); render(); });
    $('[data-ratio]').on('click', function () { state.imageRatio = $(this).data('ratio'); render(); });
    $('#image-model-select').on('change', function () { state.selectedModelIds.image = Number($(this).val()); render(); });
    $('#image-form').on('submit', function (event) { event.preventDefault(); const prompt = $('#image-prompt').val().trim(); if (!prompt) return toast('请先填写图像描述词。', 'error'); if (state.busy.image) return; state.busy.image = true; const title = prompt.slice(0, 22) + (prompt.length > 22 ? '…' : ''); const model = currentModel('image'); const submit = window.PortalConfig.demoMode ? Promise.resolve(createRecord('image', { title, mode: state.imageMode, meta: state.imageRatio, shouldFail: shouldSimulateFailure(prompt) })) : (model ? window.PortalApi.task('image', { model_id: model.id, prompt, params: { image_size: state.imageRatio.split(' ')[1].replace('×', 'x'), num: Number($('#image-count').val()) } }).then(result => remoteRecord('image', result, title, state.imageMode, state.imageRatio)) : Promise.reject({ message: '当前没有可用的图像模型。' })); submit.then(() => toast('图像任务已提交，正在生成。', 'success')).catch(error => toast(error && error.message ? error.message : '图像任务提交失败。', 'error')).finally(() => { state.busy.image = false; render(); }); });
    $('[data-audio-mode]').on('click', function () { state.audioMode = $(this).data('audio-mode'); render(); });
    $('[data-voice]').on('click', function () { state.selectedVoice = $(this).data('voice'); render(); });
    $('#audio-model-select').on('change', function () { state.selectedModelIds.audio = Number($(this).val()); render(); });
    $('#audio-text').on('input', function () { $('#audio-count').text(`${$(this).val().length} / 2000 字符`); });
    $('#audio-form').on('submit', function (event) { event.preventDefault(); const text = $('#audio-text').val().trim(); if (!text) return toast('请先输入需要合成的文本。', 'error'); if (state.busy.audio) return; state.busy.audio = true; const record = createRecord('audio', { title: text.slice(0, 20) + (text.length > 20 ? '…' : ''), mode: state.audioMode, meta: `${text.length} 字符`, shouldFail: shouldSimulateFailure(text) }); if (!record) { state.busy.audio = false; return; } state.busy.audio = false; toast('声音任务已提交，请在历史中查看进度。', 'success'); render(); });
    $('[data-video-duration]').on('click', function () { state.videoDuration = $(this).data('video-duration'); render(); });
    $('#video-model-select').on('change', function () { state.selectedModelIds.video = Number($(this).val()); render(); });
    $('#video-form').on('submit', function (event) { event.preventDefault(); const prompt = $('#video-prompt').val().trim(); if (!prompt) return toast('请先描述要生成的视频内容。', 'error'); if (state.busy.video) return; state.busy.video = true; const record = createRecord('video', { title: prompt.slice(0, 20) + (prompt.length > 20 ? '…' : ''), mode: '文生视频', meta: state.videoDuration, shouldFail: shouldSimulateFailure(prompt) }); if (!record) { state.busy.video = false; return; } state.busy.video = false; toast('视频任务已提交，渲染可能需要几分钟。', 'success'); render(); });
    $('[data-billing-tab]').on('click', function () {
      state.billing.tab = $(this).data('billing-tab');
      state.billing.page = 1;
      render();
    });
    $('[data-billing-period]').on('click', function () {
      state.billing.period = $(this).data('billing-period');
      state.billing.page = 1;
      render();
    });
    $('#billing-month').on('change', function () {
      state.billing.month = String($(this).val() || '').slice(0, 7) || new Date().toISOString().slice(0, 7);
      state.billing.period = 'custom';
      state.billing.page = 1;
      render();
    });
    $('#billing-type').on('change', function () {
      state.billing.type = String($(this).val() || 'all');
      state.billing.page = 1;
      render();
    });
    $('[data-billing-page]').on('click', function () {
      const pageCount = Math.max(1, Math.ceil(billingFilteredRecords().length / state.billing.pageSize));
      state.billing.page = Math.max(1, Math.min(pageCount, state.billing.page + Number($(this).data('billing-page'))));
      render();
    });
    $('#billing-retry').on('click', function () {
      state.billing.loaded = false;
      state.billing.error = '';
      render();
    });
    $('[data-invoice-open]').add('#invoice-open').on('click', function () {
      if (window.PortalConfig.demoMode) return toast('演示模式未连接发票接口。', 'error');
      state.invoice.formOpen = true;
      render();
      window.setTimeout(() => $('#invoice-amount').trigger('focus'), 0);
    });
    $('#invoice-cancel, #invoice-cancel-bottom').on('click', function () {
      state.invoice.formOpen = false;
      state.invoice.formBusy = false;
      render();
    });
    $('[data-invoice-period]').on('click', function () {
      state.invoice.period = $(this).data('invoice-period');
      state.invoice.page = 1;
      render();
    });
    $('#invoice-month').on('change', function () {
      state.invoice.month = String($(this).val() || '').slice(0, 7) || new Date().toISOString().slice(0, 7);
      state.invoice.period = 'custom';
      state.invoice.page = 1;
      render();
    });
    $('[data-invoice-page]').on('click', function () {
      const pageCount = Math.max(1, Math.ceil(invoiceFilteredRecords().length / state.invoice.pageSize));
      state.invoice.page = Math.max(1, Math.min(pageCount, state.invoice.page + Number($(this).data('invoice-page'))));
      render();
    });
    $('#invoice-retry').on('click', function () {
      state.invoice.loaded = false;
      state.invoice.error = '';
      render();
    });
    $('#invoice-form').on('submit', function (event) {
      event.preventDefault();
      if (window.PortalConfig.demoMode || state.invoice.formBusy) return;
      const amount = Number($('#invoice-amount').val());
      const type = String($('#invoice-type').val() || 'personal');
      const title = normalizeText($('#invoice-title').val(), '', 100);
      const taxNo = normalizeText($('#invoice-tax-no').val(), '', 50);
      if (!Number.isFinite(amount) || amount <= 0) return toast('请输入大于 0 的发票金额。', 'error');
      if (!title) return toast('请填写发票抬头。', 'error');
      if (type === 'enterprise' && !taxNo) return toast('企业发票需要填写税号。', 'error');
      const cents = Math.round(amount * 100);
      const available = invoiceAvailableMinor();
      if (cents <= 0 || cents > available) return toast(`申请金额不能超过可开票金额 ${money(available)}。`, 'error');
      state.invoice.formBusy = true;
      $('#invoice-submit').prop('disabled', true).text('正在提交…');
      window.PortalApi.createInvoice({ amount: cents, title, type, tax_no: taxNo || null }).then(() => {
        state.invoice.formBusy = false;
        state.invoice.formOpen = false;
        state.invoice.loaded = false;
        toast('开票申请已提交，请等待管理员审核。', 'success');
        render();
      }).catch(error => {
        state.invoice.formBusy = false;
        $('#invoice-submit').prop('disabled', false).text('提交申请');
        toast(error && error.message ? error.message : '开票申请提交失败，请稍后重试。', 'error');
      });
    });
    if (!window.PortalConfig.demoMode) {
      $('#image-submit, #audio-submit, #video-submit').prop('disabled', false).removeAttr('aria-disabled').each(function () {
        $(this).html(`${icon('layui-icon-release')} ${this.id === 'video-submit' ? '文生视频' : this.id === 'audio-submit' ? '生成音频' : '立即生成'}`);
      });
      $('#video-submit').next('.state-note').html(`${icon('layui-icon-tips')} 支持文生视频；上传首帧后自动使用图生视频模型。生成完成后可直接播放。`);
      const videoSettings = $('#video-resolution').closest('.form-grid');
      $('#video-resolution').html('<option value="1280x720">横屏 1280 × 720</option><option value="720x1280">竖屏 720 × 1280</option><option value="960x960">方形 960 × 960</option>');
      videoSettings.children('div').last().html('<label class="field-label" for="video-image">视频首帧（可选）</label><input class="field" id="video-image" type="file" accept="image/png,image/jpeg" /><p class="state-note" id="video-image-status">未上传时使用文生视频模型。</p>');
      $('#video-image').on('change', function () {
        const file = this.files && this.files[0];
        if (!file) return;
        if (!/^image\/(png|jpeg)$/.test(file.type)) return toast('首帧仅支持 PNG 或 JPG 图片。', 'error');
        $('#video-image-status').text('正在上传首帧…');
        window.PortalApi.upload(file).then(result => {
          state.videoImage = result.url;
          $('#video-image-status').text(`首帧已上传：${result.filename}`);
          toast('首帧上传成功，请选择图生视频模型后提交。', 'success');
        }).catch(error => {
          state.videoImage = null;
          $('#video-image-status').text('首帧上传失败。');
          toast(error && error.message ? error.message : '首帧上传失败。', 'error');
        });
      });
      $('#image-form').off('submit').on('submit', function (event) {
        event.preventDefault();
        const prompt = $('#image-prompt').val().trim(); const model = currentModel('image');
        if (!prompt) return toast('请先填写图像描述词。', 'error');
        if (!model) return toast('当前没有可用的图像模型。', 'error');
        state.busy.image = true;
        window.PortalApi.task('image', { model_id: model.id, prompt, params: {
          image_size: state.imageRatio.split(' ')[1].replace('×', 'x'),
          num: Number($('#image-count').val()),
          negative_prompt: $('#image-negative').val().trim() || undefined
        }}).then(result => {
          remoteRecord('image', result, prompt.slice(0, 22), state.imageMode, state.imageRatio);
          toast('图像任务已提交。', 'success');
        }).catch(error => toast(error && error.message ? error.message : '图像任务提交失败。', 'error'))
          .finally(() => { state.busy.image = false; render(); });
      });
      $('#audio-form').off('submit').on('submit', function (event) {
        event.preventDefault();
        const model = currentModel('audio');
        if (!model) return toast('当前没有可用的音频模型。', 'error');
        state.busy.audio = true;
        if (state.audioMode === '语音识别') {
          const file = $('#audio-file')[0] && $('#audio-file')[0].files && $('#audio-file')[0].files[0];
          if (!file) { state.busy.audio = false; return toast('请先选择要识别的音频文件。', 'error'); }
          window.PortalApi.upload(file).then(upload => {
            return window.PortalApi.request({ url: '/api/tasks/audio/asr', method: 'POST', data: { model_id: model.id, audio_url: upload.url } })
              .then(result => { remoteRecord('audio', result, String(file.name || '音频').slice(0, 20), state.audioMode, ''); toast('语音识别任务已提交。', 'success'); });
          }).catch(error => toast(error && error.message ? error.message : '语音识别任务提交失败。', 'error'))
            .finally(() => { state.busy.audio = false; render(); });
        } else {
          const text = $('#audio-text').val().trim();
          if (!text) { state.busy.audio = false; return toast('请先输入需要合成的文本。', 'error'); }
          window.PortalApi.request({ url: '/api/tasks/audio/clone', method: 'POST', data: { model_id: model.id, voice_name: state.selectedVoice, text } })
            .then(result => { remoteRecord('audio', result, text.slice(0, 20), state.audioMode, `${text.length} 字符`); toast('声音任务已提交。', 'success'); })
            .catch(error => toast(error && error.message ? error.message : '声音任务提交失败。', 'error'))
            .finally(() => { state.busy.audio = false; render(); });
        }
      });
      $('#video-form').off('submit').on('submit', function (event) {
        event.preventDefault();
        const text = $('#video-prompt').val().trim(); let model = currentModel('video');
        if (!text) return toast('请先描述要生成的视频内容。', 'error');
        if (state.videoImage && !(model && Array.isArray(model.tags) && model.tags.includes('图生视频'))) {
          model = models.find(item => item.modelType === 'video' && Array.isArray(item.tags) && item.tags.includes('图生视频')) || model;
        }
        if (!model) return toast('当前没有可用的视频模型。', 'error');
        state.busy.video = true;
        window.PortalApi.task('video', { model_id: model.id, text, params: { duration_sec: Number.parseInt(state.videoDuration, 10), resolution: $('#video-resolution').val(), negative_prompt: $('#video-negative').val().trim() || undefined, image_url: state.videoImage || undefined } })
          .then(result => { remoteRecord('video', result, text.slice(0, 20), state.videoImage ? '图生视频' : '文生视频', state.videoDuration); toast('视频任务已提交。', 'success'); })
          .catch(error => toast(error && error.message ? error.message : '视频任务提交失败。', 'error'))
          .finally(() => { state.busy.video = false; render(); });
      });
    }
    $('[data-retry]').on('click', function () { const id = String($(this).data('retry')); if (!window.PortalConfig.demoMode) { return window.PortalApi.taskRetry(id).then(result => { const record = [...state.imageHistory, ...state.audioHistory, ...state.videoHistory].find(item => String(item.id) === id); if (record) { record.status = result.status; record.error = ''; if (record.kind === 'image') state.activeImageTaskId = id; if (record.kind === 'audio') state.activeAudioTaskId = id; if (record.kind === 'video') state.activeVideoTaskId = id; pollTask(record); } toast('任务已重新提交。', 'success'); render(); }).catch(error => toast(error && error.message ? error.message : '任务重试失败。', 'error')); } let record; ['imageHistory', 'audioHistory', 'videoHistory'].some(key => { record = state[key].find(item => String(item.id) === id); return Boolean(record); }); if (!record) return toast('没有找到需要重试的任务。', 'error'); record.status = 'pending'; record.error = ''; record.shouldFail = false; record.attempts = (record.attempts || 1) + 1; if (record.kind === 'image') state.activeImageTaskId = id; if (record.kind === 'audio') state.activeAudioTaskId = id; if (record.kind === 'video') state.activeVideoTaskId = id; const mirror = state.tasks.find(item => String(item.id) === id); if (mirror) Object.assign(mirror, record); persistDemoState(); scheduleDemoTask(record, true); toast('任务已重新提交，本次演示将正常完成。', 'success'); render(); });
    $('[data-view-task]').on('click', function () {
      const id = String($(this).data('view-task'));
      const record = [...state.imageHistory, ...state.audioHistory, ...state.videoHistory].find(item => String(item.id) === id);
      if (!record) return toast('没有找到该任务，可能已被清理。', 'error');
      if (record.kind === 'image') state.activeImageTaskId = id;
      if (record.kind === 'audio') state.activeAudioTaskId = id;
      if (record.kind === 'video') state.activeVideoTaskId = id;
      if (state.route === record.kind) return render();
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
    // -------- 模型管理(admin-models) --------
    $('#admin-model-open').on('click', function () {
      state.adminModels.formOpen = true;
      state.adminModels.editingId = null;
      state.adminModels.fetchModels = [];
      render();
    });
    $('#admin-form-cancel').on('click', function () {
      state.adminModels.formOpen = false;
      state.adminModels.editingId = null;
      state.adminModels.fetchModels = [];
      render();
    });
    $(document).off('click.adminModelsEdit').on('click.adminModelsEdit', '[data-admin-edit]', function () {
      state.adminModels.formOpen = true;
      state.adminModels.editingId = Number($(this).data('admin-edit'));
      state.adminModels.fetchModels = [];
      render();
    });
    $(document).off('click.adminModelsDelete').on('click.adminModelsDelete', '[data-admin-delete]', function () {
      const id = Number($(this).data('admin-delete'));
      if (!window.confirm('确定删除该模型吗？此操作无法撤销。')) return;
      window.PortalApi.request({ url: `/api/admin/models/${id}`, method: 'DELETE' })
        .then(() => { state.adminModels.loaded = false; toast('模型已删除。', 'success'); render(); })
        .catch(error => toast(error && error.message ? error.message : '删除失败。', 'error'));
    });
    $(document).off('click.adminModelsToggle').on('click.adminModelsToggle', '[data-admin-toggle]', function () {
      const id = Number($(this).data('admin-toggle'));
      const item = state.adminModels.items.find(m => String(m.id) === String(id));
      const next = item && item.status === 'disabled' ? 'enabled' : 'disabled';
      window.PortalApi.request({ url: `/api/admin/models/${id}/status`, method: 'PUT', data: { status: next } })
        .then(() => { state.adminModels.loaded = false; render(); })
        .catch(error => toast(error && error.message ? error.message : '状态更新失败。', 'error'));
    });
    $(document).off('click.adminModelsPage').on('click.adminModelsPage', '[data-admin-page]', function () {
      const pageCount = Math.max(1, Math.ceil((Number(state.adminModels.total) || state.adminModels.items.length) / state.adminModels.pageSize));
      state.adminModels.page = Math.max(1, Math.min(pageCount, state.adminModels.page + Number($(this).data('admin-page'))));
      state.adminModels.loaded = false;
      render();
    });
    $('#admin-models-retry').on('click', function () { state.adminModels.loaded = false; state.adminModels.error = ''; render(); });
    $('#admin-fetch-models').on('click', function () {
      const baseUrl = ($('#admin-fetch-endpoint').val() || '').trim();
      const apiKey = ($('#admin-fetch-api-key').val() || '').trim();
      if (!baseUrl) return toast('请先填写 base_url。', 'error');
      state.adminModels.fetchBusy = true;
      $('#admin-fetch-models').prop('disabled', true).text('拉取中…');
      window.PortalApi.request({ url: '/api/admin/models/fetch', method: 'POST', data: { base_url: baseUrl, api_key: apiKey } })
        .then(data => {
          state.adminModels.fetchModels = Array.isArray(data && data.models) ? data.models : [];
          if (!state.adminModels.fetchModels.length) toast('未获取到模型，请检查 base_url 与 api_key。', 'error');
          else toast(`已获取 ${state.adminModels.fetchModels.length} 个模型。`, 'success');
          render();
        }).catch(error => toast(error && error.message ? error.message : '获取模型失败。', 'error'))
        .finally(() => { state.adminModels.fetchBusy = false; });
    });
    $('#admin-fetch-select').on('change', function () {
      const id = $(this).val();
      const name = $(this).find('option:selected').data('name') || id;
      if (id) { $('#admin-model-code').val(id); if (!$('#admin-name').val()) $('#admin-name').val(name); }
    });
    $('#admin-model-form').on('submit', function (event) {
      event.preventDefault();
      if (state.adminModels.formBusy) return;
      const name = normalizeText($('#admin-name').val(), '', 60);
      const modelCode = normalizeText($('#admin-model-code').val(), '', 120);
      const providerType = String($('#admin-provider-type').val() || 'online');
      const modelType = String($('#admin-model-type').val() || 'text');
      const vendor = normalizeText($('#admin-vendor').val(), '', 60);
      const endpoint = ($('#admin-endpoint').val() || '').trim() || null;
      const apiKey = ($('#admin-api-key').val() || '').trim() || null;
      const price = Number($('#admin-price').val() || 0);
      const maxDuration = Number($('#admin-max-duration').val()) || null;
      const description = ($('#admin-description').val() || '').trim() || null;
      const capabilityTags = ($('#admin-capability-tags').val() || '').split(',').map(s => s.trim()).filter(Boolean);
      if (!name || !modelCode || !vendor) return toast('请填写展示名、model_code 和供应商 vendor。', 'error');
      const body = { name, model_code: modelCode, provider_type: providerType, model_type: modelType, vendor, endpoint, api_key: apiKey, price_per_call: price, max_duration_sec: maxDuration, description, capability_tags: capabilityTags.length ? capabilityTags : null };
      state.adminModels.formBusy = true;
      $('#admin-form-submit').prop('disabled', true).text('提交中…');
      const req = state.adminModels.editingId != null
        ? window.PortalApi.request({ url: `/api/admin/models/${state.adminModels.editingId}`, method: 'PUT', data: body })
        : window.PortalApi.request({ url: '/api/admin/models', method: 'POST', data: body });
      req.then(() => {
        state.adminModels.formBusy = false;
        state.adminModels.formOpen = false;
        state.adminModels.editingId = null;
        state.adminModels.loaded = false;
        toast('模型已保存。', 'success');
        render();
      }).catch(error => {
        state.adminModels.formBusy = false;
        $('#admin-form-submit').prop('disabled', false).text(state.adminModels.editingId != null ? '保存修改' : '新增模型');
        toast(error && error.message ? error.message : '模型保存失败。', 'error');
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
  $(function () { loadCurrentUser().then(loadModels).then(loadTaskHistory).finally(render); });
}());
