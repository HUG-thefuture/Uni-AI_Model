/* 前后端联通配置（单一切换开关）。
 *
 * - apiBase: 后端 FastAPI 地址。本地一键启动器运行在 8000 端口；
 *   后端 CORS 已放行 localhost / 127.0.0.1 任意端口，跨域可直接访问。
 * - demoMode: false = 走真实后端接口（认证 / 模型 / 任务）；
 *   true = 纯本地演示数据（业务页面离线可用，不连后端）。
 *
 * 本文件先于 js/api.js 加载，api.js / app.js / auth.js 都会读取 window.PortalConfig。
 */
window.PortalConfig = {
  /* 本地访问走 127.0.0.1；局域网/外界通过 IP 访问时自动跟随页面主机名，
   * 避免把 API 请求打到访问者自己的 127.0.0.1（后端须以 0.0.0.0 监听）。
   * 注：跨主机访问还需后端 CORS_ORIGINS 放行前端来源(如 http://192.168.1.101:4174)。 */
  apiBase: (function () {
    var h = window.location.hostname;
    return (h === 'localhost' || h === '127.0.0.1')
      ? 'http://127.0.0.1:8000'
      : 'http://' + h + ':8000';
  })(),
  demoMode: false
};
