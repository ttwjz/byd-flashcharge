# BYD Flash Charge Station Tracker ⚡

每日追踪比亚迪全国闪充站部署进度，自动采集、地理编码、可视化。

## 功能特性

- **全国扫描** — 289 城市中心 + 1424 偏移点 + 3570 网格点，覆盖全部中国领土
- **自动重试** — SSL/连接/超时错误自动重试 3 次（指数退避），零失败率
- **双模式地理编码** — 高德 API 优先，额度耗尽自动切换离线 PiP（shapely + GeoJSON）
- **数据库缓存** — 已编码站点不会重复请求，支持中断恢复
- **三级地图下钻** — 全国 → 省 → 市，点击放大，逐级查看站点分布
- **暗色仪表盘** — 站点总数、覆盖城市、增长趋势、城市排行
- **双部署模式** — Flask 本地开发 / Cloudflare Pages 静态部署

## 安装

```bash
pip install requests flask shapely
```

地理编码需要高德 API Key（免费申请，5000 次/天）：
```bash
export AMAP_API_KEY=your_key_here
```

## 使用

### 1. 下载省级地图数据（首次）
```bash
python download_maps.py
```

### 2. 抓取数据 + 地理编码
```bash
python scraper.py
```
扫描全国约 25-35 分钟（含重试），地理编码约 4 分钟。

### 3. 启动网页
```bash
python web_server.py
```
打开 http://localhost:5000 查看数据面板。

### 4. 每日定时抓取（可选）
```bash
# Linux crontab: 每天凌晨 3 点执行
0 3 * * * cd /path/to/byd-flashcharge && bash deploy.sh
```

## 架构

```
数据采集                    地理编码                    可视化
┌──────────┐    ┌───────────────────────┐    ┌──────────────┐
│ BYD API  │───→│ 高德 API (主)         │───→│ Flask / 静态 │
│ 289 城市 │    │ 离线 PiP (备)         │    │ ECharts 地图 │
│ 3570 网格│    │ shapely + GeoJSON     │    │ Chart.js 图表│
└──────────┘    └───────────────────────┘    └──────────────┘
     ↓                    ↓                        ↑
   SQLite ─────── province / city ──────── JSON API
```

## 文件说明

```
byd-flashcharge/
├── config.py              # API 配置、全国网格点生成
├── scraper.py             # 数据抓取（三阶段扫描 + 自动重试）
├── geocoder.py            # 双模式地理编码（高德 API + 离线 PiP）
├── database.py            # SQLite 数据库（stations/snapshots/summary）
├── cities.py              # 289 个城市坐标 + 城市名/区县映射表
├── web_server.py          # Flask Web 服务
├── export_json.py         # 导出静态 JSON（Cloudflare Pages 部署用）
├── download_maps.py       # 下载 34 省 GeoJSON（地图下钻 + PiP 共用）
├── deploy.sh              # 自动化部署脚本（抓取→导出→git push）
├── templates/
│   └── index.html         # Flask 版前端
├── public/                # Cloudflare Pages 静态站
│   ├── index.html         # 静态版前端
│   ├── api/*.json         # 导出的 JSON 数据
│   └── static/maps/       # 省级 GeoJSON（34 省 + 全国）
├── static/                # Flask 静态资源
│   ├── echarts.min.js     # ECharts 5.6.1
│   ├── chart.js           # Chart.js
│   ├── china.js           # 中国地图 GeoJSON
│   └── maps -> ../public/static/maps/  # 符号链接
└── data/                  # 运行时数据（自动创建）
    ├── stations.db        # SQLite 数据库
    ├── raw_YYYY-MM-DD.json
    └── scraper.log
```

## 数据面板

- 📊 站点总数、闪充桩总数、覆盖城市数、今日新增
- 🗺️ 全国站点散点地图（支持三级下钻：全国→省→市）
- 📈 站点增长趋势 + 每日新增柱状图
- 🏙️ 城市站点排行（可搜索、可排序）

## 本次改动（dev 分支）

### 新增功能
- **双模式地理编码**：高德 API 为主，离线 PiP 为后备，站点 100% 归属到省/市
- **三级地图下钻**：点击省份进入省级视图，点击城市进入市级视图，显示区县边界
- **请求重试机制**：SSL/连接/超时错误自动重试 3 次，指数退避，消除瞬态错误
- **全国网格覆盖**：从 1667 点扩展到 3570 点，覆盖新疆、西藏、内蒙古全境

### 修复
- 修复 stations 表缺少 `city` 列导致的崩溃
- 修复 `data/` 目录不存在时日志初始化失败
- 站点省/市判断从不可靠的名称解析改为坐标地理编码

### 数据库变更
- stations 表新增 `province TEXT`、`geocoded INTEGER DEFAULT 0` 列
- 地理编码结果作为缓存持久化，重复运行不会重新请求
