# M 系列稳定性测试结果(WP09)

- 执行日期:2026-08-29 16:38:43
- 脚本:`backend/scripts/test_m_series.py`(本地留证,不进仓库)
- 环境:内存 sqlite(StaticPool)+ TestClient + dependency_overrides;Mock 显式延迟经 mock_delay_sec(WP09 新增)控制;SILICONFLOW_API_KEY 置空。

| 用例 | 名称 | 结果 | 耗时 | 说明 |
| --- | --- | --- | --- | --- |
| M-01 | 线上/本地筛选 | PASS | 0.02s | category=local 返回 1 个模型,全部 provider_type=local,available 存在 |
| M-02 | 类型筛选 | PASS | 0.00s | type=image 仅返回 3 个图像模型(mock/硅基/慢生图) |
| M-03 | 停用联动 | PASS | 0.06s | 停用后门户/任务/开放接口三处联动 409,恢复 enabled 后门户可见,全程零任务零扣费 |
| M-04 | 文本生成超时 | PASS | 2.02s | mock_delay_sec=5s > SSE 总超时 2s,2.0s 内失败:error=生成超时,本次不扣费;cost=0/refunded,余额原样 |
| M-05 | 上游异常不扣费 | PASS | 0.03s | 缺 Key 懒校验: failed,错误「环境变量 SILICONFLOW_API_KEY 未配置,无…」,cost=0/refunded |
| M-06 | 重复提交 409 | PASS | 0.06s | 第二次 409「请勿重复提交」;仅 1 个任务,钱包只扣 10 分(成功结算) |
| M-07 | 失败重试对平 | PASS | 2.19s | failed→retry→succeeded;总扣费 10 分=成功 1 次,失败次 cost=0/refunded,冻结=结算+释放 对平 |
| M-08 | 50 并发冒烟 | PASS | 1.89s | 50 并发提交 0 个 500;request_id 无重复;全部 succeeded(终态);总扣费 500=50×10 精确对平 |

**结果:8/8 PASS**

对平校验:全程 balance 消耗 = settled 任务 cost 之和(20 = 20),失败任务一律 cost=0/refunded。

## 说明

- M-04:`mock_delay_sec=5` > `SSE_TOTAL_TIMEOUT=2`,SSE 末帧 error=「生成超时,本次不扣费」;
- M-05:siliconflow 缺 Key 懒校验在发起网络请求前拦截,任务 failed + 中文提示 + 退费;
- M-07:超时法造 failed(图像总超时 2s < mock_delay_sec 5s),retry 后 succeeded;
- M-08:提交并发走真实路由函数(asyncio.gather,50 个独立 X-Request-Id);sqlite 无行锁,run_db 线程池收敛为单工作线程串行化写(MySQL 生产由 FOR UPDATE 行锁保证并发扣费正确);无 500/重复扣费、全部终态即冒烟通过。
