# 灯塔网播数据接入验证

验证日期：2026-11-11（北京时间）。目标是灯塔专业版 App 底部“网播/收视”，用于本项目的两部剧。

## 已验证的获取路线

官方 Android 安装包 → 内置页面路由 → 官方 H5 网播榜 → v3.0 JSON 接口。
后台已独立请求成功，不需要企业认证、用户账号 Cookie、手机连接或浏览器常开。

- 官方安装包：`https://appdownload.alicdn.com/publish/moviepro_android/latest/moviepro_android_10035099.apk`
- 包名：`com.alipictures.moviepro`；AndroidManifest 版本：8.3.2 / 83020。
- SHA256：`357d72c0decc20855c2f51508df2b9b7000d31832cb186dce080c0fb53d22e44`。
- 安装包的 `assets/router/scheme/config_online.json` 中，`onlineAndTVShow` 指向 `https://dengtapro.taopiaopiao.com/webcasts.html?pageRadiusColor=4884ff`。
- 页面脚本：`https://g.alicdn.com/alipic/beacon-pro/0.2.21/app-main/client/static/js/webcasts.html.js`。
- 配置接口：`mtop.alipictures.gravitywave.media.config.get`，版本 `3.0`。
- 榜单接口：`mtop.alipictures.gravitywave.media.rank.list`，版本 `3.0`。
- H5 地址：`https://acs.m.taopiaopiao.com/h5/mtop.alipictures.gravitywave.media.rank.list/3.0/`。

请求参数来自页面代码和配置接口：`configCode=1`（剧集）、`typeCode=12`（全部）、`platformCode=beaconmarketshare_play_vv`（正片播放）、`showDate=北京时间当天YYYYMMDD`、`dateType=0`、`isLoop=false`。

H5 首次请求由服务器设置匿名 `_m_h5_tk` Cookie，随后按官方 SDK 的请求校验格式重试。
Cookie 仅保留在单轮请求内存中，不写入日志、证据文件或来源链接。
这是网页内部接口，并非承诺兼容性或服务等级的公开开发者 API。

## 字段口径

| 原始字段 | 项目指标 | 转换 |
| --- | --- | --- |
| `vvCnt` | 当日正片播放量 | 原始次数，不用“万”的显示值反推 |
| `cnt` | 正片播放市占率 | 原始比例乘 100，单位 % |
| `mediaRank` | 正片播放排名 | 从 0 起，展示时加 1 |
| `modifiedTime` | 来源更新时间 | 北京时间；与采集时间分别保存 |

灯塔正片播放不能直接视作云合正片有效播放。当天指标跨日重新统计，图表按日分段，变化分析只计算最新统计日，不做跨日累计预测。

独立 HTTP 实测取得 30 条榜单，包含《今天是太阳雨》和《折月亮》。两轮响应的播放量与更新时间均发生变化，证明获取到可更新的榜单，而非固定截图。

## 接入与限制

- `backend/dengta_api.py` 每次请求一份榜单，同时更新两部剧。
- 服务运行时每分钟检查；平台自身更新节奏仍以 `modifiedTime` 为准。
- 图表固定按采集分钟对齐，不受其他平台15分钟等合并刻度影响；没有新记录的分钟不补值。平台更新时间可能不随数值同步变化，因此单独保留并在图表提示中展示，避免相同来源时间覆盖多次有效采样。
- 校验统计日、指标名称、数值范围、唯一剧名、排名和更新时间。来源时间超过两小时、日期不符、登录/限流错误不写入新数值，保留上次成功记录。
- 当前只接入“剧集 → 全部 → 正片播放”的三个指标。电视收视、其他视频平台榜单、集均播放尚未接入。
- 电视收视在当前包中使用 Flutter 页面 `tv_show_page_syntax`，发现接口 `mtop.alipictures.gravitywave.tvaudience.rating`，尚未完成实际响应验证。
- 来源证据保存于 `backend/evidence/`，只含榜单字段、公开参数、来源地址和采集时间。

## 已排除的错误路线

企业宣发网页要求公司认证，不能代表免费 App 的访问要求。
官方默认渠道 `moviepro_android_700125.apk` 本次仍返回 5.4.4；其中 v2.1 的 `beacon` 榜单成功响应可能停留在 2021-11-12，不能仅凭 SUCCESS 判断实时接通。

可复现静态分析：`python scripts/analyze_dengta_apk.py package.apk output_directory`。
该脚本不安装、不执行 APK；输出 Manifest、哈希、相关字符串和内置路由。


## 正片播放分时图

2026-11-11验证 `mtop.alipictures.gravitywave.media.vv.detail.list` v1.0，参数为 `mediaId=1514343`、`platform=ALL`、`dateType=HOUR`。`vvCnt` 为该完整小时的原始播放次数，`marketShare` 为带百分号的小时市占率。每分钟检查，分钟累计采集保持不变。

分时面板使用小时原值：今日蓝柱、昨日虚线、今日小时市占金线。SQLite `dengta_hourly` 按日期和小时保存并更新修订值，不覆盖此前日期。接口目前只返回当日已闭合小时；接入首日没有昨天分时档案，明确提示并不造数。未提供的23点时段也不以日累计倒推。昨日同时段差值只比较双方从零点开始连续具备数据的共同小时，缺口之后不计算。

## 官方全部逐日历史

已验证 `mtop.alipictures.gravitywave.media.vv.detail.list` v1.0，参数 `mediaId=1514343, platform=ALL, dateType=DAY`。2026-11-11 返回本剧自 11 月 6 日开播以来的 6 个统计日期。每日正片播放使用 `vvCnt`，市占使用 `marketShare` 百分数，不使用累计 `totalVv`。

后端每分钟随灯塔任务更新独立日档案，同日修订覆盖展示值并保存原始响应证据，失败保留历史与最后成功时间。详情“全部”按日展示官方历史，“今日”保留分钟采样；当日未结束的数值会持续更新。日历史不用于冒充昨日小时分布。
