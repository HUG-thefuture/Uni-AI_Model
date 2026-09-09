/* global $ */
(function () {
  'use strict';

  // 联调时由成员2、4提供真实地址；演示模式不会向任何第三方模型厂商发送请求。
  window.PortalConfig = Object.assign({ apiBase: 'http://127.0.0.1:8000', demoMode: false, loginUrl: 'auth.html' }, window.PortalConfig || {});
  const DEMO_STORAGE_KEY = 'ai_portal_demo_state_v1';
  const taskTimers = new Map();
  let taskMonitor = null;
  let chatHistoryLoaded = false;
  const routeTitles = {
    home: '首页', models: '模型广场', text: '文本交互舱', image: '图像生成室',
    audio: '声音创作坊', video: '视频合成站', tasks: '创作历史', profile: '个人中心',
    billing: '个人账单', invoice: '发票管理', usage: '用量统计', apikeys: 'API Key 管理',
    admin: '管理后台'
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
    // 对话随模型切换自动跟随：每个模型维护各自独立的会话（消息/历史/后端会话id）。
    // chatMessages / chatSessionId / chatHistory 仍是“当前模型会话”的工作副本，切换时通过快照还原。
    chatByModel: {},
    // 真实模式下服务端会话列表（历史会话侧栏的数据源，含 session_id，可点击回读消息）。
    chatSessions: [],
    imageMode: '文生图',
    imageRefUrl: null,        // 图生图:已上传的参考图 URL(/static/...)
    imageRatio: '1:1 1024×1024',
    // 输入草稿:轮询/模式切换引发重渲染时保留用户正在输入的内容
    imagePrompt: '',
    imageNegative: '',
    audioText: '',
    videoPrompt: '',
    videoNegative: '',
    cloneSampleUrl: null,     // 声音克隆:已上传的人声样例 URL
    cloneVoiceName: '',       // 声音克隆:自定义音色名称
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
    busy: { text: false, image: false, audio: false, video: false, profile: false, recharge: false, phoneBind: false, imageUpload: false, cloneSample: false },
    billing: { loaded: false, loading: false, error: '', wallet: null, records: [], page: 1, pageSize: 10, tab: 'usage', period: 'all', month: new Date().toISOString().slice(0, 7), type: 'all' },
    invoice: { loaded: false, loading: false, error: '', wallet: null, records: [], page: 1, pageSize: 10, period: 'all', month: new Date().toISOString().slice(0, 7), formOpen: false, formBusy: false },
    usage: { loaded: false, loading: false, error: '', stats: null, filter: { model_id: '', task_type: '', days: '' } },
    apiKeys: { loaded: false, loading: false, error: '', records: [], busyId: null, createOpen: false, createBusy: false, created: null },
    admin: {
      tab: 'overview', loading: false, error: '',
      overview: null,
      users: { records: [], total: 0, page: 1, pageSize: 10, keyword: '', role: '', status: '', loaded: false, busyId: null, formOpen: false, editing: null, busy: false },
      models: { records: [], total: 0, page: 1, pageSize: 10, keyword: '', loaded: false, busyId: null, formOpen: false, editing: null, busy: false },
      wallets: { records: [], total: 0, page: 1, pageSize: 10, keyword: '', loaded: false },
      orders: { records: [], total: 0, page: 1, pageSize: 10, loaded: false },
      consumptions: { records: [], total: 0, page: 1, pageSize: 10, loaded: false },
      invoices: { records: [], total: 0, page: 1, pageSize: 10, loaded: false, busyId: null }
    }
  };

  let user = { name: '用户', initial: 'U', balance: '—', school: '未加载学校', realName: '未认证', role: 'user' };
  const navItems = [
    ['home', '首页', 'layui-icon-home'], ['models', '模型广场', 'layui-icon-app'],
    ['text', '文本交互舱', 'layui-icon-dialogue'], ['image', '图像生成室', 'layui-icon-picture'],
    ['audio', '声音创作坊', 'layui-icon-voice'], ['video', '视频合成站', 'layui-icon-video'],
    ['tasks', '创作历史', 'layui-icon-list'], ['profile', '个人中心', 'layui-icon-user'],
    ['billing', '个人账单', 'layui-icon-rmb'], ['invoice', '发票管理', 'layui-icon-file'],
    ['usage', '用量统计', 'layui-icon-chart'], ['apikeys', 'API Key 管理', 'layui-icon-key']
  ];
  let models = [
    { name: 'qwen3.7-plus', modelType: 'text', type: '语言模型', group: '国产顶级模型', source: '云端模型', tag: '深度思考', discount: '6折', desc: '适合问答、写作、代码与复杂任务规划的高质量语言模型。', tone: 'linear-gradient(135deg,#386ee5,#7951d4)' },
    { name: 'qwen-plus', modelType: 'text', type: '语言模型', group: '阿里系列模型', source: '云端模型', tag: '文本生成', discount: '6折', desc: '面向日常文本创作和多语言理解的通用对话模型。', tone: 'linear-gradient(135deg,#1684af,#2eaf91)' },
    { name: 'qwen-image', modelType: 'image', type: '生图模型', group: '国产顶级模型', source: '云端模型', tag: '图像生成', discount: '8折', desc: '支持文生图与图生图，适合视觉概念、海报与插画创作。', tone: 'linear-gradient(135deg,#ff825d,#bd4caf)' },
    { name: 'cosyvoice-v3-plus', modelType: 'audio', type: 'TTS模型', group: '阿里系列模型', source: '云端模型', tag: '语音生成', discount: '9折', desc: '可将文字转换为自然流畅的多音色语音。', tone: 'linear-gradient(135deg,#7e57dc,#3d8ff0)' },
    { name: 'wanx2.1-vace-plus', modelType: 'video', type: '生视频模型', group: '首推旗舰模型', source: '云端模型', tag: '视频生成', discount: '9折', desc: '支持文本、图像和视频条件控制的视频生成与编辑。', tone: 'linear-gradient(135deg,#176d9a,#283d91)' },
    { name: 'campus-knowledge-rag', modelType: 'text', type: '本地模型', group: '私域知识模型', source: '私域模型', tag: '本地部署', discount: '校内', desc: '校内知识库检索增强模型，适合规章制度与课程资料问答。', tone: 'linear-gradient(135deg,#34875b,#1f5f6b)' }
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
    return models.find(item => String(item.id) === String(state.selectedModelIds[type])) || models.find(item => item.modelType === type);
  }

  function modelSelectionKey(model) {
    return model && model.id != null ? String(model.id) : String(model && model.name || '');
  }

  function ensureMediaModelSelections() {
    ['image', 'audio', 'video'].forEach(type => {
      const selected = models.find(item => item.modelType === type && modelSelectionKey(item) === String(state.selectedModelIds[type]));
      if (selected) return;
      const preferred = models.find(item => item.modelType === type && item.vendor === 'dashscope')
        || models.find(item => item.modelType === type);
      if (preferred) state.selectedModelIds[type] = modelSelectionKey(preferred);
    });
  }

  function mediaModelSelectHtml(type, label) {
    const list = models.filter(item => item.modelType === type);
    const options = list.map(item => `<option value="${escapeHtml(modelSelectionKey(item))}" ${modelSelectionKey(item) === String(state.selectedModelIds[type]) ? 'selected' : ''}>${escapeHtml(item.name)}</option>`).join('');
    return `<select class="select-field" data-model-select="${type}" aria-label="选择${label}" ${list.length ? '' : 'disabled'}>${options || `<option value="">暂无${label}模型</option>`}</select>`;
  }

  function activeModelName(type) {
    const model = currentModel(type);
    return model ? escapeHtml(model.name) : '未选择';
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
    if (window.PortalConfig.demoMode || !window.PortalApi || !window.PortalApi.token()) {
      ensureMediaModelSelections();
      return Promise.resolve();
    }
    return api.models().then(items => {
      const typeNames = { text: '语言模型', image: '生图模型', audio: 'TTS模型', video: '生视频模型' };
      // 售价单位 0.0001 元/千token;主流报价口径为「元/百万token」= 值/10
      const perM = value => `¥${(((Number(value) || 0) / 10).toFixed(2))}`;
      const perK = value => `¥${(((Number(value) || 0) / 10000).toFixed(4).replace(/0+$/, '').replace(/\.$/, ''))}`;
      // 按次计费的数量单位:图像按张、视频按条、其余按次(口径与后端结算一致)
      const perCallUnit = type => ({ image: '/张', video: '/条' }[type] || '/次');
      models = items.filter(item => item.available !== false).map((item, index) => ({
        id: item.id != null ? item.id : item.name, name: item.name, modelCode: item.model_code || '', modelType: item.model_type, vendor: item.vendor,
        type: typeNames[item.model_type] || '其他模型',
        group: item.provider_type === 'local' ? '私域知识模型' : '云端模型',
        source: item.provider_type === 'local' ? '私域模型' : '云端模型',
        tag: Array.isArray(item.capability_tags) ? item.capability_tags[0] || item.model_type : item.model_type,
        tags: Array.isArray(item.capability_tags) ? item.capability_tags : [],
        billingMode: item.billing_mode === 'per_token' ? 'per_token' : 'per_call',
        // 计费徽标 + 计费说明(与后端计费口径一一对应:售价=供应商成本×加价)
        discount: item.billing_mode === 'per_token'
          ? `按token计费 ${perM(item.token_input_price)}/百万tok起`
          : (item.price_per_call ? `¥${item.price_per_call}${perCallUnit(item.model_type)}` : '免费'),
        billingDetail: item.billing_mode === 'per_token'
          ? `按token计费：输入 ${perM(item.token_input_price)} / 输出 ${perM(item.token_output_price)} 每百万token（每千token ${perK(item.token_input_price)} / ${perK(item.token_output_price)}）`
          : (item.price_per_call
            ? `按量计费 · 单价 ¥${item.price_per_call}${perCallUnit(item.model_type)}，按实际产出${({ image: '张数', video: '条数' }[item.model_type] || '次数')}结算`
            : '限免体验 · 调用免费'),
        desc: item.description || '已接入平台模型服务。',
        tone: ['#386ee5', '#7951d4', '#2eaf91', '#bd4caf'][index % 4]
      }));
      ensureMediaModelSelections();
      const selected = currentModel('text');
      if (selected) activateChatFor(selected.name);
    }).catch(error => {
      toast(error && error.message ? `模型列表加载失败：${error.message}` : '模型列表加载失败，请稍后刷新。', 'error');
    });
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
        const editing = document.activeElement && document.activeElement.closest && document.activeElement.closest('#image-form, #audio-form, #video-form');
        if (!editing && ['image', 'audio', 'video', 'tasks', 'profile'].includes(state.route)) render();
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
      balance: Number.isFinite(Number(wallet.balance)) ? String(Number(wallet.balance)) : '—',
      phone: normalizeText(source.phone, '', 20),
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
      if (saved.selectedModelIds && typeof saved.selectedModelIds === 'object') {
        ['image', 'audio', 'video'].forEach(type => {
          const value = saved.selectedModelIds[type];
          if (typeof value === 'string' || typeof value === 'number') state.selectedModelIds[type] = String(value);
        });
      }
      // 逐模型会话：新格式直接载入；旧存档（无 chatByModel）时把单一历史挂到当前模型名下。
      if (saved.chatByModel && typeof saved.chatByModel === 'object') {
        const entries = Object.entries(saved.chatByModel);
        entries.forEach(([name, conv]) => {
          if (!name || !conv || typeof conv !== 'object') return;
          state.chatByModel[name] = {
            messages: Array.isArray(conv.messages) ? conv.messages.filter(item => item && typeof item === 'object').slice(-100) : activeChatWelcome(),
            history: Array.isArray(conv.history) ? conv.history.slice(0, 100) : [],
            sessionId: conv.sessionId || null
          };
        });
      } else if (state.chatMessages.length || state.chatHistory.length) {
        // 旧存档（无 chatByModel）迁移：把已载入工作副本的单一会话挂到当前模型名下，
        // 避免随后 syncActiveChatToCurrentModel 用默认欢迎语覆盖掉历史对话。
        const key = state.currentChatModel || 'default';
        state.chatByModel[key] = {
          messages: state.chatMessages.slice(-100),
          history: state.chatHistory.slice(0, 100),
          sessionId: state.chatSessionId || null
        };
      }
      syncActiveChatToCurrentModel();
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
      chatByModel: Object.keys(state.chatByModel).reduce((acc, name) => {
        const conv = state.chatByModel[name] || {};
        acc[name] = {
          messages: Array.isArray(conv.messages) ? conv.messages.slice(-100) : [],
          history: Array.isArray(conv.history) ? conv.history.slice(0, 100) : [],
          sessionId: conv.sessionId || null
        };
        return acc;
      }, {}),
      imageHistory: state.imageHistory.slice(0, 100),
      audioHistory: state.audioHistory.slice(0, 100),
      videoHistory: state.videoHistory.slice(0, 100),
      tasks: state.tasks.slice(0, 100),
      modelType: state.modelType,
      modelGroup: state.modelGroup,
      modelSource: state.modelSource,
      keyword: state.keyword,
      currentChatModel: state.currentChatModel,
      selectedModelIds: Object.assign({}, state.selectedModelIds),
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
    // 金额口径:后端统一返回「元」;小于 1 分的金额展示到 0.000001 元,避免便宜的调用显示 ¥0.00
    const abs = Math.abs(amount);
    let text;
    if (abs === 0) text = '0.00';
    else if (abs < 0.01) text = abs.toFixed(6).replace(/0+$/, '').replace(/\.$/, '');
    else text = abs.toFixed(2);
    return `${sign}${amount < 0 ? '-' : ''}¥${text}`;
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
  function chatSessionDate(value) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return '';
    const now = new Date();
    const sameDay = date.toDateString() === now.toDateString();
    if (sameDay) return '今天';
    const yesterday = new Date(now); yesterday.setDate(now.getDate() - 1);
    if (date.toDateString() === yesterday.toDateString()) return '昨天';
    return date.toLocaleDateString('zh-CN');
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
      const modelLabel = record.model_name || (isConsumption ? '模型调用' : '充值订单');
      const detail = isConsumption ? `${modelLabel} · ${record.order_no || ''}` : (record.order_no || '充值订单');
      // 消费行展示真实 token 用量(输入+输出);充值/退款行无 token,显示 —
      const inTok = Number(record.prompt_tokens);
      const outTok = Number(record.completion_tokens);
      const hasTokens = isConsumption && Number.isFinite(inTok) && Number.isFinite(outTok) && (inTok + outTok) > 0;
      const usage = hasTokens ? `${inTok} / ${outTok}` : '—';
      const unit = hasTokens ? 'tokens(入/出)' : '—';
      return `<tr><td>${escapeHtml(dateText(record.created_at))}</td><td>${escapeHtml(detail)}</td><td>${isConsumption ? '模型调用' : '余额充值'}</td><td>${escapeHtml(usage)}</td><td>${escapeHtml(unit)}</td><td class="${Number(record.amount) < 0 ? 'amount-negative' : 'amount-positive'}">${escapeHtml(money(record.amount, true))}</td><td>${walletStatusLabel(record.status)}</td></tr>`;
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
          <div class="wallet">${icon('layui-icon-rmb')}<span>余额 ${escapeHtml(money(user.balance))}</span></div>
          <div class="account-menu-wrap">
            <button class="user-menu" id="account-menu-button" type="button" aria-label="打开账户菜单" aria-haspopup="menu" aria-controls="account-menu-popup" aria-expanded="false"><span class="avatar">${escapeHtml(user.initial)}</span><span>${escapeHtml(user.name)}</span>${icon('layui-icon-down')}</button>
            <div class="account-menu" id="account-menu-popup" role="menu" aria-labelledby="account-menu-button" hidden>
              <div class="account-menu-summary" role="presentation"><span class="avatar account-menu-avatar">${escapeHtml(user.initial)}</span><span class="account-menu-copy"><strong>${escapeHtml(user.name)}</strong><small>${escapeHtml(user.school)} · ${user.role === 'admin' ? '管理员' : '学生用户'}</small></span></div>
                            <div class="account-menu-meta" role="presentation"><span>${icon('layui-icon-vercode')} ${escapeHtml(user.realName)}</span><span>余额 ${escapeHtml(money(user.balance))}</span></div>
              <div class="account-menu-divider" role="separator"></div>
              <button class="account-menu-item" type="button" role="menuitem" data-route="profile">${icon('layui-icon-user')}<span>个人中心</span></button>
              <button class="account-menu-item" type="button" role="menuitem" data-route="tasks">${icon('layui-icon-list')}<span>创作历史</span></button>
              <button class="account-menu-item" type="button" role="menuitem" data-route="usage">${icon('layui-icon-chart')}<span>用量统计</span></button>
              <button class="account-menu-item" type="button" role="menuitem" data-route="apikeys">${icon('layui-icon-key')}<span>API Key 管理</span></button>
              ${user.role === 'admin' ? `<button class="account-menu-item" type="button" role="menuitem" data-route="admin">${icon('layui-icon-set')}<span>管理后台</span></button>` : ''}
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
      <p class="model-desc text-muted" style="font-size:12px;margin-top:-4px">${escapeHtml(model.billingDetail || '')}</p>
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
    const messages = state.chatMessages.map(item => {
      const meta = item.meta ? `<div class="msg-meta text-muted" style="font-size:12px;margin-top:6px">${escapeHtml(item.meta)}</div>` : '';
      return `<div class="message ${item.role === 'user' ? 'user' : ''}"><span class="message-avatar">${item.role === 'user' ? escapeHtml(user.initial) : 'AI'}</span><div class="bubble">${item.loading ? '<span class="typing-dots"><i></i><i></i><i></i></span>' : escapeHtml(item.content)}${meta}</div></div>`;
    }).join('');
    return `${pageHead('文本交互舱', '选择模型，开始一次专注的对话与创作。')}
      <section class="panel chat-layout">
        <aside class="chat-models"><strong style="font-size:14px">可用模型</strong><div class="chat-list">${chatModels.map(model => `<button type="button" class="chat-model-option ${state.currentChatModel === model.name ? 'active' : ''}" data-chat-model="${escapeHtml(model.name)}" aria-pressed="${state.currentChatModel === model.name}">${escapeHtml(model.name)}<small>${escapeHtml(model.tag)}</small></button>`).join('')}</div></aside>
        <div class="chat-main"><div class="chat-toolbar"><div><strong>${escapeHtml(state.currentChatModel)}</strong><span> · 已准备就绪</span></div><button class="btn-secondary" id="new-chat" type="button">${icon('layui-icon-add-1')} 新建会话</button></div><div class="messages" id="message-list" role="log" aria-live="polite" aria-label="对话消息">${messages}</div><div class="chat-compose"><textarea id="chat-input" class="textarea-field" maxlength="2000" placeholder="输入你的问题或指令…（Enter 发送，Shift + Enter 换行）" aria-label="对话内容，按 Enter 发送，Shift 加 Enter 换行"></textarea><div class="compose-foot"><div class="chip-row"><button type="button" class="prompt-chip" data-prompt="请帮我优化下面这段文案：">文案优化</button><button type="button" class="prompt-chip" data-prompt="请把下面内容翻译成英文：">翻译</button><button type="button" class="prompt-chip" data-prompt="请用 Python 写一个函数：">代码编写</button></div><button class="btn-primary" id="send-chat" type="button" ${state.busy.text ? 'disabled' : ''}>${state.busy.text ? '生成中…' : '发送'} ${icon('layui-icon-release')}</button></div></div></div>
        <aside class="chat-history"><div style="display:flex;justify-content:space-between;align-items:center"><strong style="font-size:14px">历史会话</strong><button class="btn-quiet" id="new-chat-side" type="button" aria-label="新建会话" title="新建会话">${icon('layui-icon-add-1')}</button></div><div style="margin-top:14px">${window.PortalConfig.demoMode ? state.chatHistory.map(item => `<div class="history-row">${escapeHtml(item.title)}<small>${escapeHtml(item.date)}</small></div>`).join('') : (() => { const currentTextModel = currentModel('text'); const ownSessions = state.chatSessions.filter(item => currentTextModel && item.model_id != null && String(item.model_id) === String(currentTextModel.id)); return ownSessions.length ? ownSessions.map(item => `<div class="history-row" data-chat-session="${escapeHtml(item.session_id)}" role="button" tabindex="0" aria-label="加载会话：${escapeHtml(item.title)}">${escapeHtml(item.title)}<small>${escapeHtml(chatSessionDate(item.updated_at))}</small></div>`).join('') : `<div class="history-row"><small>当前模型暂无历史会话，发送第一条消息后自动保存。</small></div>`; })()}</div></aside>
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
    const activeImageModel = currentModel('image');
    const isI2I = state.imageMode === '图生图';
    const i2iForm = isI2I ? `<div class="form-block"><label class="field-label" for="image-ref">参考图（图生图基底） <span class="required">*</span></label><input class="field" id="image-ref" type="file" accept="image/png,image/jpeg,image/webp" /><p class="state-note" id="image-ref-status">${state.imageRefUrl ? `已上传：${escapeHtml(state.imageRefUrl)}` : '上传后将以该图为基底生成新图；请选择支持图生图的模型。'}</p></div>` : '';
    const submitDisabled = state.busy.image || state.busy.imageUpload;
    const submitLabel = state.busy.image ? '正在提交…' : (state.busy.imageUpload ? '参考图上传中…' : (isI2I ? '以图生图' : '立即生成'));
    const noteText = isI2I
      ? '图生图：先上传参考图，再输入描述词描述想要的改动；模型不支持时会明确报错且不扣费。'
      : '提交后进入后台任务队列，生成完成的图像会自动保存到平台并在此预览。';
    return `${pageHead('图像生成室', '选择模型并输入描述词，把灵感转成可用的视觉素材。')}
      <section class="studio-layout"><div class="panel preview-stage"><div class="panel-pad" style="padding-bottom:12px"><h2 class="section-title">${icon('layui-icon-picture')}图像预览</h2></div><div class="preview-art ${hasResult ? 'demo-image' : ''}">${hasResult && currentImage.resultUrls && currentImage.resultUrls.length ? currentImage.resultUrls.map(url => `<img src="${escapeHtml(resultUrl(url))}" alt="${escapeHtml(currentImage.title)}" style="max-width:100%;max-height:420px;object-fit:contain" />`).join('') : `<div class="preview-art-inner">${icon(hasResult ? 'layui-icon-picture' : 'layui-icon-upload-drag')}<strong>${hasResult ? '图像生成完成' : currentImage ? '正在生成图像' : '等待生成图像'}</strong><span>${hasResult ? '服务端图像结果已返回。' : currentImage ? '新任务正在处理，完成后会替换当前预览。' : '提交提示词后，生成结果会在这里展示。'}</span></div>`}</div><div class="preview-caption">${hasResult && currentImage.resultUrls && currentImage.resultUrls.length ? `已返回 ${currentImage.resultUrls.length} 张图像，可右键保存。` : hasResult ? '任务完成，但服务端未返回图像地址。' : currentImage ? escapeHtml(currentImage.title) : '尚未提交任务'}</div></div>
        <form class="panel panel-pad" id="image-form"><div class="inline-model"><span>${icon('layui-icon-light')} 图像模型 <small data-active-model-name="image">${activeImageModel ? escapeHtml(activeImageModel.name) : '未选择'}</small></span>${mediaModelSelectHtml('image', '图像')}</div><div class="tab-row" role="group" aria-label="图像生成模式"><button type="button" class="tab-btn ${state.imageMode === '文生图' ? 'active' : ''}" data-image-mode="文生图" aria-pressed="${state.imageMode === '文生图'}">文生图</button><button type="button" class="tab-btn ${isI2I ? 'active' : ''}" data-image-mode="图生图" aria-pressed="${isI2I}">图生图</button></div>${i2iForm}<div class="form-block"><label class="field-label" for="image-prompt">${isI2I ? '改动描述词' : '输入描述词'} <span class="required">*</span></label><textarea class="textarea-field" id="image-prompt" required placeholder="${isI2I ? '例如：把背景换成雪山日落，保持人物不变…' : '例如：一只可爱的橘猫在阳光下睡觉，写实风格，8K 分辨率…'}">${escapeHtml(state.imagePrompt || '')}</textarea></div><div class="form-block"><span class="field-label" id="image-ratio-label">图像尺寸</span><div class="ratio-row" role="group" aria-labelledby="image-ratio-label">${['1:1 1024×1024', '9:16 720×1280', '16:9 1280×720'].map(item => `<button type="button" class="duration-btn ${state.imageRatio === item ? 'active' : ''}" data-ratio="${item}" aria-pressed="${state.imageRatio === item}">${item}</button>`).join('')}</div></div><div class="advanced"><div class="form-grid"><div><label class="field-label" for="image-count">生成数量</label><select class="select-field" id="image-count"><option value="1">1 张</option><option value="2">2 张</option><option value="4">4 张</option></select></div><div><label class="field-label" for="image-negative">负面提示词</label><input id="image-negative" class="field" placeholder="模糊、低质量、变形…" value="${escapeHtml(state.imageNegative || '')}" /></div></div></div><button class="btn-primary wide-action" id="image-submit" type="submit" ${submitDisabled ? 'disabled' : ''}>${icon('layui-icon-release')} ${submitLabel}</button><p class="state-note">${icon('layui-icon-tips')} ${noteText}</p></form></section>
      <section class="panel panel-pad history-panel"><h2 class="section-title">${icon('layui-icon-list')}生成历史</h2><div class="table-wrap" role="region" aria-label="创作记录表格" tabindex="0"><table class="data-table"><thead><tr><th scope="col">提示词</th><th scope="col">类型</th><th scope="col">尺寸</th><th scope="col">创建时间</th><th scope="col">状态</th><th scope="col">操作</th></tr></thead><tbody>${historyRows(state.imageHistory, '生成')}</tbody></table></div></section>`;
  }

  function audioView() {
    const current = state.audioHistory.find(item => String(item.id) === String(state.activeAudioTaskId)) || state.audioHistory[0];
    const running = current && ['pending', 'processing'].includes(current.status);
    const complete = current && ['succeeded', 'success'].includes(current.status);
    const failed = current && current.status === 'failed';
    const voices = [['龙安洋', '阳光大男孩 · 中英双语'], ['龙安欢', '欢脱元气女 · 中英双语'], ['清雅老师', '知性女声 · 普通话'], ['星河少年', '沉稳男声 · 普通话']];
    const activeAudioModel = currentModel('audio');
    const audioModes = ['声音合成', '声音克隆', '语音识别'];
    const isAsr = state.audioMode === '语音识别';
    const isClone = state.audioMode === '声音克隆';
    const modeHint = isAsr ? '上传音频文件，服务端将转写为文字，识别结果在左侧展示。'
      : isClone ? '声音克隆分两步：① 上传一段 5-30 秒的清晰人声样例；② 输入要让该音色说出的文本。生成结果为该音色的语音。'
      : '输入文本并选择配音员，直接合成为语音。';
    const asrResult = complete && isAsr && current && current.resultText ? `<div class="asr-result"><strong>识别结果</strong><p>${escapeHtml(current.resultText)}</p></div>` : '';
    const ttsForm = `${isClone ? `<div class="form-block"><label class="field-label" for="clone-sample">① 人声样例音频 <span class="required">*</span></label><input class="field" id="clone-sample" type="file" accept="audio/*" /><p class="state-note" id="clone-sample-status">${state.cloneSampleUrl ? `已上传：${escapeHtml(state.cloneSampleUrl)}` : '请上传 5-30 秒清晰、无背景噪音的人声样例（MP3/WAV）。'}</p></div><div class="form-block"><label class="field-label" for="clone-voice-name">② 自定义音色名称 <span class="required">*</span></label><input class="field" id="clone-voice-name" maxlength="30" placeholder="例如：我的音色" value="${escapeHtml(state.cloneVoiceName || '')}" /></div><div class="form-block"><label class="field-label" for="audio-text">③ 合成文本 <span class="required">*</span></label><textarea class="textarea-field" id="audio-text" aria-describedby="audio-count" maxlength="2000" required placeholder="输入要让克隆音色说出的内容…">${escapeHtml(state.audioText || '')}</textarea><div class="state-note" style="margin-top:6px">${icon('layui-icon-note')} <span id="audio-count" aria-live="polite">0 / 2000 字符</span></div></div>`
      : `<div class="form-block"><label class="field-label" for="audio-text">输入文本 <span class="required">*</span></label><textarea class="textarea-field" id="audio-text" aria-describedby="audio-count" maxlength="5000" required placeholder="输入您想转换成声音的文本内容…">${escapeHtml(state.audioText || '')}</textarea><div class="state-note" style="margin-top:6px">${icon('layui-icon-note')} <span id="audio-count" aria-live="polite">0 / 5000 字符</span></div></div><div class="form-grid"><div><label class="field-label" for="audio-speed">语速</label><input class="field" id="audio-speed" type="number" step="0.1" min="0.5" max="2" value="1" /></div><div><label class="field-label" for="audio-format">音频格式</label><select class="select-field" id="audio-format"><option>MP3（默认）</option><option>WAV</option><option>PCM</option><option>OPUS</option></select></div></div><div class="form-block" style="margin-top:18px"><span class="field-label" id="voice-label">选择配音员</span><div class="audio-voice-grid" role="group" aria-labelledby="voice-label">${voices.map(([name, detail]) => `<button type="button" class="voice-card ${state.selectedVoice === name ? 'active' : ''}" data-voice="${name}" aria-pressed="${state.selectedVoice === name}"><strong>${name}</strong><span>${detail}</span></button>`).join('')}</div></div>`}`;
    return `${pageHead('声音创作坊', '将文字转成自然语音，并保留每一次创作的任务记录。')}
       <section class="studio-layout"><div class="panel preview-stage"><div class="panel-pad" style="padding-bottom:12px"><h2 class="section-title">${icon('layui-icon-voice')}音频预览</h2></div><div class="preview-art" style="min-height:250px;background:linear-gradient(140deg,#182545,#283c77)"><div class="preview-art-inner">${icon(failed ? 'layui-icon-error' : complete ? 'layui-icon-headset' : 'layui-icon-voice')}<strong>${failed ? '音频生成失败' : complete ? (isAsr ? '语音识别完成' : '音频已生成') : running ? '正在生成音频' : '未开始生成'}</strong><span>${failed ? escapeHtml(current.error || '任务失败，请检查后重试。') : complete ? (isAsr ? '服务端识别结果已返回。' : '服务端音频结果已返回，可直接播放或下载。') : running ? '任务已提交，正在等待模型服务处理。' : '提交文本后可查看任务状态。'}</span></div></div><div class="preview-caption">${complete ? (current.resultUrls && current.resultUrls[0] ? `<audio controls preload="metadata" src="${escapeHtml(resultUrl(current.resultUrls[0]))}"></audio>` : asrResult || '任务完成，但服务端未返回音频地址。') : failed ? escapeHtml(current.error || '可在下方历史记录中重新提交。') : running ? escapeHtml(current.title) : '声音任务通常以异步方式处理，请勿重复提交。'}</div></div>
        <form class="panel panel-pad" id="audio-form"><div class="inline-model"><span>${icon('layui-icon-light')} 语音模型 <small data-active-model-name="audio">${activeAudioModel ? escapeHtml(activeAudioModel.name) : '未选择'}</small></span>${mediaModelSelectHtml('audio', '语音')}</div><div class="tab-row" role="group" aria-label="声音创作模式">${audioModes.map(item => `<button type="button" class="tab-btn ${state.audioMode === item ? 'active' : ''}" data-audio-mode="${item}" aria-pressed="${state.audioMode === item}">${item}</button>`).join('')}</div>${isAsr ? `<div class="form-block"><label class="field-label" for="audio-file">上传音频 <span class="required">*</span></label><input class="field" id="audio-file" type="file" accept="audio/*" required /><p class="state-note">支持常见音频格式，文件将先上传后提交识别任务。</p></div>` : ttsForm}<button class="btn-primary wide-action" id="audio-submit" type="submit" ${state.busy.audio ? 'disabled' : ''}>${icon('layui-icon-release')} ${state.busy.audio ? '正在提交…' : (isAsr ? '开始识别' : isClone ? '克隆并合成音频' : '生成音频')}</button><p class="state-note">${icon('layui-icon-tips')} ${modeHint}</p></form></section>
      <section class="panel panel-pad history-panel"><h2 class="section-title">${icon('layui-icon-list')}创作历史</h2><div class="table-wrap" role="region" aria-label="创作记录表格" tabindex="0"><table class="data-table"><thead><tr><th scope="col">作品名称</th><th scope="col">模式</th><th scope="col">时长/字数</th><th scope="col">完成时间</th><th scope="col">状态</th><th scope="col">操作</th></tr></thead><tbody>${historyRows(state.audioHistory, '创作')}</tbody></table></div></section>`;
  }

  function videoView() {
    const current = state.videoHistory.find(item => String(item.id) === String(state.activeVideoTaskId)) || state.videoHistory[0];
    const running = current && ['pending', 'processing'].includes(current.status);
    const complete = current && ['succeeded', 'success'].includes(current.status);
    const failed = current && current.status === 'failed';
    const videoResults = complete && current && current.resultUrls ? current.resultUrls : [];
    const activeVideoModel = currentModel('video');
    return `${pageHead('视频合成站', '以文本、图片或音频条件组合成一段可控的短视频。')}
      <section class="studio-layout"><div class="panel preview-stage"><div class="panel-pad" style="padding-bottom:12px"><h2 class="section-title">${icon('layui-icon-video')}视频预览</h2></div><div class="video-preview">${videoResults.length ? videoResults.map((url, index) => `<figure style="margin:0 0 16px"><video controls preload="metadata" src="${escapeHtml(resultUrl(url))}" style="width:100%;max-height:420px"></video><figcaption class="preview-caption">结果 ${index + 1} · <a href="${escapeHtml(resultUrl(url))}" target="_blank" rel="noopener">在新窗口打开/下载</a></figcaption></figure>`).join('') : `<div class="preview-art-inner">${icon(failed ? 'layui-icon-error' : complete ? 'layui-icon-play' : 'layui-icon-video')}<strong>${failed ? '视频生成失败' : complete ? '视频生成完成' : running ? '正在渲染视频' : '视频预览区域'}</strong><span>${failed ? escapeHtml(current.error || '任务失败，请检查参数后重试。') : complete ? '服务端未返回可播放的视频地址。' : '生成完成后将在此显示结果。'}</span></div>`}</div><div class="preview-caption">${running ? '渲染过程可能需要 3–5 分钟，请耐心等待。' : complete ? `${escapeHtml(current.title)}${videoResults.length > 1 ? ` · 共 ${videoResults.length} 个结果` : ''}` : failed ? escapeHtml(current.error || '可在下方历史记录中重新提交。') : '无首帧时将采用文生视频模型。'}</div></div>
        <form class="panel panel-pad" id="video-form"><div class="inline-model"><span>${icon('layui-icon-light')} 视频模型 <small data-active-model-name="video">${activeVideoModel ? escapeHtml(activeVideoModel.name) : '未选择'}</small></span>${mediaModelSelectHtml('video', '视频')}</div><div class="form-block"><label class="field-label" for="video-prompt">视频描述提示词 <span class="required">*</span></label><textarea class="textarea-field" maxlength="500" id="video-prompt" required placeholder="描述您想要生成的视频内容…">${escapeHtml(state.videoPrompt || '')}</textarea></div><div class="form-block"><label class="field-label" for="video-negative">反向提示词（可选）</label><input class="field" id="video-negative" value="${escapeHtml(state.videoNegative || '模糊、失真、低质量、变形、扭曲、水印、文字')}" /></div><div class="form-block"><span class="field-label" id="video-duration-label">视频时长</span><div class="duration-row" role="group" aria-labelledby="video-duration-label">${['5秒', '10秒', '15秒'].map(item => `<button type="button" class="duration-btn ${state.videoDuration === item ? 'active' : ''}" data-video-duration="${item}" aria-pressed="${state.videoDuration === item}">${item}</button>`).join('')}</div></div><div class="form-grid"><div><label class="field-label" for="video-resolution">分辨率</label><select class="select-field" id="video-resolution"><option>720P（高清）</option><option>1080P（超清）</option></select></div><div><span class="field-label">音频设置</span><button class="upload-drop" type="button" disabled aria-disabled="true" title="上传字段确认后开放">${icon('layui-icon-upload')} 音频上传 · 待开放</button></div></div><button class="btn-primary wide-action" id="video-submit" type="submit" ${state.busy.video ? 'disabled' : ''}>${icon('layui-icon-release')} ${state.busy.video ? '正在提交…' : '开始生成视频'}</button><p class="state-note">${icon('layui-icon-tips')} ${window.PortalConfig.demoMode ? '提示词包含“#失败”可验证失败任务和重新提交。' : '提交后进入后台队列；上传首帧可走图生视频，未上传时使用文生视频模型。'}</p><div class="tip-box"><strong>${icon('layui-icon-tips')} 温馨提示</strong>有首帧时可改用图生视频；尾帧可选，用于控制视频结束画面。长任务提交后请在创作历史中查看状态。</div></form></section>
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
            <div class="metric"><strong>${escapeHtml(money(user.balance))}</strong><span>账户余额</span></div>
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
                <div class="recharge-input-wrap"><input class="field" id="recharge-amount" type="number" min="1" max="100000" step="1" inputmode="numeric" required placeholder="请输入金额（元）" /><span class="recharge-unit">元</span></div>
              </div>
              <div class="recharge-presets" role="group" aria-label="快捷充值金额">
                ${[10, 50, 100].map(amount => `<button type="button" class="btn-secondary recharge-preset" data-recharge-amount="${amount}">${amount} 元</button>`).join('')}
              </div>
              <p class="state-note">${icon('layui-icon-tips')} 提交后进入收银台完成支付，充值到账后余额自动更新。</p>
              <div class="recharge-actions"><button class="btn-quiet" id="recharge-cancel" type="button">取消</button><button class="btn-primary" id="recharge-submit" type="submit" ${state.busy.recharge ? 'disabled' : ''}>${state.busy.recharge ? '正在提交…' : '去收银台'}</button></div>
            </form>
          </div>
        </article>
        <section class="panel panel-pad"><h2 class="section-title">${icon('layui-icon-user')}基础资料</h2><form id="profile-form"><div class="form-grid"><div class="form-block"><label class="field-label" for="profile-name">昵称</label><input class="field" id="profile-name" autocomplete="nickname" maxlength="30" value="${escapeHtml(user.name)}" /></div><div class="form-block"><label class="field-label" for="profile-school">学校</label><input class="field" id="profile-school" autocomplete="organization" maxlength="50" value="${escapeHtml(user.school)}" /></div><div class="form-block"><label class="field-label" for="profile-verification">实名认证状态</label><input class="field" id="profile-verification" value="${escapeHtml(user.realName)}" disabled /></div><div class="form-block"><label class="field-label" for="profile-role">账号角色</label><input class="field" id="profile-role" value="${escapeHtml(roleLabel)}" disabled /></div></div><button class="btn-primary" id="profile-submit" type="submit" ${state.busy.profile ? 'disabled' : ''}>${state.busy.profile ? '正在保存…' : '保存资料'}</button></form>
            <div class="notice" style="margin-top:20px">${icon('layui-icon-tips')}<div>钱包余额、账单和发票记录均来自后端接口。金额口径：全部按人民币「元」显示，按 token 计费的调用按实际用量精确扣费。</div></div>
            <section style="margin-top:20px"><h2 class="section-title">${icon('layui-icon-cellphone')}手机号绑定</h2>
              <p class="text-muted" style="font-size:13px">绑定后可用「手机号 + 短信验证码」登录门户。${user.phone ? `当前绑定：<strong>${escapeHtml(user.phone)}</strong>（换绑需验证新手机号）` : '当前未绑定。'}</p>
              <form id="phone-bind-form" style="display:flex;gap:8px;flex-wrap:wrap;margin-top:10px">
                <input class="field" id="bind-phone" maxlength="11" inputmode="numeric" placeholder="11位手机号" style="width:160px" autocomplete="tel" />
                <input class="field" id="bind-code" maxlength="6" inputmode="numeric" placeholder="验证码" style="width:110px" />
                <button class="btn-secondary" type="button" id="bind-send-btn">获取验证码</button>
                <button class="btn-primary" type="submit" id="bind-submit" ${state.busy.phoneBind ? 'disabled' : ''}>${state.busy.phoneBind ? '绑定中…' : '绑定手机号'}</button>
              </form>
            </section>
          </section>
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
    const action = `<button class="btn-primary" type="button" data-route="profile">${icon('layui-icon-rmb')} 立即充值</button> <button class="btn-secondary" id="billing-export" type="button">${icon('layui-icon-download-circle')} 导出 CSV</button>`;
    return `${pageHead('个人账单', '查看余额和使用记录。', action)}
      <section class="billing-summary">
        <article class="panel billing-card"><div class="billing-card-head"><span>当前余额</span><span class="status-tag success">可用</span></div><strong class="billing-amount">${escapeHtml(money(wallet.balance))}</strong><span class="billing-unit">人民币</span></article>
        <article class="panel billing-card"><div class="billing-card-head"><span>累计消费</span><span class="text-muted">钱包统计</span></div><strong class="billing-amount">${escapeHtml(money(wallet.total_consumed))}</strong><span class="billing-unit">人民币</span></article>
      </section>
      <section class="panel panel-pad">
        <div class="billing-section-head"><div><h2 class="section-title">${icon('layui-icon-list')}账单明细</h2><p class="text-muted">充值与消费/退款流水，消费行含模型与 token 用量。</p></div></div>
        <div class="billing-toolbar">
          <div class="tab-row" role="tablist" aria-label="账单记录类型"><button type="button" class="tab-btn ${state.billing.tab === 'usage' ? 'active' : ''}" data-billing-tab="usage" aria-selected="${state.billing.tab === 'usage'}">使用记录</button><button type="button" class="tab-btn ${state.billing.tab === 'balance' ? 'active' : ''}" data-billing-tab="balance" aria-selected="${state.billing.tab === 'balance'}">余额变更记录</button></div>
          <div class="filters" role="group" aria-label="账单时间范围">${[['all', '全部'], ['year', '年'], ['month', '月'], ['day', '日'], ['custom', '自定义']].map(([value, label]) => `<button type="button" class="filter-btn ${state.billing.period === value ? 'active' : ''}" data-billing-period="${value}" aria-pressed="${state.billing.period === value}">${label}</button>`).join('')}</div>
          <label class="billing-month"><span class="sr-only">账单月份</span><input class="field" id="billing-month" type="month" value="${month}" aria-label="账单月份" /></label>
          <select class="select-field billing-type" id="billing-type" aria-label="账单分类"><option value="all" ${state.billing.type === 'all' ? 'selected' : ''}>所有分类</option><option value="consumption" ${state.billing.type === 'consumption' ? 'selected' : ''}>模型调用</option><option value="recharge" ${state.billing.type === 'recharge' ? 'selected' : ''}>余额充值</option></select>
        </div>
        <div class="notice billing-notice">${icon('layui-icon-tips')}<div>账单包含充值、消费与退款流水：消费行展示对应模型的实际 token 用量（输入 / 输出）与扣费金额；退款为失败调用退回的金额，不计入消费。</div></div>
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
    const maxAmount = Math.max(available, 1);
    const form = state.invoice.formOpen ? `<section class="panel panel-pad invoice-form-panel"><div class="billing-section-head"><div><h2 class="section-title">${icon('layui-icon-edit')}提交开票申请</h2><p class="text-muted">申请金额按人民币元填写。</p></div><button class="btn-quiet" id="invoice-cancel" type="button">取消</button></div><form id="invoice-form"><div class="form-grid"><div class="form-block"><label class="field-label" for="invoice-amount">发票金额（元）<span class="required">*</span></label><input class="field" id="invoice-amount" type="number" min="1" max="${maxAmount}" step="1" inputmode="numeric" required placeholder="整数金额" /></div><div class="form-block"><label class="field-label" for="invoice-type">发票类型<span class="required">*</span></label><select class="select-field" id="invoice-type"><option value="personal">个人</option><option value="enterprise">企业</option></select></div></div><div class="form-block"><label class="field-label" for="invoice-title">发票抬头<span class="required">*</span></label><input class="field" id="invoice-title" maxlength="100" required placeholder="请输入发票抬头" /></div><div class="form-block"><label class="field-label" for="invoice-tax-no">企业税号</label><input class="field" id="invoice-tax-no" maxlength="50" placeholder="企业发票填写，个人发票可留空" /></div><p class="state-note">${icon('layui-icon-tips')} 当前可开票金额：${escapeHtml(money(available))}；申请后需等待管理员审核。</p><div class="invoice-form-actions"><button class="btn-quiet" id="invoice-cancel-bottom" type="button">取消</button><button class="btn-primary" id="invoice-submit" type="submit" ${state.invoice.formBusy ? 'disabled' : ''}>${state.invoice.formBusy ? '正在提交…' : '提交申请'}</button></div></form></section>` : '';
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

  // ===== 个人中心 · 用量统计 =====
  function loadUsageData(force) {
    if (window.PortalConfig.demoMode || !window.PortalApi || !window.PortalApi.usageStats) return;
    if (!force && (state.usage.loaded || state.usage.loading)) return;
    state.usage.loading = true;
    state.usage.error = '';
    window.PortalApi.usageStats(state.usage.filter)
      .then(data => { state.usage.stats = data && typeof data === 'object' ? data : null; state.usage.loaded = true; })
      .catch(error => { state.usage.error = error && error.message ? error.message : '用量统计加载失败。'; state.usage.loaded = true; })
      .finally(() => { state.usage.loading = false; render(); });
  }
  function usageView() {
    const demoMode = Boolean(window.PortalConfig.demoMode);
    const s = state.usage.stats || {};
    const filter = state.usage.filter;
    const call = Number(s.total_call) || 0;
    const tokens = Number(s.total_tokens) || 0;
    const cost = Number(s.total_cost) || 0;
    const filterDisabled = state.usage.loading ? 'disabled' : '';
    const modelOptions = (Array.isArray(models) ? models : [])
      .map(m => `<option value="${escapeHtml(String(m.id))}" ${String(filter.model_id) === String(m.id) ? 'selected' : ''}>${escapeHtml(m.name)}</option>`).join('');
    const typeOptions = [
      ['text', '文本对话'], ['image', '图像生成'], ['audio_clone', '声音合成'], ['asr', '语音识别'], ['video', '视频生成'],
    ].map(([value, label]) => `<option value="${value}" ${filter.task_type === value ? 'selected' : ''}>${label}</option>`).join('');
    const dayOptions = [['', '全部时间'], ['1', '今天'], ['7', '近 7 天'], ['30', '近 30 天'], ['90', '近 90 天']]
      .map(([value, label]) => `<option value="${value}" ${String(filter.days) === value ? 'selected' : ''}>${label}</option>`).join('');
    const filterBar = `<section class="panel panel-pad" style="margin-bottom:16px"><div class="usage-filter-grid">
        <div class="form-block"><label class="field-label" for="usage-filter-model">模型</label>
          <select class="select-field" id="usage-filter-model" ${filterDisabled}><option value="">全部模型</option>${modelOptions}</select></div>
        <div class="form-block"><label class="field-label" for="usage-filter-type">任务类型</label>
          <select class="select-field" id="usage-filter-type" ${filterDisabled}><option value="">全部类型</option>${typeOptions}</select></div>
        <div class="form-block"><label class="field-label" for="usage-filter-days">时间范围</label>
          <select class="select-field" id="usage-filter-days" ${filterDisabled}>${dayOptions}</select></div>
        <div class="form-block"><label class="field-label">&nbsp;</label><button class="btn-quiet" id="usage-filter-reset" type="button" ${filterDisabled}>重置筛选</button></div>
      </div></section>`;
    const filtered = filter.model_id || filter.task_type || filter.days;
    const filterNote = filtered ? `<p class="text-muted" style="margin-top:8px">${icon('layui-icon-tips')} 当前展示筛选后的用量；「累计消费」等卡片同步按筛选范围统计。</p>` : '';
    const empty = state.usage.error
      ? `<div class="notice usage-load-error">${icon('layui-icon-tips')}<div>用量统计加载失败：${escapeHtml(state.usage.error)}<br><small>请确认后端已注册并返回统一格式，稍后刷新重试。</small></div></div>`
      : (call === 0 && tokens === 0 && cost === 0 ? (demoMode ? `<div class="notice" style="margin-bottom:16px">${icon('layui-icon-tips')}<div>当前处于演示模式，未连接用量统计接口；关闭演示模式后将展示账户的真实累计用量。</div></div>` : `<div class="empty-state usage-empty">${icon('layui-icon-chart')}<div>${filtered ? '当前筛选条件下暂无用量记录' : '暂无用量记录'}<br><small>${filtered ? '调整筛选条件或清除筛选后重试。' : '完成一次模型调用后，这里会汇总你的累计用量。'}</small></div></div>`) : '');
    const items = Array.isArray(s.items) ? s.items : [];
    const detailRows = items.map(item => {
      const typeLabel = { text: '文本对话', image: '图像生成', audio_clone: '声音合成', asr: '语音识别', video: '视频生成' }[item.task_type] || item.task_type || '—';
      return `<tr><td>${escapeHtml(dateText(item.created_at))}</td><td>${escapeHtml(item.model_name || '—')}</td><td>${escapeHtml(typeLabel)}</td><td>${Number(item.prompt_tokens) || 0}</td><td>${Number(item.completion_tokens) || 0}</td><td><strong>${Number(item.total_tokens) || 0}</strong></td><td>${escapeHtml(money(item.cost))}</td></tr>`;
    }).join('');
    const detailTable = items.length
      ? `<section class="panel panel-pad" style="margin-top:16px"><div class="billing-section-head"><div><h2 class="section-title">${icon('layui-icon-note')}Token 用量明细</h2><p class="text-muted">筛选范围内最近 ${items.length} 次成功调用的逐条 token 用量与扣费；更早的记录可在「个人账单」查看。</p></div></div>
        <div class="table-wrap" role="region" aria-label="Token 用量明细表格" tabindex="0"><table class="data-table"><thead><tr><th scope="col">时间</th><th scope="col">模型</th><th scope="col">类型</th><th scope="col">输入 token</th><th scope="col">输出 token</th><th scope="col">合计</th><th scope="col">扣费</th></tr></thead><tbody>${detailRows}</tbody></table></div></section>`
      : '';
    const breakdown = Array.isArray(s.model_breakdown) ? s.model_breakdown : [];
    const breakdownRows = breakdown.map(row => `<tr><td>${escapeHtml(row.model_name || '—')}</td><td>${Number(row.calls) || 0}</td><td>${Number(row.tokens) || 0}</td><td>${escapeHtml(money(row.cost))}</td></tr>`).join('');
    const breakdownTable = breakdown.length
      ? `<section class="panel panel-pad" style="margin-top:16px"><div class="billing-section-head"><div><h2 class="section-title">${icon('layui-icon-chart')}按模型汇总</h2><p class="text-muted">筛选范围内各模型的调用次数、token 总量与消费（按消费从高到低排序）。</p></div></div>
        <div class="table-wrap" role="region" aria-label="按模型汇总表格" tabindex="0"><table class="data-table"><thead><tr><th scope="col">模型</th><th scope="col">调用次数</th><th scope="col">Token 总量</th><th scope="col">消费</th></tr></thead><tbody>${breakdownRows}</tbody></table></div></section>`
      : '';
    return `${pageHead('用量统计', '汇总你账户内全部模型调用的累计消耗。')}
      ${filterBar}
      <section class="usage-grid">
        <article class="panel usage-card"><span class="usage-card-label">累计调用</span><strong class="usage-card-value">${escapeHtml(String(call))}</strong><span class="usage-card-unit">次</span><p class="usage-card-note">${icon('layui-icon-tips')} 成功完成的模型任务次数</p></article>
        <article class="panel usage-card"><span class="usage-card-label">累计 Token</span><strong class="usage-card-value">${escapeHtml(String(tokens))}</strong><span class="usage-card-unit">tokens</span><p class="usage-card-note">${icon('layui-icon-tips')} 输入与输出 token 合计</p></article>
        <article class="panel usage-card"><span class="usage-card-label">累计消费</span><strong class="usage-card-value">${escapeHtml(money(cost))}</strong><span class="usage-card-unit">元</span><p class="usage-card-note">${icon('layui-icon-tips')} 按成功消费累计</p></article>
      </section>
      ${filterNote}
      ${empty}
      ${breakdownTable}
      ${detailTable}
      <section class="panel panel-pad" style="margin-top:16px"><h2 class="section-title">${icon('layui-icon-tips')}说明</h2><p class="text-muted">用量口径：仅统计状态为“成功”的模型任务。累计消费按实际结算金额累计（按 token 计费模型按真实 usage 结算，单位为元）；累计 Token 为输入与输出 token 合计，来自每次调用服务端采集的真实用量；图像/视频/声音任务的输入 token 按提示词估算，产出的媒体文件不计 token。<br>2026-09-07 上线 token 统计之前的文本任务，按全站估算口径（2 字符 ≈ 1 token）从对话内容回填，仅供参考；此后新任务均为服务端采集的真实用量。</p></section>`;
  }

  // ===== 个人中心 · API Key 管理 =====
  function apiKeyStatusLabel(status) { return status === 'disabled' ? ['已停用', 'pending'] : ['已启用', 'success']; }
  function loadApiKeysData() {
    if (window.PortalConfig.demoMode || !window.PortalApi || !window.PortalApi.apiKeys) return;
    if (state.apiKeys.loaded || state.apiKeys.loading) return;
    state.apiKeys.loading = true;
    state.apiKeys.error = '';
    window.PortalApi.apiKeys()
      .then(data => {
        state.apiKeys.records = Array.isArray(data) ? data : [];
        state.apiKeys.loaded = true;
      })
      .catch(error => { state.apiKeys.error = error && error.message ? error.message : 'API Key 列表加载失败。'; state.apiKeys.loaded = true; })
      .finally(() => { state.apiKeys.loading = false; render(); });
  }
  // ===== 开放平台接入信息(便于复制) =====
  function apiBaseUrl() {
    return `${String(window.PortalConfig.apiBase || '').replace(/\/$/, '')}/api/v1`;
  }
  function textModelOptions() {
    // 已加载的可用文本模型(vendor + model_code),供接入信息展示与复制
    return models.filter(m => m.modelType === 'text' && m.modelCode);
  }
  function escapeExample(text) {
    return escapeHtml(text).replace(/"/g, '&quot;');
  }
  function apiKeyUsagePanel(key) {
    const baseUrl = apiBaseUrl();
    const endpoint = `${baseUrl}/chat/completions`;
    const options = textModelOptions();
    const demo = options[0] ? options[0].modelCode : 'qwen-plus';
    const curl = [
      `curl ${endpoint} \\`,
      `  -H "Authorization: Bearer ${key || 'sk-你的密钥'}" \\`,
      `  -H "Content-Type: application/json" \\`,
      `  -d '{"model": "${demo}", "messages": [{"role": "user", "content": "你好"}], "stream": false}'`
    ].join('\n');
    const python = [
      `from openai import OpenAI`,
      ``,
      `client = OpenAI(api_key="${key || 'sk-你的密钥'}", base_url="${baseUrl}")`,
      `resp = client.chat.completions.create(`,
      `    model="${demo}",`,
      `    messages=[{"role": "user", "content": "你好"}],`,
      `)`,
      `print(resp.choices[0].message.content)`
    ].join('\n');
    const chips = options.length
      ? options.map(m => `<span style="display:inline-flex;align-items:center;gap:6px;background:#f6f8fd;border:1px solid #e3e9f5;border-radius:999px;padding:3px 10px;font-size:12px;margin:0 8px 8px 0"><code style="font-size:12px" title="${escapeHtml(m.modelCode)}">${escapeHtml(m.vendor)} · ${escapeHtml(m.modelCode)}</code><button type="button" class="btn-quiet" data-copy="${escapeExample(m.modelCode)}" style="padding:0 4px;font-size:11px" title="复制厂商调用名">${icon('layui-icon-transfer')}</button></span>`).join('')
      : '<span class="text-muted" style="font-size:13px">模型列表加载中，稍后自动刷新展示。</span>';
    return `<section class="panel panel-pad" style="margin-top:20px">
      <div class="billing-section-head"><div><h2 class="section-title">${icon('layui-icon-template-1')}接入信息</h2><p class="text-muted">OpenAI 兼容接口，以下信息均可一键复制，粘贴到你的应用即可调用。</p></div></div>
      <div class="usage-info-rows">
        <div class="usage-info-row" style="display:flex;align-items:center;gap:10px;margin-bottom:10px;flex-wrap:wrap"><span class="text-muted" style="width:110px;font-size:13px">API Base URL</span><code class="api-key-code" style="flex:1;min-width:220px">${escapeHtml(baseUrl)}</code><button class="btn-secondary" type="button" data-copy="${escapeExample(baseUrl)}">${icon('layui-icon-transfer')} 复制</button></div>
        <div class="usage-info-row" style="display:flex;align-items:center;gap:10px;margin-bottom:10px;flex-wrap:wrap"><span class="text-muted" style="width:110px;font-size:13px">对话接口</span><code class="api-key-code" style="flex:1;min-width:220px">${escapeHtml(endpoint)}</code><button class="btn-secondary" type="button" data-copy="${escapeExample(endpoint)}">${icon('layui-icon-transfer')} 复制</button></div>
        <div style="margin:6px 0 14px"><span class="text-muted" style="display:block;width:110px;font-size:13px;margin-bottom:6px">供应商与模型</span>${chips}</div>
        <div style="margin-bottom:14px"><div style="display:flex;align-items:center;gap:10px;margin-bottom:6px"><span class="text-muted" style="font-size:13px">curl 示例</span><button class="btn-quiet" type="button" data-copy="${escapeExample(curl)}">${icon('layui-icon-transfer')} 复制示例</button></div><pre class="api-key-code" style="white-space:pre-wrap;padding:12px;border-radius:10px;overflow:auto">${escapeHtml(curl)}</pre></div>
        <div><div style="display:flex;align-items:center;gap:10px;margin-bottom:6px"><span class="text-muted" style="font-size:13px">Python(OpenAI SDK)示例</span><button class="btn-quiet" type="button" data-copy="${escapeExample(python)}">${icon('layui-icon-transfer')} 复制示例</button></div><pre class="api-key-code" style="white-space:pre-wrap;padding:12px;border-radius:10px;overflow:auto">${escapeHtml(python)}</pre></div>
      </div>
    </section>`;
  }
  function apiKeyCreatedPanel() {
    const created = state.apiKeys.created;
    if (!created || !created.key) return '';
    return `<section class="panel panel-pad api-key-reveal">
      <div class="billing-section-head"><div><h2 class="section-title">${icon('layui-icon-key')}新的 API Key 已生成</h2><p class="text-muted">完整密钥仅展示这一次，请立即复制并妥善保存，关闭后无法再次查看。</p></div></div>
      <div class="api-key-codebox">
        <code class="api-key-code" id="api-key-reveal">${escapeHtml(created.name || '未命名')} · ${escapeHtml(created.key)}</code>
        <button class="btn-secondary" id="api-key-copy" type="button">${icon('layui-icon-transfer')} 复制密钥</button>
      </div>
      <p class="state-note">${icon('layui-icon-tips')} 请勿将密钥发送给他人或提交到公开仓库，泄露后可在下方列表中停用。</p>
    </section>
    ${apiKeyUsagePanel(created.key)}`;
  }
  function apiKeyRows() {
    if (state.apiKeys.error) return `<tr><td colspan="6"><div class="empty-state">${icon('layui-icon-tips')}<div>加载失败：${escapeHtml(state.apiKeys.error)}</div></div></td></tr>`;
    if (!state.apiKeys.records.length) return `<tr><td colspan="6"><div class="empty-state">${icon('layui-icon-key')}<div>暂无 API Key<br><small>点击右上角“创建 Key”生成一个用于开放接口调用的密钥。</small></div></div></td></tr>`;
    return state.apiKeys.records.map(key => {
      const [label, style] = apiKeyStatusLabel(key.status);
      const busy = String(state.apiKeys.busyId) === String(key.id);
      const masked = key.key_prefix ? `${escapeHtml(key.key_prefix)}${'•'.repeat(24)}` : '—';
      const toggle = key.status === 'disabled'
        ? `<button class="btn-secondary" type="button" data-key-toggle="${escapeHtml(key.id)}" data-key-next="enabled" ${busy ? 'disabled' : ''}>${busy ? '处理中…' : '启用'}</button>`
        : `<button class="btn-quiet danger" type="button" data-key-toggle="${escapeHtml(key.id)}" data-key-next="disabled" ${busy ? 'disabled' : ''}>${busy ? '处理中…' : '停用'}</button>`;
      const del = `<button class="btn-quiet danger" type="button" data-key-delete="${escapeHtml(key.id)}" data-key-name="${escapeHtml(key.name || '未命名')}" ${busy ? 'disabled' : ''}>${busy ? '处理中…' : '删除'}</button>`;
      return `<tr><td><strong>${escapeHtml(key.name || '未命名')}</strong></td><td><code class="api-key-mask">${masked}</code></td><td><span class="status-tag ${style}">${label}</span></td><td>${escapeHtml(String(key.use_count || 0))}</td><td>${escapeHtml(dateText(key.created_at))}</td><td>${toggle} ${del}</td></tr>`;
    }).join('');
  }
  function apiKeysView() {
    const demoMode = Boolean(window.PortalConfig.demoMode);
    const createDisabled = demoMode ? 'disabled aria-disabled="true" title="演示模式未连接 API Key 接口"' : '';
    const createHint = demoMode ? `<div class="notice" style="margin-bottom:16px">${icon('layui-icon-tips')}<div>当前处于演示模式，未连接 API Key 接口，因此仅展示页面结构与既有列表；关闭演示模式后可创建与管理密钥。</div></div>` : '';
    const formOpen = state.apiKeys.createOpen && !demoMode;
    const createForm = formOpen ? `<section class="panel panel-pad api-key-create-panel"><div class="billing-section-head"><div><h2 class="section-title">${icon('layui-icon-add-1')}创建 API Key</h2><p class="text-muted">为你的密钥取一个便于识别的名称，创建后仅展示一次完整密钥。</p></div><button class="btn-quiet" id="api-key-create-cancel" type="button">取消</button></div><form id="api-key-create-form"><div class="form-block"><label class="field-label" for="api-key-name">密钥名称<span class="required">*</span></label><input class="field" id="api-key-name" maxlength="100" required autocomplete="off" placeholder="例如：本地联调、测试环境" /></div><div class="form-actions-row"><button class="btn-quiet" id="api-key-create-cancel-bottom" type="button">取消</button><button class="btn-primary" id="api-key-create-submit" type="submit" ${state.apiKeys.createBusy ? 'disabled' : ''}>${state.apiKeys.createBusy ? '正在生成…' : '生成 Key'}</button></div></form></section>` : '';
    const action = `<button class="btn-primary" id="api-key-create-open" type="button" ${createDisabled}>${icon('layui-icon-add-1')} 创建 Key</button>`;
    return `${pageHead('API Key 管理', '管理用于开放接口访问的密钥。', action)}
      ${state.apiKeys.created && !demoMode ? apiKeyCreatedPanel() : ''}
      ${createHint}
      ${createForm}
      ${!demoMode && !(state.apiKeys.created && state.apiKeys.created.key) ? apiKeyUsagePanel('') : ''}
      <section class="panel panel-pad"><div class="billing-section-head"><div><h2 class="section-title">${icon('layui-icon-key')}我的密钥</h2><p class="text-muted">密钥前缀用于识别；为安全起见完整密钥不会在此列表中展示。支持停用（可恢复）与删除（立即失效且不可恢复）。</p></div></div><div class="table-wrap" role="region" aria-label="API Key 列表表格" tabindex="0"><table class="data-table"><thead><tr><th scope="col">名称</th><th scope="col">密钥</th><th scope="col">状态</th><th scope="col">调用次数</th><th scope="col">创建时间</th><th scope="col">操作</th></tr></thead><tbody>${apiKeyRows()}</tbody></table></div><div class="notice" style="margin-top:16px">${icon('layui-icon-tips')}<div>密钥用于调用「开放平台」的 OpenAI 兼容对话接口（见上方接入信息），每次调用按模型计费规则从余额扣费。Key 泄露时可先停用止损，确认不再需要后可删除。</div></div></section>`;
  }

  // ===== 管理后台：状态文案辅助 =====
  function adminUserStatusLabel(status) { return Number(status) === -1 ? ['已删除', 'pending'] : (Number(status) === 1 ? ['已启用', 'success'] : ['已禁用', 'pending']); }
  function adminRoleLabel(role) { return role === 'admin' ? '管理员' : '普通用户'; }
  function adminModelTypeLabel(type) { return { text: '文本', image: '图像', audio: '音频', video: '视频' }[type] || type; }
  function adminModelStatusLabel(status) { return status === 'enabled' ? ['已启用', 'success'] : ['已停用', 'pending']; }
  function adminPayLabel(method) { return { alipay: '支付宝', wxpay: '微信', bank: '网银', mock: '模拟' }[method] || method; }
  function adminStatusZh(status) {
    const map = { pending: '待处理', paid: '已支付', failed: '失败', cancelled: '已取消', success: '成功', refunded: '已退款', issued: '已开票', rejected: '已驳回', enabled: '启用', disabled: '停用' };
    return map[status] || status;
  }
  function adminStatusTag(status) {
    const tone = ['failed', 'cancelled', 'rejected', 'disabled'].includes(status) ? 'pending' : 'success';
    return `<span class="status-tag ${tone}">${icon('layui-icon-vercode')} ${escapeHtml(adminStatusZh(status))}</span>`;
  }
  function adminPager(section, total, page, pageSize) {
    const pageCount = Math.max(1, Math.ceil(total / pageSize));
    const safePage = Math.min(page, pageCount);
    const prev = safePage <= 1 ? 'disabled aria-disabled="true"' : '';
    const next = safePage >= pageCount ? 'disabled aria-disabled="true"' : '';
    return `<div class="billing-pagination"><span>共 ${total} 条</span><div><button type="button" class="btn-quiet" data-admin-page="-1" data-admin-section="${section}" ${prev}>上一页</button><span>第 ${safePage} / ${pageCount} 页</span><button type="button" class="btn-quiet" data-admin-page="1" data-admin-section="${section}" ${next}>下一页</button></div></div>`;
  }
  function adminEmpty(rowCount, colSpan) {
    return rowCount ? '' : `<tr><td colspan="${colSpan}"><div class="empty-state">${icon('layui-icon-file')}<div>暂无数据</div></div></td></tr>`;
  }

  // ===== 管理后台：统计概览 =====
  function adminOverviewView() {
    const o = state.admin.overview || {};
    const cards = [
      ['累计调用', o.total_call, 'layui-icon-release', '次'],
      ['累计消费', money(o.total_cost), 'layui-icon-rmb', '人民币'],
      ['注册用户', o.total_users, 'layui-icon-friends', '人'],
      ['Token 总量', o.total_tokens, 'layui-icon-note', 'tok']
    ].map(([title, value, ic, unit]) => `<article class="panel billing-card"><div class="billing-card-head"><span>${title}</span></div><strong class="billing-amount">${escapeHtml(value == null ? '—' : value)}</strong><span class="billing-unit">${unit}</span></article>`).join('');
    const markup = Number(o.token_markup_pct) || 0;
    const profitCards = [
      ['按token收入', money(o.token_revenue), 'layui-icon-rmb', '元'],
      ['供应商成本', money(o.token_provider_cost), 'layui-icon-template-1', '元'],
      ['毛利', money(o.token_profit), 'layui-icon-chart', '元'],
      ['售价加价比例', `${markup ? markup : '—'}`, 'layui-icon-vercode', markup ? `%（${markup}% = 成本×${(markup / 100).toFixed(2)}）` : '']
    ].map(([title, value, ic, unit]) => `<article class="panel billing-card"><div class="billing-card-head"><span>${title}</span></div><strong class="billing-amount">${escapeHtml(value == null ? '—' : value)}</strong><span class="billing-unit">${unit}</span></article>`).join('');
    return `<section class="billing-summary">${cards}</section>
      <section style="margin-top:16px"><div class="billing-section-head"><div><h2 class="section-title">${icon('layui-icon-vercode')}按 token 模型盈利报表</h2><p class="text-muted">用户售价 = 供应商成本价 × 加价比例（模型行可单独覆盖）；毛利 = 实际结算收入 − 供应商成本。口径：状态为成功的按 token 任务。</p></div></div><section class="billing-summary">${profitCards}</section></section>
      <section class="panel panel-pad" style="margin-top:16px"><div class="billing-section-head"><div><h2 class="section-title">${icon('layui-icon-set')}管理后台</h2><p class="text-muted">从顶部标签切换到用户、模型、钱包、订单、消费与发票审核。</p></div></div><div class="empty-state">${icon('layui-icon-template-1')}<div>选择上方标签开始管理<br><small>概览统计口径与后端 /api/admin/stats/usage 一致。</small></div></div></section>`;
  }

  // ===== 管理后台：用户管理 =====
  function adminUsersView() {
    const u = state.admin.users;
    const rows = (u.records || []).map(item => {
      const id = Number(item.id);
      const st = adminUserStatusLabel(item.status);
      const isDel = Number(item.status) === -1;
      const disabled = id === u.busyId;
      const auth = Number(item.real_auth_status);
      const authTag = auth === 1 ? '<span class="status-tag success">已认证</span>' : (auth === 2 ? '<span class="status-tag pending">审核中</span>' : '<span class="status-tag pending">未认证</span>');
      const toggle = Number(item.status) === 1 ? 0 : 1;
      const tLabel = isDel ? '—' : (Number(item.status) === 1 ? '禁用' : '启用');
      const tBtn = isDel ? '' : `<button class="btn-quiet" type="button" data-admin-user-toggle="${id}" data-admin-user-next="${toggle}" ${disabled ? 'disabled aria-disabled="true"' : ''}>${disabled ? '处理中…' : tLabel}</button>`;
      return `<tr data-deleted="${isDel ? '1' : '0'}"><td><strong>${escapeHtml(item.username)}</strong><br><small class="text-muted">#${id}${escapeHtml(item.nickname ? ' · ' + item.nickname : '')}</small></td><td>${adminRoleLabel(item.role)}</td><td><span class="status-tag ${st[1]}">${icon('layui-icon-vercode')} ${st[0]}</span></td><td>${authTag}</td><td>${escapeHtml(money(item.balance))}</td><td>${escapeHtml(money(item.total_consumed))}</td><td>${escapeHtml(item.school || '—')}</td><td>${escapeHtml(item.phone || '—')}</td><td>${escapeHtml(dateText(item.created_at))}</td><td>${isDel ? '<span class="text-muted">已删除</span>' : `<button class="btn-quiet" type="button" data-admin-user-edit="${id}" data-admin-user-username="${escapeHtml(item.username)}">编辑</button> ${tBtn} <button class="btn-quiet danger" type="button" data-admin-user-del="${id}" data-admin-user-username="${escapeHtml(item.username)}">删除</button>`}</td></tr>`;
    }).join('');
    const form = u.formOpen ? adminUserForm(u.editing) : '';
    return `<div class="billing-section-head" style="margin-bottom:14px"><div><h2 class="section-title">${icon('layui-icon-set')}用户管理</h2><p class="text-muted">查询 / 编辑 / 禁用 / 软删除 / 余额调整 / 重置密码。删除为软删(status=-1),可点右上刷新只显示在用用户。</p></div></div>
      ${form}
      <div class="billing-toolbar"><div class="filters"><input class="field search-field" id="admin-user-search" value="${escapeHtml(u.keyword || '')}" placeholder="搜索用户名/学校…" aria-label="搜索用户名" /></div>
      <select class="select-field" id="admin-user-role" aria-label="角色筛选"><option value="">全部角色</option><option value="admin" ${u.role === 'admin' ? 'selected' : ''}>管理员</option><option value="user" ${u.role === 'user' ? 'selected' : ''}>普通用户</option></select>
      <select class="select-field" id="admin-user-status" aria-label="状态筛选"><option value="">全部状态</option><option value="1" ${u.status === '1' ? 'selected' : ''}>已启用</option><option value="0" ${u.status === '0' ? 'selected' : ''}>已禁用</option><option value="-1" ${u.status === '-1' ? 'selected' : ''}>已删除</option></select>
      <button class="btn-secondary" id="admin-user-search-btn" type="button">${icon('layui-icon-search')} 搜索</button>
      <button class="btn-quiet" id="admin-user-reset-btn" type="button">${icon('layui-icon-refresh')} 重置</button></div>
      <div class="table-wrap" role="region" aria-label="用户管理表格" tabindex="0"><table class="data-table"><thead><tr><th scope="col">用户名</th><th scope="col">角色</th><th scope="col">状态</th><th scope="col">实名</th><th scope="col">余额</th><th scope="col">累计消费</th><th scope="col">学校</th><th scope="col">手机号</th><th scope="col">注册时间</th><th scope="col">操作</th></tr></thead><tbody>${adminEmpty(u.records.length, 10)}${rows}</tbody></table></div>${adminPager('users', u.total, u.page, u.pageSize)}`;
  }
  function adminUserForm(editing) {
    const e = editing || {};
    const roleOpts = [['user', '普通用户'], ['admin', '管理员']];
    const authOpts = [['0', '未认证'], ['1', '已认证'], ['2', '审核中']];
    return `<section class="panel panel-pad invoice-form-panel" style="margin-bottom:16px"><div class="billing-section-head"><div><h2 class="section-title">${icon('layui-icon-edit')}${e.id ? '编辑用户 #' + e.id + ' · ' + escapeHtml(e.username || '') : '新建用户'}</h2></div></div><form id="admin-user-form" data-user-id="${e.id || ''}"><div class="form-grid">
      <div class="form-block"><label class="field-label" for="au-role">角色</label><select class="select-field" id="au-role">${roleOpts.map(([v, l]) => `<option value="${v}" ${e.role === v ? 'selected' : ''}>${l}</option>`).join('')}</select></div>
      <div class="form-block"><label class="field-label" for="au-auth">实名认证</label><select class="select-field" id="au-auth">${authOpts.map(([v, l]) => `<option value="${v}" ${String(e.real_auth_status) === v ? 'selected' : ''}>${l}</option>`).join('')}</select></div>
      <div class="form-block"><label class="field-label" for="au-nickname">昵称</label><input class="field" id="au-nickname" maxlength="50" value="${escapeHtml(e.nickname || '')}" /></div>
      <div class="form-block"><label class="field-label" for="au-phone">手机号</label><input class="field" id="au-phone" maxlength="20" value="${escapeHtml(e.phone || '')}" /></div>
      <div class="form-block"><label class="field-label" for="au-email">邮箱</label><input class="field" id="au-email" maxlength="100" value="${escapeHtml(e.email || '')}" /></div>
      <div class="form-block"><label class="field-label" for="au-school">学校</label><input class="field" id="au-school" maxlength="100" value="${escapeHtml(e.school || '')}" /></div>
      <div class="form-block"><label class="field-label" for="au-balance">余额调整(分,负数为扣减)</label><input class="field" id="au-balance" type="number" step="1" placeholder="留空则不变" value="" /></div>
      <div class="form-block"><label class="field-label" for="au-password">重置密码(留空则不改)</label><input class="field" id="au-password" type="password" autocomplete="new-password" maxlength="64" placeholder="至少8位" value="" /></div>
      </div>
      <div class="form-block"><p class="text-muted">当前余额：${escapeHtml(money(e.balance))} ｜ 累计消费：${escapeHtml(money(e.total_consumed))}</p></div>
      <div class="invoice-form-actions"><button class="btn-quiet" id="admin-user-form-cancel" type="button">取消</button><button class="btn-primary" id="admin-user-form-submit" type="submit" ${state.admin.users.busy ? 'disabled' : ''}>${state.admin.users.busy ? '正在保存…' : '保存'}</button></div></form></section>`;
  }

  // ===== 管理后台：模型管理 =====
  function adminModelsView() {
    const m = state.admin.models;
    const rows = (m.records || []).map(item => {
      const st = adminModelStatusLabel(item.status);
      const disabled = item.id === m.busyId;
      const toggle = item.status === 'enabled' ? 'disabled' : 'enabled';
      const tLabel = item.status === 'enabled' ? '停用' : '启用';
      const tags = Array.isArray(item.capability_tags) && item.capability_tags.length ? item.capability_tags.map(t => `<span class="tag">${escapeHtml(t)}</span>`).join('') : '';
      return `<tr><td><strong>${escapeHtml(item.name)}</strong><br><small class="text-muted">${escapeHtml(item.model_code)}</small></td><td>${adminModelTypeLabel(item.model_type)}</td><td>${escapeHtml(item.provider_type)} / ${escapeHtml(item.vendor)}</td><td>${item.billing_mode === 'per_token' ? `<span class="text-muted">按token</span><br><small>成本 入${item.token_input_price || 0}/出${item.token_output_price || 0}‱<br>售价 入${item.sell_input_price ?? '—'}/出${item.sell_output_price ?? '—'}‱${item.token_markup_pct ? ` · ${item.token_markup_pct}%` : ''}</small>` : (Number.isFinite(Number(item.price_per_call)) ? `<small>成本 ¥${item.price_per_call}${perCallUnit(item.model_type)}<br>售价 ${escapeHtml(money(item.sell_price_per_call))}${perCallUnit(item.model_type)}</small>` : '—')}</td><td><span class="status-tag ${st[1]}">${icon('layui-icon-vercode')} ${st[0]}</span></td><td>${tags || '—'}</td><td><button class="btn-quiet" type="button" data-admin-model-edit="${item.id}" data-admin-model-name="${escapeHtml(item.name)}">编辑</button> <button class="btn-quiet" type="button" data-admin-model-status="${item.id}" data-admin-model-next="${toggle}" ${disabled ? 'disabled aria-disabled="true"' : ''}>${disabled ? '处理中…' : tLabel}</button> <button class="btn-quiet" type="button" data-admin-model-del="${item.id}" data-admin-model-name="${escapeHtml(item.name)}">删除</button></td></tr>`;
    }).join('');
    const form = m.formOpen ? adminModelForm(m.editing) : '';
    const openLabel = m.formOpen ? '收起表单' : (m.editing ? '继续编辑' : '新建模型');
    return `<div class="billing-section-head" style="margin-bottom:14px"><div><h2 class="section-title">${icon('layui-icon-set')}模型管理</h2><p class="text-muted">创建 / 编辑 / 启停 / 删除门户模型，列表含停用项。</p></div><button class="btn-primary" id="admin-model-toggle-form" type="button">${icon('layui-icon-add-1')} ${openLabel}</button></div>
      ${form}
      <div class="billing-toolbar"><div class="filters"><input class="field search-field" id="admin-model-search" value="${escapeHtml(m.keyword || '')}" placeholder="搜索模型名/描述…" aria-label="搜索模型" /></div><button class="btn-secondary" id="admin-model-search-btn" type="button">${icon('layui-icon-search')} 搜索</button></div>
      <div class="table-wrap" role="region" aria-label="模型管理表格" tabindex="0"><table class="data-table"><thead><tr><th scope="col">模型</th><th scope="col">类型</th><th scope="col">来源</th><th scope="col">单价</th><th scope="col">状态</th><th scope="col">能力标签</th><th scope="col">操作</th></tr></thead><tbody>${adminEmpty(m.records.length, 7)}${rows}</tbody></table></div>${adminPager('models', m.total, m.page, m.pageSize)}`;
  }
  function adminModelForm(editing) {
    const e = editing || {};
    const vt = ['text', 'image', 'audio', 'video'];
    const vp = ['online', 'local'];
    return `<section class="panel panel-pad invoice-form-panel" style="margin-bottom:16px"><div class="billing-section-head"><div><h2 class="section-title">${icon('layui-icon-edit')}${editing ? '编辑模型 #' + e.id : '新建模型'}</h2></div></div><form id="admin-model-form" data-model-id="${e.id || ''}"><div class="form-grid">
      <div class="form-block"><label class="field-label" for="am-name">名称<span class="required">*</span></label><input class="field" id="am-name" maxlength="100" required value="${escapeHtml(e.name || '')}" /></div>
      <div class="form-block"><label class="field-label" for="am-code">厂商调用名(model_code)<span class="required">*</span></label><input class="field" id="am-code" maxlength="200" required value="${escapeHtml(e.model_code || '')}" /></div>
      <div class="form-block"><label class="field-label" for="am-type">类型<span class="required">*</span></label><select class="select-field" id="am-type">${vt.map(t => `<option value="${t}" ${e.model_type === t ? 'selected' : ''}>${adminModelTypeLabel(t)}</option>`).join('')}</select></div>
      <div class="form-block"><label class="field-label" for="am-provider">来源(provider)<span class="required">*</span></label><select class="select-field" id="am-provider">${vp.map(p => `<option value="${p}" ${e.provider_type === p ? 'selected' : ''}>${p === 'online' ? '云端' : '本地'}</option>`).join('')}</select></div>
      <div class="form-block"><label class="field-label" for="am-vendor">厂商(vendor)<span class="required">*</span></label><input class="field" id="am-vendor" maxlength="30" required value="${escapeHtml(e.vendor || '')}" placeholder="内置 siliconflow / dashscope / ollama / mock，或自定义供应商名" /></div>
      <div class="form-block"><label class="field-label" for="am-endpoint">base_url(endpoint)</label><input class="field" id="am-endpoint" maxlength="255" placeholder="自定义供应商填写，如 http://127.0.0.1:11434/v1" value="${escapeHtml(e.endpoint || '')}" /></div>
      <div class="form-block"><label class="field-label" for="am-api-key">api_key(自定义供应商用)</label><input class="field" id="am-api-key" type="password" autocomplete="off" placeholder="${e.api_key ? '已配置（留空表示不修改）' : '自定义供应商填写密钥'}" /></div>
      <div class="form-block"><label class="field-label" for="am-price">成本单价(元/张·条·次)<span class="required">*</span></label><input class="field" id="am-price" type="number" min="0" step="0.01" required value="${e.price_per_call == null ? 0 : e.price_per_call}" /></div>
      <div class="form-block"><label class="field-label" for="am-billing-mode">计费方式</label><select class="select-field" id="am-billing-mode"><option value="per_call" ${(e.billing_mode || 'per_call') === 'per_call' ? 'selected' : ''}>按次(per_call)</option><option value="per_token" ${e.billing_mode === 'per_token' ? 'selected' : ''}>按实际token(per_token)</option></select></div>
      <div class="form-block"><label class="field-label" for="am-token-in">输入token成本价<small class="text-muted">(0.0001元/千token)</small></label><input class="field" id="am-token-in" type="number" min="0" step="1" value="${e.token_input_price == null ? 0 : e.token_input_price}" /></div>
      <div class="form-block"><label class="field-label" for="am-token-out">输出token成本价<small class="text-muted">(0.0001元/千token)</small></label><input class="field" id="am-token-out" type="number" min="0" step="1" value="${e.token_output_price == null ? 0 : e.token_output_price}" /></div>
      <div class="form-block"><label class="field-label" for="am-token-markup">售价加价比例<small class="text-muted">(%,留空=全局默认)</small></label><input class="field" id="am-token-markup" type="number" min="1" max="10000" step="1" placeholder="如 130 = 成本加价 30%" value="${e.token_markup_pct == null ? '' : e.token_markup_pct}" /></div>
      <div class="form-block"><label class="field-label" for="am-duration">音视频时长上限(秒)</label><input class="field" id="am-duration" type="number" min="0" step="1" value="${e.max_duration_sec == null ? '' : e.max_duration_sec}" /></div>
      <div class="form-block"><label class="field-label">获取可用模型</label><div class="admin-fetch-row"><input class="field" id="am-fetch-endpoint" placeholder="base_url" value="${escapeHtml(e.endpoint || '')}" /><input class="field" id="am-fetch-key" type="password" autocomplete="off" placeholder="api_key" /><button class="btn-secondary" type="button" id="am-fetch-models">获取</button></div><select class="select-field" id="am-fetch-select" style="margin-top:6px"><option value="">— 选择获取到的模型 —</option></select></div>
      </div>
      <div class="form-block"><label class="field-label" for="am-desc">说明</label><textarea class="textarea-field" id="am-desc" maxlength="500" rows="2">${escapeHtml(e.description || '')}</textarea></div>
      <div class="form-block"><label class="field-label" for="am-tags">能力标签(逗号分隔)</label><input class="field" id="am-tags" placeholder="如 对话,推理" value="${escapeHtml((e.capability_tags || []).join(','))}" /></div>
      <div class="invoice-form-actions"><button class="btn-quiet" id="admin-model-form-cancel" type="button">取消</button><button class="btn-primary" id="admin-model-form-submit" type="submit" ${mBusy('models') ? 'disabled' : ''}>${mBusy('models') ? '正在保存…' : '保存'}</button></div></form></section>`;
  }

  // ===== 管理后台：钱包 / 订单 / 消费 / 发票 =====
  function adminWalletsView() {
    const w = state.admin.wallets;
    const rows = (w.records || []).map(item => `<tr><td>${escapeHtml(item.username)}</td><td>#${item.user_id}</td><td>${escapeHtml(money(item.balance))}</td><td>${escapeHtml(money(item.total_recharged))}</td><td>${escapeHtml(money(item.total_consumed))}</td><td>${escapeHtml(dateText(item.created_at))}</td></tr>`).join('');
    return `<div class="billing-toolbar"><div class="filters"><input class="field search-field" id="admin-wallet-search" value="${escapeHtml(w.keyword || '')}" placeholder="搜索用户名…" aria-label="搜索用户名" /></div><button class="btn-secondary" id="admin-wallet-search-btn" type="button">${icon('layui-icon-search')} 搜索</button></div>
      <div class="table-wrap" role="region" aria-label="钱包列表" tabindex="0"><table class="data-table"><thead><tr><th scope="col">用户名</th><th scope="col">用户ID</th><th scope="col">余额</th><th scope="col">累计充值</th><th scope="col">累计消费</th><th scope="col">创建时间</th></tr></thead><tbody>${adminEmpty(w.records.length, 6)}${rows}</tbody></table></div>${adminPager('wallets', w.total, w.page, w.pageSize)}`;
  }
  function adminOrdersView() {
    const o = state.admin.orders;
    const rows = (o.records || []).map(item => `<tr><td>${escapeHtml(item.order_no)}</td><td>#${item.user_id}</td><td>${escapeHtml(adminPayLabel(item.payment_method))}</td><td>${escapeHtml(money(item.amount))}</td><td>${adminStatusTag(item.status)}</td><td>${escapeHtml(item.external_trade_no || '—')}</td><td>${escapeHtml(dateText(item.created_at))}</td></tr>`).join('');
    return `<div class="table-wrap" role="region" aria-label="充值订单" tabindex="0"><table class="data-table"><thead><tr><th scope="col">订单号</th><th scope="col">用户ID</th><th scope="col">支付方式</th><th scope="col">金额</th><th scope="col">状态</th><th scope="col">外部流水号</th><th scope="col">创建时间</th></tr></thead><tbody>${adminEmpty(o.records.length, 7)}${rows}</tbody></table></div>${adminPager('orders', o.total, o.page, o.pageSize)}`;
  }
  function adminConsumptionsView() {
    const c = state.admin.consumptions;
    const rows = (c.records || []).map(item => `<tr><td>#${item.id}</td><td>#${item.user_id}</td><td>#${item.model_id}</td><td>${escapeHtml(money(item.amount))}</td><td>${adminStatusTag(item.status)}</td><td>${escapeHtml(dateText(item.created_at))}</td></tr>`).join('');
    return `<div class="table-wrap" role="region" aria-label="消费记录" tabindex="0"><table class="data-table"><thead><tr><th scope="col">记录ID</th><th scope="col">用户ID</th><th scope="col">模型ID</th><th scope="col">金额</th><th scope="col">状态</th><th scope="col">创建时间</th></tr></thead><tbody>${adminEmpty(c.records.length, 6)}${rows}</tbody></table></div>${adminPager('consumptions', c.total, c.page, c.pageSize)}`;
  }
  function adminInvoicesView() {
    const inv = state.admin.invoices;
    const rows = (inv.records || []).map(item => {
      const busy = item.id === inv.busyId;
      const rejected = item.status === 'pending';
      const actions = item.status === 'pending'
        ? `<button class="btn-quiet" type="button" data-admin-invoice-review="${item.id}" data-admin-invoice-next="issued" ${busy ? 'disabled' : ''}>${busy ? '处理中…' : '通过'}</button> <button class="btn-quiet" type="button" data-admin-invoice-review="${item.id}" data-admin-invoice-next="rejected" ${busy ? 'disabled' : ''}>驳回</button>`
        : adminStatusTag(item.status);
      return `<tr><td>#${item.id}</td><td>#${item.user_id}</td><td>${escapeHtml(item.title)}</td><td>${item.type === 'enterprise' ? '企业' : '个人'}</td><td>${escapeHtml(money(item.amount))}</td><td>${actions}</td><td>${escapeHtml(item.tax_no || '—')}</td><td>${escapeHtml(dateText(item.created_at))}</td></tr>`;
    }).join('');
    return `<div class="table-wrap" role="region" aria-label="发票审核" tabindex="0"><table class="data-table"><thead><tr><th scope="col">发票ID</th><th scope="col">用户ID</th><th scope="col">抬头</th><th scope="col">类型</th><th scope="col">金额</th><th scope="col">状态</th><th scope="col">税号</th><th scope="col">申请时间</th></tr></thead><tbody>${adminEmpty(inv.records.length, 8)}${rows}</tbody></table></div>${adminPager('invoices', inv.total, inv.page, inv.pageSize)}`;
  }

  // ===== 管理后台：总视图 + 标签切换 =====
  function adminView() {
    if (user.role !== 'admin') return `<main class="auth-required"><section class="panel panel-pad"><span class="auth-icon">${icon('layui-icon-password')}</span><h1>无权限</h1><p>该页面仅限管理员访问。</p></section></main>`;
    const tabs = [
      ['overview', '概览', 'layui-icon-chart-screen'], ['users', '用户管理', 'layui-icon-friends'],
      ['models', '模型管理', 'layui-icon-app'], ['wallets', '钱包', 'layui-icon-rmb'],
      ['orders', '充值订单', 'layui-icon-list'], ['consumptions', '消费记录', 'layui-icon-note'],
      ['invoices', '发票审核', 'layui-icon-file']
    ];
    const tabBar = `<div class="tab-row admin-tab-bar" role="tablist" aria-label="管理后台模块">${tabs.map(([id, label, ic]) => `<button type="button" class="tab-btn ${state.admin.tab === id ? 'active' : ''}" data-admin-tab="${id}" role="tab" aria-selected="${state.admin.tab === id}">${icon(ic)} ${label}</button>`).join('')}</div>`;
    const body = ({ overview: adminOverviewView, users: adminUsersView, models: adminModelsView, wallets: adminWalletsView, orders: adminOrdersView, consumptions: adminConsumptionsView, invoices: adminInvoicesView }[state.admin.tab] || adminOverviewView)();
    return `${pageHead('管理后台', '用户 / 模型 / 钱包与发票的集中管理。')}<section class="panel panel-pad">${tabBar}<div style="margin-top:20px">${body}</div></section>`;
  }

  // ===== 管理后台：数据加载 =====
  function adminListKey(response) {
    if (!response) return [];
    const list = response.list;
    return Array.isArray(list) ? list : (Array.isArray(response.items) ? response.items : []);
  }
  function mBusy() { return Boolean(state.admin.models.busy); }
  function loadAdminOverview() {
    if (state.admin.overview) return Promise.resolve();
    return window.PortalApi.adminUsageStats().then(data => { state.admin.overview = data || {}; }).catch(() => { state.admin.overview = {}; });
  }
  function adminUserQuery() {
    const q = {};
    const kw = String(state.admin.users.keyword || '').trim();
    if (kw) q.keyword = kw;
    const role = String(state.admin.users.role || '');
    if (role) q.role = role;
    const status = String(state.admin.users.status || '');
    if (status !== '') q.status = Number(status);
    return q;
  }
  function adminFetch(section, params) {
    state.admin.error = '';
    state.admin.loading = true;
    const base = Object.assign({ page: 1, page_size: 10 }, params);
    const apiCalls = {
      users: () => window.PortalApi.adminUsers(Object.assign({}, base, adminUserQuery(), { page: state.admin.users.page, page_size: state.admin.users.pageSize }, params)),
      models: () => window.PortalApi.adminModels(Object.assign({}, base, { page: state.admin.models.page, page_size: state.admin.models.pageSize }, params)),
      wallets: () => window.PortalApi.adminWallets(Object.assign({}, base, { page: state.admin.wallets.page, page_size: state.admin.wallets.pageSize }, params)),
      orders: () => window.PortalApi.adminOrders({ page: state.admin.orders.page, page_size: state.admin.orders.pageSize }),
      consumptions: () => window.PortalApi.adminConsumptions({ page: state.admin.consumptions.page, page_size: state.admin.consumptions.pageSize }),
      invoices: () => window.PortalApi.adminInvoices({ page: state.admin.invoices.page, page_size: state.admin.invoices.pageSize })
    };
    const call = apiCalls[section];
    if (!call) { state.admin.loading = false; return Promise.resolve(); }
    return Promise.resolve(call()).then(data => {
      const rec = state.admin[section];
      rec.records = adminListKey(data);
      rec.total = Number(data && data.total) || rec.records.length;
      const maxPage = Math.max(1, Math.ceil(rec.total / rec.pageSize));
      rec.page = Math.min(Number(data && data.page) || 1, maxPage);
      rec.loaded = true;
    }).catch(error => {
      state.admin.error = error && error.message ? error.message : '数据加载失败。';
      toast(state.admin.error, 'error');
    }).finally(() => { state.admin.loading = false; });
  }
  function adminLoadActiveTab() {
    if (user.role !== 'admin') return;
    const tab = state.admin.tab;
    if (tab === 'overview') return loadAdminOverview();
    return adminFetch(tab);
  }

  function viewFor(route) {
    const views = { home: homeView, models: modelsView, text: textView, image: imageView, audio: audioView, video: videoView, tasks: tasksView, profile: profileView, billing: billingView, invoice: invoiceView, usage: usageView, apikeys: apiKeysView, admin: adminView };
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
  // 重渲染时保留表单已填内容(切换尺寸/配音员/模式等操作不再丢失描述词)
  const PRESERVED_FIELD_IDS = ['image-prompt', 'image-negative', 'image-count', 'audio-text',
    'clone-voice-name', 'audio-speed', 'audio-format', 'video-prompt', 'video-negative',
    'video-resolution', 'chat-input'];

  function snapshotFormValues() {
    const saved = {};
    PRESERVED_FIELD_IDS.forEach(id => {
      const el = document.getElementById(id);
      if (el && el.type !== 'file') saved[id] = el.value;
    });
    return saved;
  }

  function restoreFormValues(saved) {
    if (!saved) return;
    PRESERVED_FIELD_IDS.forEach(id => {
      const el = document.getElementById(id);
      if (el && el.type !== 'file' && saved[id] != null) el.value = saved[id];
    });
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
    if (state.route === 'usage') { loadUsageData(); loadModels(); }
    if (state.route === 'apikeys') { loadApiKeysData(); loadModels(); }
    if (state.route === 'text') loadChatHistory();
    if (state.route === 'admin' && user.role === 'admin') adminLoadActiveTab();
    const savedFormValues = snapshotFormValues();
    $('#app').html(shell(state.route, viewFor(state.route)));
    bindEvents();
    restoreFormValues(savedFormValues);
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
  function activeChatWelcome() {
    return [{ role: 'assistant', content: '你好！我是你的 AI 创意助手。你可以让我协助优化文案、解释知识点，或开始一次创作。' }];
  }
  function ensureChatConversation(modelName) {
    const key = String(modelName || state.currentChatModel || 'default');
    if (!state.chatByModel[key]) {
      state.chatByModel[key] = { messages: [], history: [], sessionId: null };
    }
    return state.chatByModel[key];
  }
  // 将当前正在编辑的会话写回所属模型，保证切换后不丢上下文。
  function snapshotCurrentChat() {
    const conv = ensureChatConversation(state.currentChatModel);
    conv.messages = state.chatMessages.slice(-100);
    conv.history = state.chatHistory.slice(0, 100);
    conv.sessionId = state.chatSessionId || null;
  }
  // 让工作副本（chatMessages/chatHistory/chatSessionId）与“当前模型”的会话保持一致。
  function syncActiveChatToCurrentModel() {
    const conv = ensureChatConversation(state.currentChatModel);
    if (!Array.isArray(conv.messages) || !conv.messages.length) conv.messages = activeChatWelcome();
    state.chatMessages = conv.messages;
    state.chatHistory = Array.isArray(conv.history) ? conv.history : [];
    state.chatSessionId = conv.sessionId || null;
  }
  // 真实模式：从服务端拉取当前用户的历史会话，填入侧栏；失败静默保留本地状态。
  function loadChatHistory() {
    if (window.PortalConfig.demoMode || !window.PortalApi || !window.PortalApi.token()) return;
    if (chatHistoryLoaded) return;
    chatHistoryLoaded = true;
    window.PortalApi.listChatSessions({ page: 1, page_size: 100 }).then(data => {
      const items = Array.isArray(data && data.items) ? data.items : [];
      state.chatSessions = items.map(item => ({
        session_id: item.session_id,
        title: item.title || '新会话',
        model_id: item.model_id,
        updated_at: item.updated_at || item.created_at || ''
      }));
      if (state.route === 'text') render();
    }).catch(() => { /* 历史会话加载失败不阻断页面 */ });
  }
  // 会话变化后强制重拉一次（新建会话成功后刷新侧栏）。
  function refreshChatHistory() {
    chatHistoryLoaded = false;
    loadChatHistory();
  }
  // 真实模式：点击历史会话回读该会话的全部消息并切到对应模型。
  function loadChatSession(sessionId) {
    if (window.PortalConfig.demoMode || !window.PortalApi) return;
    window.PortalApi.listSessionMessages(sessionId).then(data => {
      const items = Array.isArray(data && data.items) ? data.items : [];
      const lastModelId = items.length ? items[items.length - 1].model_id : null;
      const model = lastModelId != null ? models.find(item => Number(item.id) === Number(lastModelId)) : null;
      snapshotCurrentChat();
      if (model && model.name !== state.currentChatModel) state.currentChatModel = model.name;
      state.chatSessionId = sessionId;
      state.chatMessages = items.length
        ? items.map(item => ({ role: item.role, content: item.content }))
        : activeChatWelcome();
      const conv = ensureChatConversation(state.currentChatModel);
      conv.sessionId = sessionId;
      conv.messages = state.chatMessages.slice(-100);
      render();
    }).catch(error => toast(error && error.message ? error.message : '历史会话加载失败，请稍后重试。', 'error'));
  }
  // 切换到指定模型并加载其独立的会话；reset=true 时为当前模型另起新会话。
  function activateChatFor(modelName, reset) {
    if (modelName) {
      snapshotCurrentChat(); // 先把上一个模型没写完的上下文归档
      state.currentChatModel = String(modelName);
    }
    if (reset) {
      const conv = ensureChatConversation(state.currentChatModel);
      conv.messages = [{ role: 'assistant', content: '已创建新会话。告诉我你想完成什么，我会从这里开始协助。' }];
      conv.history = [];
      conv.sessionId = null;
    }
    syncActiveChatToCurrentModel();
  }
  function sendChat() {
    const input = $('#chat-input'); const prompt = input.val().trim();
    if (!prompt) return toast('请输入问题或指令后再发送。', 'error');
    if (state.busy.text) return toast('上一条消息仍在处理中，请稍候。', 'error');
    const model = currentModel('text');
    if (!window.PortalConfig.demoMode && !model) return toast('当前没有可用的文本模型，请先在模型广场确认模型状态。', 'error');
    state.busy.text = true;
    input.val(''); // 已入列发送,显式清空(重渲染保留逻辑不再依赖清空)
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
            if (event.done) {
              // 服务端按实际 token 结算后回传:展示本次用量与扣费
              const tokens = Number(event.tokens) || 0;
              const cost = Number(event.cost) || 0;
              state.chatMessages[state.chatMessages.length - 1] = {
                role: 'assistant', content: answer,
                meta: `本次 ${tokens} tokens · 扣费 ${money(cost)}${event.prompt_tokens != null ? `（输入 ${event.prompt_tokens} / 输出 ${event.completion_tokens}）` : ''}`,
              };
            }
          }).then(() => ({ answer }));
        });
    stream.then(result => {
      const prev = state.chatMessages[state.chatMessages.length - 1] || {};
      state.chatMessages[state.chatMessages.length - 1] = {
        role: 'assistant',
        content: result.answer || '模型未返回文本内容。',
        meta: prev.meta,
      };
      state.chatHistory.unshift({ title: prompt.slice(0, 18) + (prompt.length > 18 ? '…' : ''), date: '刚刚' });
    }).catch(error => {
      state.chatMessages[state.chatMessages.length - 1] = { role: 'assistant', content: error && error.message ? error.message : '当前模型暂时无法响应，请稍后重试。' };
      toast(streamFailureMessage(error), 'error');
    }).finally(() => {
      state.busy.text = false;
      snapshotCurrentChat(); // 把本轮会话结果与会话id归档到当前模型
      persistDemoState();
      refreshChatHistory(); // 真实模式下新会话已落库，刷新侧栏历史列表
      render();
    });
  }
  function bindEvents() {
    // 输入草稿同步:轮询/模式切换重渲染时保留用户正在输入的内容(error/img 兜底同款一次性委托)
    if (!bindEvents.draftSyncBound) {
      bindEvents.draftSyncBound = true;
      const draftMap = {
        '#image-prompt': 'imagePrompt',
        '#image-negative': 'imageNegative',
        '#audio-text': 'audioText',
        '#video-prompt': 'videoPrompt',
        '#video-negative': 'videoNegative',
        '#clone-voice-name': 'cloneVoiceName',
      };
      $(document).on('input.draft', Object.keys(draftMap).join(','), function () {
        state[draftMap[`#${this.id}`] || ''] = this.value;
      });
    }
    // 用量统计筛选:任一条件变化即按当前筛选重新拉取统计
    if (!bindEvents.usageFilterBound) {
      bindEvents.usageFilterBound = true;
      $(document).on('change.usage-filter', '#usage-filter-model,#usage-filter-type,#usage-filter-days', function () {
        state.usage.filter = {
          model_id: String($('#usage-filter-model').val() || ''),
          task_type: String($('#usage-filter-type').val() || ''),
          days: String($('#usage-filter-days').val() || ''),
        };
        loadUsageData(true);
      });
      $(document).on('click.usage-filter', '#usage-filter-reset', function () {
        state.usage.filter = { model_id: '', task_type: '', days: '' };
        loadUsageData(true);
      });
    }
    // 预览图加载失败兜底:历史任务的旧临时外链已过期时给出明确解释(原生 capture,error 不冒泡)
    if (!bindEvents.imgFallbackBound) {
      bindEvents.imgFallbackBound = true;
      document.addEventListener('error', event => {
        const img = event.target;
        if (!(img instanceof HTMLImageElement) || !img.closest('.preview-art')) return;
        const box = document.createElement('div');
        box.className = 'preview-art-inner';
        box.innerHTML = `<strong>原图无法访问</strong><span>该结果保存于早期版本,使用的是供应商临时链接,现已过期;新提交的任务结果会永久保存在平台,可直接查看。</span>`;
        img.replaceWith(box);
      }, true);
    }
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
    $('[data-use-model]').on('click', function () { const model = $(this).data('use-model'); const found = models.find(item => item.name === model); if (!found) return; if (found.modelType === 'text' || found.type === '语言模型' || found.type === '本地模型') { activateChatFor(model); setRoute('text'); } else if (found.modelType === 'image' || found.type === '生图模型') { state.selectedModelIds.image = modelSelectionKey(found); setRoute('image'); } else if (found.modelType === 'audio' || found.type === 'TTS模型') { state.selectedModelIds.audio = modelSelectionKey(found); setRoute('audio'); } else if (found.modelType === 'video' || found.type === '生视频模型') { state.selectedModelIds.video = modelSelectionKey(found); setRoute('video'); } else toast('该模型的应用入口正在准备中。'); });
    $('[data-source]').on('click', function () { state.modelSource = $(this).data('source'); render(); });
    $('[data-group]').on('click', function () { state.modelGroup = $(this).data('group'); render(); });
    $('[data-type]').on('click', function () { state.modelType = $(this).data('type'); render(); });
    $('#model-search').on('input', function () { state.keyword = $(this).val(); $('.models-grid').html(modelResultsHtml()); });
    $('[data-chat-model]').on('click', function () {
      const next = String($(this).data('chat-model'));
      if (next === state.currentChatModel) return;
      if (state.busy.text) return toast('当前模型仍在生成中，请稍候再切换模型。', 'error');
      activateChatFor(next);
      render();
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
    $('#new-chat, #new-chat-side').on('click', () => { activateChatFor(state.currentChatModel, true); persistDemoState(); render(); });
    $('[data-chat-session]').on('click keydown', function (event) {
      if (event.type === 'keydown' && event.key !== 'Enter' && event.key !== ' ') return;
      if (event.type === 'keydown') event.preventDefault();
      if (state.busy.text) return toast('当前模型仍在生成中，请稍候再切换会话。', 'error');
      const sessionId = $(this).data('chat-session');
      if (sessionId != null) loadChatSession(sessionId);
    });
    $('[data-image-mode]').on('click', function () { state.imageMode = $(this).data('image-mode'); render(); });
    $('[data-ratio]').on('click', function () { state.imageRatio = $(this).data('ratio'); render(); });
    $('#image-form').on('submit', function (event) { event.preventDefault(); const prompt = $('#image-prompt').val().trim(); if (!prompt) return toast('请先填写图像描述词。', 'error'); if (state.busy.image) return; state.busy.image = true; const title = prompt.slice(0, 22) + (prompt.length > 22 ? '…' : ''); const model = currentModel('image'); const submit = window.PortalConfig.demoMode ? Promise.resolve(createRecord('image', { title, mode: state.imageMode, meta: state.imageRatio, shouldFail: shouldSimulateFailure(prompt) })) : (model ? window.PortalApi.task('image', { model_id: model.id, prompt, params: { image_size: state.imageRatio.split(' ')[1].replace('×', 'x'), num: Number($('#image-count').val()) } }).then(result => remoteRecord('image', result, title, state.imageMode, state.imageRatio)) : Promise.reject({ message: '当前没有可用的图像模型。' })); submit.then(() => toast('图像任务已提交，正在生成。', 'success')).catch(error => toast(error && error.message ? error.message : '图像任务提交失败。', 'error')).finally(() => { state.busy.image = false; render(); }); });
    $('[data-audio-mode]').on('click', function () { state.audioMode = $(this).data('audio-mode'); render(); });
    $('[data-voice]').on('click', function () { state.selectedVoice = $(this).data('voice'); render(); });
    $('#audio-text').on('input', function () { $('#audio-count').text(`${$(this).val().length} / 2000 字符`); });
    $('#audio-form').on('submit', function (event) { event.preventDefault(); if (!window.PortalConfig.demoMode) return; const text = $('#audio-text').val().trim(); if (!text) return toast('请先输入需要合成的文本。', 'error'); if (state.busy.audio) return; state.busy.audio = true; const record = createRecord('audio', { title: text.slice(0, 20) + (text.length > 20 ? '…' : ''), mode: state.audioMode, meta: `${text.length} 字符`, shouldFail: shouldSimulateFailure(text) }); if (!record) { state.busy.audio = false; return; } state.busy.audio = false; toast('声音任务已提交，请在历史中查看进度。', 'success'); render(); });
    $('[data-video-duration]').on('click', function () { state.videoDuration = $(this).data('video-duration'); render(); });
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
      const points = Math.floor(amount);
      const available = invoiceAvailableMinor();
      if (points <= 0 || points > available) return toast(`申请金额不能超过可开票金额 ${money(available)}。`, 'error');
      state.invoice.formBusy = true;
      $('#invoice-submit').prop('disabled', true).text('正在提交…');
      window.PortalApi.createInvoice({ amount: points, title, type, tax_no: taxNo || null }).then(() => {
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

    // ===== 个人中心 · API Key 管理 事件 =====
    $('#api-key-create-open').on('click', function () { state.apiKeys.createOpen = true; render(); });
    $('#api-key-create-cancel, #api-key-create-cancel-bottom').on('click', function () { state.apiKeys.createOpen = false; render(); });
    $('#api-key-create-form').on('submit', function (event) {
      event.preventDefault();
      const name = normalizeText($('#api-key-name').val(), '', 100);
      if (!name) return toast('请填写密钥名称。', 'error');
      if (state.apiKeys.createBusy) return;
      state.apiKeys.createBusy = true;
      $('#api-key-create-submit').prop('disabled', true).text('正在生成…');
      window.PortalApi.createApiKey({ name }).then(created => {
        state.apiKeys.createBusy = false;
        state.apiKeys.createOpen = false;
        state.apiKeys.loaded = false;
        state.apiKeys.created = created && typeof created === 'object' ? created : null;
        toast('API Key 已生成，请立即复制保存。', 'success');
        render();
      }).catch(error => {
        state.apiKeys.createBusy = false;
        $('#api-key-create-submit').prop('disabled', false).text('生成 Key');
        toast(error && error.message ? error.message : 'API Key 生成失败，请稍后重试。', 'error');
      });
    });
    // 接入信息一键复制(data-copy 携带原文,由 escapeExample 转义后由浏览器还原)
    $(document).off('click.copyFallback').on('click.copyFallback', '[data-copy]', function () {
      const raw = $(this).attr('data-copy');
      if (!raw) return;
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(raw).then(() => toast('已复制到剪贴板。', 'success')).catch(() => toast('复制失败，请手动选择复制。', 'error'));
      } else {
        const input = document.createElement('textarea');
        input.value = raw;
        document.body.appendChild(input);
        input.select();
        document.execCommand('copy');
        document.body.removeChild(input);
        toast('已复制到剪贴板。', 'success');
      }
    });
    $('#api-key-copy').on('click', function () {
      const created = state.apiKeys.created;
      if (!created || !created.key) return;
      const raw = `${created.name || ''} · ${created.key}`;
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(raw).then(() => toast('已复制，请注意安全保存。', 'success')).catch(() => toast('复制失败，请手动选择复制。', 'error'));
      } else {
        const box = document.getElementById('api-key-reveal');
        if (box) { const range = document.createRange(); range.selectNodeContents(box); const sel = window.getSelection(); sel.removeAllRanges(); sel.addRange(range); document.execCommand('copy'); sel.removeAllRanges(); toast('已复制，请注意安全保存。', 'success'); }
      }
    });
    $('[data-key-toggle]').on('click', function () {
      const id = String($(this).data('key-toggle'));
      const next = String($(this).data('key-next'));
      if (state.apiKeys.busyId) return;
      state.apiKeys.busyId = id;
      window.PortalApi.updateApiKeyStatus(id, next).then(() => {
        state.apiKeys.busyId = null;
        state.apiKeys.loaded = false;
        toast(next === 'enabled' ? 'API Key 已启用。' : 'API Key 已停用。', 'success');
        render();
      }).catch(error => {
        state.apiKeys.busyId = null;
        toast(error && error.message ? error.message : '状态更新失败。', 'error');
        render();
      });
    });
    $('[data-key-delete]').on('click', function () {
      const id = String($(this).data('key-delete'));
      const name = String($(this).data('key-name') || '未命名');
      if (state.apiKeys.busyId) return;
      if (!window.confirm(`确定删除 API Key「${name}」吗？删除后该 Key 立即失效，且无法恢复。`)) return;
      state.apiKeys.busyId = id;
      render();
      window.PortalApi.deleteApiKey(id).then(() => {
        state.apiKeys.busyId = null;
        state.apiKeys.loaded = false;
        toast('API Key 已删除。', 'success');
        return window.PortalApi.apiKeys().then(data => {
          state.apiKeys.records = Array.isArray(data) ? data : [];
          state.apiKeys.loaded = true;
        });
      }).catch(error => {
        state.apiKeys.busyId = null;
        toast(error && error.message ? error.message : '删除失败。', 'error');
      }).finally(render);
    });

    if (!window.PortalConfig.demoMode) {
      // 真实模式:分辨率选项对齐上游契约;首帧上传后自动切换图生视频
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
        const isI2I = state.imageMode === '图生图';
        if (!prompt) return toast('请先填写图像描述词。', 'error');
        if (!model) return toast('当前没有可用的图像模型。', 'error');
        const params = {
          image_size: state.imageRatio.split(' ')[1].replace('×', 'x'),
          num: Number($('#image-count').val()),
          negative_prompt: $('#image-negative').val().trim() || undefined
        };
        const ready = Promise.resolve(state.imageRefUrl);
        if (isI2I) {
          const file = $('#image-ref')[0] && $('#image-ref')[0].files ? $('#image-ref')[0].files[0] : null;
          if (!file && !state.imageRefUrl) return toast('图生图请先上传参考图。', 'error');
          if (file) {
            state.busy.imageUpload = true; render();
            return window.PortalApi.upload(file).then(upload => {
              state.imageRefUrl = upload.url;
              state.busy.imageUpload = false;
            }).then(() => $('#image-form').trigger('submit'))
              .catch(error => { state.busy.imageUpload = false; render(); toast(error && error.message ? error.message : '参考图上传失败。', 'error'); });
          }
          params.image_url = state.imageRefUrl;
        }
        state.busy.image = true;
        window.PortalApi.task('image', { model_id: model.id, prompt, params })
          .then(result => {
            remoteRecord('image', result, prompt.slice(0, 22), state.imageMode, state.imageRatio);
            toast('图像任务已提交,完成后结果自动保存在平台。', 'success');
          })
          .catch(error => toast(error && error.message ? error.message : '图像任务提交失败。', 'error'))
          .finally(() => { state.busy.image = false; render(); });
      });
      $('#audio-form').off('submit').on('submit', function (event) {
        event.preventDefault();
        const model = currentModel('audio');
        if (!model) return toast('当前没有可用的音频模型。', 'error');
        const isAsr = state.audioMode === '语音识别';
        const isClone = state.audioMode === '声音克隆';
        state.busy.audio = true;
        const file = isAsr && $('#audio-file')[0] && $('#audio-file')[0].files ? $('#audio-file')[0].files[0] : null;
        const sampleFile = isClone && $('#clone-sample')[0] && $('#clone-sample')[0].files ? $('#clone-sample')[0].files[0] : null;
        const text = !isAsr && $('#audio-text').length ? $('#audio-text').val().trim() : '';
        if (isAsr && !file) {
          state.busy.audio = false;
          return toast('请先上传需要识别的音频。', 'error');
        }
        if (!isAsr && !text) {
          state.busy.audio = false;
          return toast('请先输入需要合成的文本。', 'error');
        }
        if (isClone && !sampleFile && !state.cloneSampleUrl) {
          state.busy.audio = false;
          return toast('声音克隆请先上传人声样例音频。', 'error');
        }
        if (isClone && !String($('#clone-voice-name').val() || '').trim()) {
          state.busy.audio = false;
          return toast('请为克隆音色取一个名称。', 'error');
        }
        const submitAudio = sampleAudioUrl => {
          const payload = isClone
            ? { model_id: model.id, voice_name: String($('#clone-voice-name').val() || '').trim(), text, sample_audio_url: sampleAudioUrl }
            : { model_id: model.id, voice_name: state.selectedVoice, text };
          return window.PortalApi.request({ url: '/api/tasks/audio/clone', method: 'POST', data: payload })
            .then(result => { remoteRecord('audio', result, isClone ? `克隆·${text.slice(0, 14)}` : (isAsr ? (file ? file.name : '识别') : text.slice(0, 20)), state.audioMode, isAsr ? '语音识别' : `${text.length} 字符`); toast(isAsr ? '语音识别任务已提交。' : '声音任务已提交,完成后可在线播放。', 'success'); });
        };
        let submitted;
        if (isAsr) {
          submitted = window.PortalApi.upload(file).then(upload => window.PortalApi.request({ url: '/api/tasks/audio/asr', method: 'POST', data: { model_id: model.id, audio_url: upload.url } }))
            .then(result => { remoteRecord('audio', result, file.name, state.audioMode, '语音识别'); toast('语音识别任务已提交。', 'success'); });
        } else if (isClone && sampleFile) {
          state.busy.cloneSample = true;
          submitted = window.PortalApi.upload(sampleFile).then(upload => {
            state.cloneSampleUrl = upload.url;
            state.busy.cloneSample = false;
            return submitAudio(upload.url);
          }).catch(error => { state.busy.cloneSample = false; throw error; });
        } else {
          submitted = submitAudio(state.cloneSampleUrl);
        }
        submitted
          .catch(error => toast(error && error.message ? error.message : '声音任务提交失败。', 'error'))
          .finally(() => { state.busy.audio = false; state.busy.cloneSample = false; render(); });
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
      const points = Math.floor(Number($('#recharge-amount').val()));
      if (!Number.isFinite(points) || points < 1 || points > 100000) {
        return toast('请输入 1–100000 的充值金额（元）。', 'error');
      }
      state.busy.recharge = true;
      $('#recharge-submit').prop('disabled', true).text('正在提交…');
      window.PortalApi.recharge({ amount: points, payment_method: 'alipay' }).then(result => {
        state.busy.recharge = false;
        if (!result || !result.pay_url) throw { message: '收银台信息缺失，请稍后重试。' };
        // 沙箱模式为站内收银台页(相对路径),支付宝模式为网关绝对地址
        const target = /^https?:/i.test(result.pay_url) ? result.pay_url : (location.origin + result.pay_url);
        window.location.href = target;
      }).catch(error => {
        state.busy.recharge = false;
        $('#recharge-submit').prop('disabled', false).text('去收银台');
        toast(error && error.message ? error.message : '充值下单失败，请稍后重试。', 'error');
      });
    });
    // ===== 手机号绑定(短信验证) =====
    const PHONE_PATTERN = /^1[3-9]\d{9}$/;
    $('#billing-export').on('click', function () {
      window.PortalApi.walletRecordsExport().then(csvText => {
        const blob = new Blob([csvText], { type: 'text/csv;charset=utf-8' });
        const link = document.createElement('a');
        link.href = URL.createObjectURL(blob);
        link.download = `billing-records-${new Date().toISOString().slice(0, 10)}.csv`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(link.href);
        toast('账单已导出。', 'success');
      }).catch(error => toast(error && error.message ? error.message : '账单导出失败。', 'error'));
    });
    $('#bind-send-btn').on('click', function () {
      const phone = String($('#bind-phone').val() || '').trim();
      if (!PHONE_PATTERN.test(phone)) return toast('请输入正确的 11 位手机号。', 'error');
      const btn = $(this).prop('disabled', true);
      window.PortalApi.smsSend({ phone, purpose: 'bind' }).then(() => {
        toast('验证码已发送，请查收短信。', 'success');
        let left = 60;
        const timer = setInterval(() => {
          left -= 1;
          if (left <= 0) { clearInterval(timer); btn.prop('disabled', false).text('获取验证码'); }
          else btn.text(`${left} s 后重发`);
        }, 1000);
      }).catch(error => {
        btn.prop('disabled', false);
        toast(error && error.message ? error.message : '验证码发送失败，请稍后重试。', 'error');
      });
    });
    $('#phone-bind-form').on('submit', function (event) {
      event.preventDefault();
      if (state.busy.phoneBind) return;
      const phone = String($('#bind-phone').val() || '').trim();
      const code = String($('#bind-code').val() || '').trim();
      if (!PHONE_PATTERN.test(phone)) return toast('请输入正确的 11 位手机号。', 'error');
      if (!/^\d{6}$/.test(code)) return toast('请输入 6 位数字验证码。', 'error');
      state.busy.phoneBind = true;
      $('#bind-submit').prop('disabled', true).text('绑定中…');
      window.PortalApi.smsBind({ phone, code }).then(() => {
        state.busy.phoneBind = false;
        toast('手机号绑定成功，之后可用短信验证码登录。', 'success');
        return window.PortalApi.currentUser().then(me => {
          if (me && typeof me === 'object') applyCurrentUser(me);
          render();
        });
      }).catch(error => {
        state.busy.phoneBind = false;
        $('#bind-submit').prop('disabled', false).text('绑定手机号');
        toast(error && error.message ? error.message : '绑定失败，请稍后重试。', 'error');
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

    // ===== 管理后台事件 =====
    const adminIsOn = () => state.route === 'admin' && user.role === 'admin';
    $('[data-admin-tab]').on('click', function () {
      if (!adminIsOn()) return;
      const tab = $(this).data('admin-tab');
      if (state.admin.tab === tab) return;
      state.admin.tab = tab;
      render();
    });
    $('[data-admin-page]').on('click', function () {
      if (!adminIsOn()) return;
      const section = $(this).data('admin-section');
      const delta = Number($(this).data('admin-page'));
      const rec = state.admin[section];
      if (!rec) return;
      rec.page = Math.max(1, rec.page + delta);
      render();
      adminFetch(section, section === 'users' ? adminUserQuery() : (section === 'models' || section === 'wallets' ? { keyword: rec.keyword } : undefined)).then(render);
    });
    $('#admin-user-search-btn').on('click', function () {
      if (!adminIsOn()) return;
      state.admin.users.keyword = String($('#admin-user-search').val() || '').trim();
      state.admin.users.role = String($('#admin-user-role').val() || '');
      state.admin.users.status = String($('#admin-user-status').val() || '');
      state.admin.users.page = 1;
      render();
      adminFetch('users', adminUserQuery()).then(render);
    });
    $('#admin-user-search').on('keydown', function (e) { if (e.key === 'Enter') $('#admin-user-search-btn').trigger('click'); });
    $('#admin-user-role, #admin-user-status').on('change', function () { $('#admin-user-search-btn').trigger('click'); });
    $('#admin-user-reset-btn').on('click', function () {
      if (!adminIsOn()) return;
      state.admin.users.keyword = '';
      state.admin.users.role = '';
      state.admin.users.status = '';
      state.admin.users.page = 1;
      state.admin.users.formOpen = false;
      state.admin.users.editing = null;
      render();
      adminFetch('users', {}).then(render);
    });
    $('[data-admin-user-edit]').on('click', function () {
      if (!adminIsOn()) return;
      const id = Number($(this).data('admin-user-edit'));
      const rec = (state.admin.users.records || []).find(item => Number(item.id) === id) || { id };
      state.admin.users.editing = rec;
      state.admin.users.formOpen = true;
      render();
    });
    $('#admin-user-form-cancel').on('click', function () {
      if (!adminIsOn()) return;
      state.admin.users.formOpen = false;
      state.admin.users.editing = null;
      render();
    });
    $('#admin-user-form').on('submit', function (e) {
      e.preventDefault();
      if (!adminIsOn()) return;
      const id = Number($(this).data('user-id'));
      if (!id) { toast('缺少用户ID，无法保存。', 'error'); return; }
      const balanceVal = String($('#au-balance').val() || '').trim();
      const newPass = String($('#au-password').val() || '');
      const payload = {
        role: String($('#au-role').val() || 'user'),
        real_auth_status: Number($('#au-auth').val()) || 0,
        nickname: String($('#au-nickname').val() || '').trim() || null,
        phone: String($('#au-phone').val() || '').trim() || null,
        email: String($('#au-email').val() || '').trim() || null,
        school: String($('#au-school').val() || '').trim() || null
      };
      if (newPass && newPass.length < 8) { toast('新密码至少 8 位。', 'error'); return; }
      if (balanceVal !== '' && !Number.isFinite(Number(balanceVal))) { toast('余额调整需为整数金额(元)。', 'error'); return; }
      const balanceDelta = balanceVal === '' ? null : Number(balanceVal);
      state.admin.users.busy = true;
      render();
      Promise.resolve()
        .then(() => window.PortalApi.adminUpdateUser(id, payload))
        .then(() => (newPass ? window.PortalApi.adminResetPassword(id, newPass) : Promise.resolve()))
        .then(() => (balanceDelta !== null ? window.PortalApi.adminAdjustBalance(id, balanceDelta, '管理后台手工调整') : Promise.resolve()))
        .then(() => { state.admin.users.busy = false; state.admin.users.formOpen = false; state.admin.users.editing = null; toast('用户信息已保存。', 'success'); return adminFetch('users', adminUserQuery()); })
        .then(render)
        .catch(error => { state.admin.users.busy = false; toast(error && error.message ? error.message : '保存失败。', 'error'); render(); });
    });
    $('[data-admin-user-toggle]').on('click', function () {
      if (!adminIsOn()) return;
      const id = Number($(this).data('admin-user-toggle'));
      const next = Number($(this).data('admin-user-next'));
      state.admin.users.busyId = id;
      render();
      window.PortalApi.adminUpdateUserStatus(id, next).then(() => { toast('用户状态已更新。', 'success'); state.admin.users.busyId = null; return adminFetch('users', adminUserQuery()); }).then(render).catch(error => { state.admin.users.busyId = null; toast(error && error.message ? error.message : '更新失败。', 'error'); render(); });
    });
    $('[data-admin-user-del]').on('click', function () {
      if (!adminIsOn()) return;
      const id = Number($(this).data('admin-user-del'));
      const name = $(this).data('admin-user-username');
      if (!window.confirm(`确定删除用户「${name}」？\n\n软删除后将无法登录，历史订单/消费数据保留可追溯。`)) return;
      state.admin.users.busyId = id;
      render();
      window.PortalApi.adminDeleteUser(id).then(() => { toast('用户已删除(软删)。', 'success'); state.admin.users.busyId = null; return adminFetch('users', adminUserQuery()); }).then(render).catch(error => { state.admin.users.busyId = null; toast(error && error.message ? error.message : '删除失败。', 'error'); render(); });
    });
    $('#admin-model-search-btn').on('click', function () {
      if (!adminIsOn()) return;
      state.admin.models.keyword = String($('#admin-model-search').val() || '').trim();
      state.admin.models.page = 1;
      render();
      adminFetch('models', { keyword: state.admin.models.keyword }).then(render);
    });
    $('#admin-model-search').on('keydown', function (e) { if (e.key === 'Enter') $('#admin-model-search-btn').trigger('click'); });
    $('#admin-wallet-search-btn').on('click', function () {
      if (!adminIsOn()) return;
      state.admin.wallets.keyword = String($('#admin-wallet-search').val() || '').trim();
      state.admin.wallets.page = 1;
      render();
      adminFetch('wallets', { keyword: state.admin.wallets.keyword }).then(render);
    });
    $('#admin-wallet-search').on('keydown', function (e) { if (e.key === 'Enter') $('#admin-wallet-search-btn').trigger('click'); });
    $('#admin-model-toggle-form').on('click', function () {
      if (!adminIsOn()) return;
      state.admin.models.formOpen = !state.admin.models.formOpen;
      state.admin.models.editing = null;
      render();
    });
    $('#admin-model-form-cancel').on('click', function () {
      if (!adminIsOn()) return;
      state.admin.models.formOpen = false;
      state.admin.models.editing = null;
      render();
    });
    $('#am-fetch-models').on('click', function () {
      const baseUrl = String($('#am-fetch-endpoint').val() || '').trim();
      const apiKey = String($('#am-fetch-key').val() || '').trim();
      if (!baseUrl) return toast('请先填写 base_url。', 'error');
      window.PortalApi.adminFetchModels(baseUrl, apiKey).then(data => {
        const models = Array.isArray(data && data.models) ? data.models : [];
        if (!models.length) return toast('未获取到模型，请检查 base_url 与 api_key。', 'error');
        $('#am-fetch-select').html('<option value="">— 选择获取到的模型 —</option>' + models.map(m => `<option value="${escapeHtml(m.id)}" data-name="${escapeHtml(m.name)}">${escapeHtml(m.name)}（${escapeHtml(m.id)}）</option>`).join(''));
        toast(`已获取 ${models.length} 个模型。`, 'success');
      }).catch(error => toast(error && error.message ? error.message : '获取模型失败。', 'error'));
    });
    $('#am-fetch-select').on('change', function () {
      const id = $(this).val();
      const name = $(this).find('option:selected').data('name') || id;
      if (id) { $('#am-code').val(id); if (!$('#am-name').val()) $('#am-name').val(name); }
    });
    $('[data-admin-model-edit]').on('click', function () {
      if (!adminIsOn()) return;
      const id = Number($(this).data('admin-model-edit'));
      const rec = (state.admin.models.records || []).find(item => Number(item.id) === id);
      state.admin.models.editing = rec || { id };
      state.admin.models.formOpen = true;
      render();
    });
    $('[data-admin-model-status]').on('click', function () {
      if (!adminIsOn()) return;
      const id = Number($(this).data('admin-model-status'));
      const next = $(this).data('admin-model-next');
      state.admin.models.busyId = id;
      render();
      window.PortalApi.adminUpdateModelStatus(id, next).then(() => { toast('模型状态已更新。', 'success'); state.admin.models.busyId = null; return adminFetch('models', { keyword: state.admin.models.keyword }); }).then(render).catch(error => { state.admin.models.busyId = null; toast(error && error.message ? error.message : '更新失败。', 'error'); render(); });
    });
    $('[data-admin-model-del]').on('click', function () {
      if (!adminIsOn()) return;
      const id = Number($(this).data('admin-model-del'));
      const name = $(this).data('admin-model-name');
      if (!window.confirm(`确定删除模型「${name}」？该操作不可恢复。`)) return;
      state.admin.models.busyId = id;
      render();
      window.PortalApi.adminDeleteModel(id).then(() => { toast('模型已删除。', 'success'); state.admin.models.busyId = null; return adminFetch('models', { keyword: state.admin.models.keyword }); }).then(render).catch(error => { state.admin.models.busyId = null; toast(error && error.message ? error.message : '删除失败。', 'error'); render(); });
    });
    $('#admin-model-form').on('submit', function (e) {
      e.preventDefault();
      if (!adminIsOn()) return;
      const id = String($(this).data('model-id') || '');
      const payload = {
        name: String($('#am-name').val() || '').trim(),
        model_code: String($('#am-code').val() || '').trim(),
        model_type: String($('#am-type').val() || 'text'),
        provider_type: String($('#am-provider').val() || 'online'),
        vendor: String($('#am-vendor').val() || 'siliconflow'),
        price_per_call: Number($('#am-price').val()) || 0,
        billing_mode: String($('#am-billing-mode').val() || 'per_call'),
        token_input_price: Number($('#am-token-in').val()) || 0,
        token_output_price: Number($('#am-token-out').val()) || 0,
        token_markup_pct: $('#am-token-markup').val() === '' ? null : Number($('#am-token-markup').val()),
        endpoint: String($('#am-endpoint').val() || '').trim() || null,
        api_key: String($('#am-api-key').val() || '').trim() || null,
        max_duration_sec: $('#am-duration').val() === '' ? null : Number($('#am-duration').val()),
        description: String($('#am-desc').val() || '').trim() || null,
        capability_tags: String($('#am-tags').val() || '').split(/[,，]/).map(t => t.trim()).filter(Boolean)
      };
      state.admin.models.busy = true;
      render();
      const call = id ? window.PortalApi.adminUpdateModel(Number(id), payload) : window.PortalApi.adminCreateModel(payload);
      call.then(() => { state.admin.models.busy = false; state.admin.models.formOpen = false; state.admin.models.editing = null; toast('模型已保存。', 'success'); return adminFetch('models', { keyword: state.admin.models.keyword }); }).then(render).catch(error => { state.admin.models.busy = false; toast(error && error.message ? error.message : '保存失败。', 'error'); render(); });
    });
    $('[data-admin-invoice-review]').on('click', function () {
      if (!adminIsOn()) return;
      const id = Number($(this).data('admin-invoice-review'));
      const next = $(this).data('admin-invoice-next');
      const rec = (state.admin.invoices.records || []).find(item => Number(item.id) === id);
      const tip = next === 'issued' ? '确定通过该开票申请？' : '确定驳回该开票申请？';
      if (rec && !window.confirm(`${tip}（${rec.title}，¥${escapeHtml(money(rec.amount))}）`)) return;
      state.admin.invoices.busyId = id;
      render();
      window.PortalApi.adminReviewInvoice(id, next).then(() => { toast('发票审核状态已更新。', 'success'); state.admin.invoices.busyId = null; return adminFetch('invoices'); }).then(render).catch(error => { state.admin.invoices.busyId = null; toast(error && error.message ? error.message : '审核失败。', 'error'); render(); });
    });
  }

  window.addEventListener('portal:unauthorized', event => {
    const suffix = event.detail && event.detail.requestId ? `（请求ID：${event.detail.requestId}）` : '';
    toast(`登录状态已失效，请重新登录。${suffix}`, 'error');
  });
  hydrateDemoState();
  resumeDemoTasks();
  $(document).off('change.modelSelect').on('change.modelSelect', '[data-model-select]', function () {
    const type = String($(this).data('model-select') || '');
    if (!['image', 'audio', 'video'].includes(type)) return;
    state.selectedModelIds[type] = String($(this).val() || '') || null;
    const selected = currentModel(type);
    $(`[data-active-model-name="${type}"]`).text(selected ? selected.name : '未选择');
    persistDemoState();
  });

  $(window).on('hashchange', render);
  $(function () { loadCurrentUser().then(loadModels).then(loadTaskHistory).finally(render); });
}());

