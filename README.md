# Garmin 游泳活动解析器

解析 Garmin 导出的 `.fit` 游泳活动文件，并在 Vue 页面中展示数据。

## 项目结构

```
garmin/
├── Lunch_Swim.fit          # 示例游泳活动文件
├── backend/                # Python FastAPI 后端
│   ├── main.py
│   ├── parser.py
│   └── requirements.txt
└── frontend/               # Vue 3 前端
    └── src/
        ├── App.vue
        └── components/
```

## 启动方式

### 1. 启动后端

```bash
cd backend
python3 -m pip install -r requirements.txt
python3 -m uvicorn main:app --reload --port 8000
```

后端会自动扫描项目根目录下所有 `.fit` 文件。

### 2. 启动前端

```bash
cd frontend
npm install
npm run dev
```

浏览器访问 http://localhost:5173

## Docker 部署

前后端打包为单一镜像，对外暴露 **8080** 端口：

```bash
# 构建并启动（数据持久化在 Docker volume）
docker compose up -d --build

# 或手动构建运行，挂载本地目录存放 .fit 文件
docker build -t garmin-swim .
docker run -d --name garmin-swim -p 8080:8080 -v "$(pwd)/data:/data" garmin-swim
```

浏览器访问 http://localhost:8080

上传的 `.fit` 文件默认保存在容器内 `/data` 目录，可通过环境变量 `GARMIN_DATA_DIR` 修改。

### 数据库（Strava 登录）

```bash
cd backend
python3 -m pip install -r requirements.txt
python3 init_db.py
```

默认 SQLite 路径：`{GARMIN_DATA_DIR}/garmin.db`，可通过 `DATABASE_URL` 覆盖。

| 表 | 说明 |
|----|------|
| `users` | 应用用户（昵称、头像等） |
| `strava_accounts` | Strava 绑定与 OAuth token（`athlete_id`、access/refresh token） |

## 功能

- 自动扫描项目根目录所有 `.fit` 游泳活动，左侧展示活动列表
- 点击活动查看详情，支持上传新的 `.fit` 文件到目录
- 展示活动摘要：距离、时间、卡路里、心率、配速等
- 分段（Lap）明细表，区分游泳段与休息段
- 趟数（Length）明细表
- 心率曲线图

## API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查 |
| GET | `/api/activities` | 扫描目录，返回活动列表 |
| GET | `/api/activities/{filename}` | 解析指定 FIT 文件 |
| GET | `/api/activity` | 解析最新一条活动（兼容） |
| POST | `/api/activity/upload` | 上传 FIT 文件到目录并解析 |
