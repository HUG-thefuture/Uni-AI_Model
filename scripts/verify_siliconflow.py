"""D1 硬性门槛:硅基流动 API Key 首次真实调用验证(WP01 验收标准3)。

用法(在仓库根目录或 scripts/ 下):
    set SILICONFLOW_API_KEY=sk-xxxx        (Windows CMD)
    $env:SILICONFLOW_API_KEY="sk-xxxx"     (PowerShell)
    python scripts/verify_siliconflow.py

成功会打印模型回复与耗时,请截图留证(晚间对齐会交账)。
密钥只通过环境变量传入,严禁写入本文件或任何入库内容。
"""
import os
import sys
import time

import httpx

BASE_URL = "https://api.siliconflow.cn"
MODEL = "Qwen/Qwen2.5-7B-Instruct"


def main() -> int:
    key = os.getenv("SILICONFLOW_API_KEY", "").strip()
    if not key:
        print("错误:环境变量 SILICONFLOW_API_KEY 未配置。")
        print('示例(PowerShell): $env:SILICONFLOW_API_KEY="sk-xxxx"')
        return 2

    print(f"调用 {MODEL} @ {BASE_URL} ...")
    start = time.monotonic()
    try:
        resp = httpx.post(
            f"{BASE_URL}/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={
                "model": MODEL,
                "messages": [{"role": "user", "content": "用一句话介绍四川高校AI大模型门户项目"}],
                "max_tokens": 100,
            },
            timeout=httpx.Timeout(connect=10, read=60),
        )
    except httpx.HTTPError as exc:
        print(f"网络失败: {exc!r}")
        return 1

    latency = int((time.monotonic() - start) * 1000)
    if resp.status_code != 200:
        print(f"失败 HTTP {resp.status_code}: {resp.text[:300]}")
        return 1

    data = resp.json()
    content = data["choices"][0]["message"]["content"]
    usage = data.get("usage", {})
    print(f"成功!耗时 {latency} ms")
    print(f"回复: {content}")
    print(f"usage: {usage}")
    print(">>> 请截图留证(D1 验收门槛)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
