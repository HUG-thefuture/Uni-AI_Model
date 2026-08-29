# frontend（成员3：Layui 前端）

技术栈：HTML / CSS / JavaScript / Ajax / jQuery / Layui。

## 页面

- `index.html`：首页
- `models.html`：模型广场
- `chat.html`：文本交互舱
- `image.html`：图像生成室
- `audio.html`：声音创作坊
- `video.html`：视频合成站
- `tasks.html`：创作历史
- `profile.html`：个人中心

八个物理入口复用 `css/app.css`、`css/hardening.css`、`js/api.js` 和 `js/app.js`。页面内使用Hash路由，公共顶部栏、侧栏和任务状态组件只维护一份。

## 本地预览

在仓库根目录执行：

```powershell
python -m http.server 4174 --bind 127.0.0.1 --directory frontend
```

浏览器访问 `http://127.0.0.1:4174/index.html`。

页面依赖已经放在 `vendor/`，预览和部署不再依赖外部CDN。

## 当前演示模式

`js/api.js`中的 `demoMode` 默认为 `true`。演示模式具备：

- 图像、声音、视频任务的待处理、处理中、成功、失败状态；
- 任务记录和个人资料本地持久化，刷新页面后仍保留；
- 失败任务真正重新提交，并在第二次演示中完成；
- 文本、图像、声音、视频输入包含 `#失败` 时确定性模拟失败，便于验收异常流程；
- 防止文本重复提交；
- 清空演示任务记录入口；
- 390px移动端导航和表单布局。

图生图、声音克隆、语音识别、长文本转音频和视频音频上传尚未冻结接口字段，相关控件已标记为“待开放”并禁用，避免出现看似可用但实际无功能的入口。

## 接口对接

`js/api.js`已实现以下确定内容：

- 接口统一使用 `/api` 前缀；
- JWT使用 `Authorization: Bearer <token>`；
- 成功数据读取 `{code:0,message,data,request_id}` 中的 `data`；
- 统一处理400、401、403、404、409、429、500和网络中断；
- 401时清理Token并触发 `portal:unauthorized` 事件；
- 配置 `PortalConfig.loginUrl` 后，非演示模式可跳转登录页并携带 `return_to`；
- 已封装健康检查、当前用户、资料更新、模型列表、任务提交和任务详情方法；
- 前端不直连第三方模型服务。

当前业务页面仍使用明确标注的演示数据。成员1、2、4提供正式响应样例后，再切换真实数据源；不要自行猜测任务列表、媒体URL、上传和钱包字段。

后端健康检查可在浏览器控制台执行：

```javascript
PortalApi.health().then(console.log).catch(console.error)
```

## 自检

```powershell
node --check frontend/js/api.js
node --check frontend/js/app.js
```

已验证内容：八个入口返回200、本地静态依赖返回200、模型搜索保持输入焦点、失败任务可重试、任务和资料刷新后保留、390px移动端无横向溢出、移动端侧栏自动收起、浏览器控制台无错误或警告。

## 协作边界

- `sql/002_member2_models_ai_tasks.sql`由成员4与用户三表脚本一并执行，成员3不执行数据库脚本。
- 金额由后端以整数处理，前端只负责格式化展示。
- 长任务状态固定为 `pending / processing / succeeded / failed`。
- 模型失败是否扣费由后端事务保证，前端只显示接口返回结果。
- Git提交前确认 `成员2-工作包与提示词/wp01-交付记录.md` 的删除状态，不能误带入成员3提交。
