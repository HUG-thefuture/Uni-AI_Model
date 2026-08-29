# scripts：部署与运维脚本

- deploy.sh：Linux/宝塔部署（Nginx + Uvicorn/Gunicorn + Supervisor）
- backup.sh：每日备份（MySQL、上传文件、Nginx/宝塔配置、代码版本与依赖清单）
- restore.sh：恢复演练（9/3 前实际执行一次并记录耗时，目标 ≤1 小时）
