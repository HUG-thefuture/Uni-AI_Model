# services：业务逻辑

- 注册事务：users + user_profiles + wallets（余额 0）整体提交
- 扣费事务：校验登录和模型状态 → 预扣/锁定 → 调用模型 → 成功扣费写记录 → 失败释放并标记 failed
