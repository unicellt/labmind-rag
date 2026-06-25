# LabMind VPS 部署

目标服务器：`64.83.18.184`

公开网址（部署完成后）：`http://64.83.18.184/`

生产结构：

- Nginx 监听公网 80 端口。
- LabMind 仅监听服务器本机 `127.0.0.1:8765`。
- systemd 负责启动和故障重启。
- 公开环境开放 `/api/upload`，单个 PDF 上限 50 MB，并通过 Nginx 对每个 IP 限频。上传立即返回任务 ID，前端通过 `/api/upload-status` 轮询后台解析与索引进度。
- 搜索和问答同时支持 GET 与 POST；公网前端使用 GET，降低跨境网络对长连接 POST 的影响。
- VPS 优先尝试 MinerU；服务器未安装 MinerU 时自动回退 PyPDF2，并重建混合检索索引。
- 问答、检索和文档浏览保持可用。

服务器环境变量保存在 `/etc/labmind.env`。至少配置 `SILICONFLOW_API_KEY`。如果不配置模型密钥，系统会使用本地抽取式答案。
