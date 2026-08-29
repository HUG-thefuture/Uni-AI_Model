# frontend（成员3：Layui 前端）

页面：index / models / chat / image / audio / video / tasks / profile

```text
frontend/
├── index.html
├── models.html
├── chat.html
├── image.html
├── audio.html
├── video.html
├── tasks.html
├── profile.html
├── css/   # 公共样式
└── js/    # layui 配置、ajax 封装、公共组件
```

统一处理加载/成功/失败/空数据/任务轮询/重试；禁止前端直连第三方模型。
