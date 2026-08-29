# providers：ModelProvider 适配层（成员2）

- BaseProvider：generate_text / generate_image / generate_audio / generate_video / health_check
- OnlineProvider / LocalProvider / DemoProvider / MockProvider
- 第三方调用必须设置连接/读取超时、重试上限、错误转换、request_id 和耗时记录
