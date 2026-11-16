# 今天是太阳雨 · 数据看板

《今天是太阳雨》的单剧数据看板，汇总剧集资料、播出计划、播放量、收视、热度与讨论数据。

[打开在线页面](https://hentailong.github.io/sunrain-dashboard/)

## 看板内容

- 剧集资料：官方海报、主演、剧情简介、更新集数和下次播出倒计时；酷云确认正在播出时显示“播放中”。
- 灯塔：正片播放量、播放市占和排名合并展示，分时图对照今日与昨日。
- 酷云：直播收视、昨日均值、历史最高均值、秒峰值及卫视排名；历史趋势展示官方日均收视。
- 云合：有效播放市占、全舆情热度及各自排名。
- 抖音与猫眼：本剧热度及排名。
- 芒果 TV：累计播放量和剧集更新进度。
- 微博：话题阅读、讨论和官微粉丝。
- 豆瓣：评分、短评和长评；未开分时显示“暂无评分”。
- 百度指数：本剧关键词的全国 PC+移动搜索指数，展示全部已存档统计日。

各平台统计口径独立。页面区分统计时间与采集时间，采集失败时保留上次有效读数；缺失数据不补零、不伪造。

## 图表

首页保留灯塔分时播放、酷云收视、云合有效播放市占、猫眼热度和百度指数。云合与百度指数展示全部统计日期，其余首页图表展示今日数据。

灯塔分时图使用今日播放量柱形、昨日虚线与小时市占折线，并结合完整历史日估算今日总播放量。预测仅供参考，计算方法见[部署与数据说明](docs/github-deployment.md#多日播放预测)。

灯塔、猫眼和酷云详情提供“今日 / 全部”。灯塔今日按分钟对齐昨日，全部展示官方日数据；酷云今日对照昨日分钟曲线，全部展示日均收视。不同播出时段和采集缺口断开连线。

## GitHub 部署

前端由 GitHub Pages 发布，GitHub Actions 负责采集并保存公开数据快照，在线页面不依赖本机运行。

- `pages.yml`：构建并发布前端。
- `collect.yml`：运行采集任务并更新数据分支。灯塔、酷云按分钟检查，其他来源每 15 分钟采集。
- 页面每分钟读取最新快照。受 GitHub Actions 调度、网络和平台限制影响，更新可能延迟，以各项统计时间为准。

公开版本仅提供全景看板与平台详情。部署、历史恢复及来源限制见 [docs/github-deployment.md](docs/github-deployment.md)。

## 本地启动

技术栈：React / TypeScript / ECharts / FastAPI / SQLite。需要 Python 3.12、Node.js 20+。

Windows PowerShell：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\start.ps1
```

脚本安装依赖并启动前后端，访问 http://127.0.0.1:5173 。默认仅监听本机。

依赖安装完成后，可用 `./start-background.ps1` 启动隐藏的本地采集进程，日志位于 `backend/logs/`。采集使用 HTTP 接口或项目独立的无界面 Chromium，不需要保持日常 Chrome 或看板页面打开。本机关闭或休眠期间无法持续采集。

## 数据与会话

灯塔、酷云等数据按本剧名称核验后入库。百度指数读取关键词搜索趋势，不混入资讯指数或品牌搜索指数。云合优先使用官方小程序接口，失败时回退官网榜单。灯塔接入与字段说明见 [docs/dengta-data-access.md](docs/dengta-data-access.md)。

本地会话与凭据保存在 `backend/local-secrets/`、`backend/browser-profiles/`，不提交到公开仓库。需要登录的平台在 Actions 环境可能无法取得新数据，此时保留历史读数及原统计日期。

备份本地数据时先停止后端，再复制 `backend/data.db`。原始响应保存在 `backend/evidence/`，与公开快照分开保存。

## 本剧数据接口

- `GET /api/overview`：本剧总览。
- `GET /api/sources`：来源状态与指标。
- `GET /api/series?source=weibo&hours=168`：历史序列。
- `GET /api/dengta/daily`：灯塔官方逐日播放量与市占。
- `POST /api/refresh`：触发采集。
- `POST /api/sources/{source}/refresh`：刷新指定来源。
- `GET /api/health`：健康检查。

以上是本地 FastAPI 接口；GitHub Pages 从公开数据快照读取对应内容。

## 开发检查

```powershell
python -m unittest discover -s backend -p 'test_*.py' -v
cd frontend
npm run build
```
