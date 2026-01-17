文件职责：描述 Web UI 模块的目录结构与功能边界。
简明实现逻辑：以本地 HTTP 服务提供设置面板式配置编辑与运行入口。
输入输出：输入为浏览器请求；输出为配置内容与运行结果。

# Web 模块结构

```
web/
├── server.py     # 本地 Web 服务与 API
├── index.html    # Web UI 页面
├── app.js        # 前端交互逻辑
└── styles.css    # 页面样式
```

## 关键职责

- `server.py`: 提供静态文件服务与配置/运行 API
- `index.html`: 入口页面与布局结构
- `app.js`: 渲染设置面板、加载/保存配置与触发运行
- `styles.css`: UI 视觉风格与响应式布局

## 核心逻辑说明

### 静态资源

- `GET /` 返回 `index.html`
- `GET /app.js` 返回前端脚本
- `GET /styles.css` 返回样式

### 配置编辑 API

- `GET /api/configs`：返回可编辑配置列表（基础配置 + personas 目录）
- `GET /api/config?id=<id>`：读取指定配置内容
- `POST /api/config?id=<id>`：保存配置内容，写入前校验 JSON 并转换为 TOML

### 人设新增

- `POST /api/persona`：新增人设文件（文件名需符合 `A-Za-z0-9_-`）
- 人设目录固定为 `data/personas/`（Web UI 当前不管理 `data/worlds/` 下的人设）
- Web UI 通过“新建人设”创建空白人设并进入编辑

### 运行入口

- `POST /api/run`：运行 `main.py --run-seconds <n>`（读取 `config/app_config.toml` 作为基础配置）
- 运行时长与输出均有上限，避免阻塞与过量输出
- 运行结束时 `main.py` 会自动写入“运行日志（控制台输出副本）”到 `data/worlds/<world_id>/saves/`（或回退到 `data/saves/`）

### UI 编辑模型

- 表单化编辑应用配置、LLM、Persona、Knowledge Graph 配置
- 不直接暴露可编辑的原始 TOML（只提供只读预览）

### 安全与限制

- 仅允许白名单内的 TOML 文件被读取/写入
- 运行超时会被终止并返回超时提示

### 启动方式

- `python main.py --webui`
- `python web/server.py`
