# 前端本地依赖

为避免部署服务器无法访问外部CDN，页面使用以下项目内静态文件：

- jQuery 3.7.1：`vendor/jquery/jquery-3.7.1.min.js`
- Layui 2.9.18：`vendor/layui/layui.js`、`vendor/layui/css/layui.css`及图标字体

文件下载自页面原先使用的 `https://cdn.staticfile.net/` 对应版本路径，未修改第三方功能代码。jQuery与Layui均采用MIT许可证；升级版本时必须同步更新本说明和八个HTML入口，不能只替换其中一个文件。
