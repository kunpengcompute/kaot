# KAOT WebUI

KAOT（Kunpeng Ascend Optimization Tool）的可视化调优界面，提供场景选择、调优项执行、配置文件管理等功能。

## 核心特性

### 可视化调优
- 清晰的场景卡片展示
- 调优项列表与参数表单

### 执行管理
- 异步任务执行
- 实时日志流输出
- 任务中止功能
- 状态持久化与恢复

### 配置管理
- 配置文件查看/编辑
- 基线配置生成
- 一键执行配置

### 加速库管理
- BoostKit加速库安装/卸载
- 毕昇JDK Fusion安装/卸载

## 快速启动

```bash
cd webui
bash launcher.sh 8080
```

或直接使用Python：

```bash
cd webui
python3 app.py --port 8080
```

启动后访问：`http://服务器IP:8080`

### 启动参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| --port | 8080 | 服务端口 |
| --host | 0.0.0.0 | 绑定地址 |
| --debug | false | 调试模式 |

## 依赖

```bash
pip3 install flask pyyaml
```

（pyyaml已在KAOT主项目依赖中）

## 支持的场景

| 场景 | 名称 | 调优项数 | 说明 |
|------|------|----------|------|
| common | 通用场景 | 5 | CPU性能、Swap、超线程等 |
| boundary_gateway_appliance | 边界网关一体机 | 10 | 大页内存、核隔离、中断平衡等 |
| kingbase_database | 金仓数据库 | 4 | 数据库参数优化、IO调度 |
| opengauss_database | openGauss数据库 | 2 | 数据库参数优化 |

## 使用流程

### 1. 选择调优场景
首页展示4个场景卡片，点击选择进入调优项列表。

### 2. 查看调优项
左侧显示调优项列表，包含参数提示、是否需要重启等信息。

### 3. 执行调优
- 点击「配置执行」进入参数填写页面
- 填写必要参数
- 点击「生成配置并执行」
- 查看实时日志

### 4. 配置文件管理
- 在「配置」页面查看生成的YAML文件
- 可编辑、删除、直接执行配置文件

### 5. 加速库管理
- 在「加速库」页面安装/卸载BoostKit加速库

## 目录结构

```
webui/
├── app.py                   # Flask应用入口
├── runner.py                # KAOT执行引擎
├── webui_config.yaml        # WebUI配置文件
├── launcher.sh              # 启动脚本
├── templates/               # Jinja2模板
│   ├── base.html            # 基础模板
│   ├── index.html           # 首页
│   ├── scenario.html        # 场景页
│   ├── feature.html         # 调优项执行页
│   ├── tasks.html           # 任务列表
│   ├── logs.html            # 日志详情
│   ├── config.html          # 配置文件列表
│   ├── config_detail.html   # 配置文件详情
│   ├── library.html         # 加速库列表
│   ├── library_detail.html  # 加速库安装页
│   └── error.html           # 错误页
├── static/
│   ├── style.css            # 深色主题样式
│   └ app.js                 # 前端交互逻辑
└── logs/                    # 任务日志目录
```

## API接口

| 路径 | 方法 | 说明 |
|------|------|------|
| `/api/scenarios` | GET | 获取所有场景 |
| `/api/features/<scenario>` | GET | 获取场景下的调优项 |
| `/api/feature/<scenario>/<name>` | GET | 获取调优项详情 |
| `/api/generate` | POST | 生成配置文件 |
| `/api/execute` | POST | 执行调优配置 |
| `/api/basecfg` | POST | 生成基线配置 |
| `/api/install` | POST | 安装加速库 |
| `/api/uninstall` | POST | 卸载加速库 |
| `/api/tasks` | GET | 获取任务列表 |
| `/api/logs/<task_id>` | GET | 实时日志增量读取 |
| `/api/kill/<task_id>` | POST | 中止任务 |
| `/api/config/files` | GET | 获取配置文件列表 |
| `/api/config/<filename>` | GET/PUT/DELETE | 配置文件操作 |
| `/api/libraries` | GET | 获取加速库列表 |
| `/api/health` | GET | 健康检查 |

### 执行API示例

```bash
curl -X POST http://localhost:8080/api/generate \
  -H "Content-Type: application/json" \
  -d '{
    "scenario": "common",
    "features": ["disable_swap", "enable_cpu_performance_mode"],
    "output_file": "feature_config.yaml"
  }'
```

返回：
```json
{
  "task_id": "task_1234567890_1",
  "status": "started",
  "message": "任务已启动"
}
```

## 执行流程

1. 用户选择场景/调优项，填写参数
2. WebUI调用KAOT CLI命令（generate/execute）
3. 命令在独立进程组中运行（不受WebUI退出影响）
4. 日志实时写入，前端增量读取展示
5. 执行完成更新状态

## 状态持久化

- 任务状态保存到 `logs/*.status.json`
- WebUI重启时自动恢复运行中的任务
- 进程意外终止自动检测并更新状态

## 注意事项

1. **执行权限**：调优操作需要root权限执行
2. **重启提醒**：部分调优项（如CPU性能模式、大页内存）需要重启生效
3. **数据库场景**：需要提供数据库配置文件路径
4. **加速库安装**：需手动下载安装包后指定目录路径
5. **端口占用**：默认8080端口，如被占用请指定其他端口
6. **生命周期管理**：请在完成调优操作后，立即手动终止WebUI程序，避免不必要的资源占用与安全风险。
7. **环境限制**：WebUI不建议且不支持在生产环境中使用，请仅在受信任的开发或测试环境中运行
8. **BETA版本特性**：当前WebUI为beta版本特性，如您在使用过程遇到问题，请提ISSUE反馈


## 故障排除

### Flask启动失败
```bash
pip3 install flask --upgrade
```

### YAML解析错误
```bash
pip3 install pyyaml --upgrade
```

### 权限问题
```bash
chmod +x webui/launcher.sh webui/app.py webui/runner.py
```

### 进程无法中止
```bash
ps aux | grep kaot.py
kill -9 <PID>
```
