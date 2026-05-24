# 彩票分析工具

福彩 3D / 排列三智能分析与推荐系统，基于 Python 后端 + 纯前端静态页面。

## 项目结构

```
lottery-tool/
├── backend_python/           # 后端
│   ├── smart_analyze.py      # 核心分析引擎（杀码/热度/组三/趋势/反馈修正）
│   ├── analyze_today.py      # 早期分析脚本（确定性 PRNG 算法）
│   ├── backtest.py           # 回测框架
│   ├── app.py                # Flask API 服务器
│   ├── params.json           # 分析参数（自动调参）
│   ├── feedback_log.json     # 反馈日志（历史开奖 vs 预测记录）
│   ├── requirements.txt      # Python 依赖
│   └── data/
│       ├── 3d.json           # 福彩 3D 历史开奖数据
│       └── pl3.json          # 排列三历史开奖数据
│
├── frontend/                 # 前端
    ├── index.html            # 主页面（三页结构：走势 / 推荐 / 统计）
    ├── style.css             # 样式（Apple 风浅色主题）
    ├── script.js             # 前端交互逻辑
    └── api.js                # 后端 API 调用封装
```

## 核心功能

### 智能分析引擎 (`smart_analyze.py`)

- **杀码**：基于加权频率 + 遗漏期的冷度模型，排除冷号
- **热度评分**：综合频率（60%）+ 近期程度（40%）
- **组三推荐**：组三占比 ≥15% 时自动触发，生成对子候选
- **趋势分析**：和值奇偶 + 单双比分布，均值回归偏向
- **反馈修正**：开奖后自动对比预测，调整参数（衰减率/冷度权重/趋势权重等）
- **多样性过滤**：避免推荐号码过度重叠

### 前端

- **三页结构**：走势浏览 / 精选推荐 / 数据统计
- **清新浅色**：Apple 风格设计，白色卡片 + 微阴影
- **SVG 图标**：底部导航栏线性图标，与风格统一
- **双杀码**：顶部常驻显示当日杀码
- **自动降级**：后端未连接时回退到本地算法

## 启动项目

```bash
cd backend_python
pip install -r requirements.txt
python app.py
```

浏览器打开 `http://127.0.0.1:5000`

## 命令行用法

```bash
cd backend_python

# 每日分析
python smart_analyze.py analyze

# 录入开奖结果（追加数据 + 自动修正参数）
python smart_analyze.py update 3d 654
python smart_analyze.py update pl3 515

# 查看累计统计
python smart_analyze.py stats
```

## 更新数据

直接在 `backend_python/data/3d.json` 或 `pl3.json` 中追加新期号即可，格式：
```json
{"issue": "2026135", "number": "123", "date": "2026-05-25"}
```
