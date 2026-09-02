/* 前后端联通配置（单一切换开关）。
 *
 * - apiBase: 后端 FastAPI 地址。本地 master 联调服务运行在 8003 端口；
 *   后端 CORS 已放行 localhost / 127.0.0.1 任意端口，跨域可直接访问。
 * - demoMode: false = 走真实后端接口（认证 / 模型 / 任务）；
 *   true = 纯本地演示数据（业务页面离线可用，不连后端）。
 *
 * 本文件先于 js/api.js 加载，api.js / app.js / auth.js 都会读取 window.PortalConfig。
 */
window.PortalConfig = {
  apiBase: 'http://127.0.0.1:8004',
  demoMode: false
};
