# backend/assets/samples · 演示样例

供 MockProvider 离线演示与冒烟脚本使用的样例素材,登记表见 `manifest.json`。

- `sample-image-1.png` ~ `sample-image-4.png`:Mock 文生图的**离线替换图**。默认 Mock 返回公网 dummyimage URL,断网时浏览器加载不到;离线演示前把本目录图片复制到 `backend/uploads/`(经 `/static/<文件名>` 访问),或临时修改 `providers/mock.py` 的 `MOCK_IMAGE_URL`。
- 音频/视频走公网兜底(MDN CC0 样例),离线需提前下载,详见 `manifest.json` 的 `audio_video_fallback`。
- 文本对话样例 3 组(`manifest.json` 的 `text_samples`):门户冒烟标准输入、多轮上下文、长文本+参数透传。
