# YTMetrics

YTMetrics 是一个基于 Streamlit 的 YouTube 频道分析工具，面向“筛选和评估香港美食类 YouTuber”这一实际业务场景。

它的目标不是做通用数据仓库，而是让运营、商务或研究同学输入一批频道链接后，快速得到一份可直接用于合作判断的频道画像，包括频道体量、近期互动、内容品类、评论情感和 AI 合作建议。

这个仓库保存的是应用源码、启动脚本和交付辅助脚本；日志、缓存、离线交付包和运行时产物不会纳入版本库。

## 这个项目能做什么

- 批量读取 YouTube 频道 URL、`@handle`、`channel ID` 或 CSV 列表
- 拉取频道基础数据、最近视频列表和近期互动表现
- 识别频道近期内容覆盖的美食类型
- 可选抓取评论并做情感分析
- 基于频道数据生成 AI 合作建议
- 在网络受限时，通过代理检测与部分 fallback 机制尽量保持可用

## 功能

输入一组 YouTube 频道（URL / @handle / Channel ID），看板展示：

- **博主 ID / 频道名**
- **视频数 / 订阅数 / 总观看量**
- **近 7 天 / 30 天视频互动量**（点赞 + 评论汇总；窗口内无新视频时自动回退到点赞最高的单条视频）
- **涉及美食类型**（基于 15 类港式美食关键词从最近视频标题中识别）
- **评论情感摘要**（可选，依赖百度 NLP 配置）
- **AI 合作建议**（可选，依赖 DeepSeek/OpenAI 兼容接口）

## 适用场景

- 商务团队初筛一批潜在合作的香港美食博主
- 研究团队快速比较多个频道最近的活跃度和互动水平
- 运营团队基于评论情绪和内容方向判断合作风险
- 交付给客户作为轻量级本地分析看板

## 文件结构

```
YTMetrics/
├── YTMetrics.py                # Streamlit 入口（显式调用 main，保证 rerun 时重新渲染）
├── YTMetrics_网页框架.py        # 页面流程、交互、分析状态展示和看板渲染
├── YTMetrics_基础数据.py        # 频道解析、数据抓取、聚合逻辑
├── YTMetrics_AI建议.py          # AI 建议生成
├── ytmetrics_sentiment_core.py # 评论抓取与情感分析核心
├── ytmetrics_youtube_client.py # YouTube Data API 客户端
├── ytmetrics_youtube_fallback.py
├── ytmetrics_network.py
├── requirements.txt            # Python 依赖
├── run.sh                      # 启动脚本
├── .env.example                # 环境变量模板
├── .env                        # 实际 API key（不要提交 git，已在 .gitignore）
└── README.md
```

## 准备工作

### 1. 获取 YouTube Data API key（免费）

1. 打开 [Google Cloud Console](https://console.cloud.google.com/)，新建或选择一个项目
2. APIs & Services → Library → 搜 **YouTube Data API v3** → Enable
3. APIs & Services → Credentials → Create Credentials → API key
4. **建议**：点 API key → Edit → Application restrictions 选 IP/Referrer；API restrictions 仅勾 YouTube Data API v3

默认 quota 10,000 units/天，足够分析几十个频道。

### 2. 配置 .env

```bash
cp .env.example .env
# 编辑 .env，把 YOUTUBE_API_KEY=... 填上真实 key
```

最小必需配置：

- `YOUTUBE_API_KEY`

可选配置：

- `DEEPSEEK_API_KEY` 或 `OPENAI_API_KEY`：启用 AI 合作建议
- `BAIDU_APP_ID` / `BAIDU_API_KEY` / `BAIDU_SECRET_KEY`：启用评论情感分析
- `YTMETRICS_USE_ENV_PROXY` / `YTMETRICS_SOCKS_PROXY`：控制代理

如果不配置 `YOUTUBE_API_KEY`，应用仍可启动，但会使用内置 mock 示例数据。

## 安装与启动

### 方式一：用 run.sh（推荐）

```bash
pip install -r requirements.txt
chmod +x run.sh
./run.sh
```

可选环境变量：
- `PORT`（默认 8501）
- `HOST`（默认 0.0.0.0）

例如：`PORT=8888 ./run.sh`

### 方式二：直接调用 streamlit

```bash
pip install -r requirements.txt
streamlit run YTMetrics.py
```

启动后访问 http://localhost:8501

如果部署在云服务器（如 AWS EC2），记得在 Security Group 放行对应端口。

## 使用步骤

1. 打开首页，确认顶部提示 `✅ 检测到 YOUTUBE_API_KEY`（否则会使用 mock 数据）
2. **粘贴频道列表** Tab：
   - 点 **🍜 Load HK food example** 一键填入 6 个真实港食 YouTuber
   - 或自行粘贴 channel URL / @handle / channel ID，每行一条
3. **上传 CSV** Tab：上传含 `channel` 列（URL/@handle/ID）的 CSV
4. 点 **Analyze** → 跳转看板
5. 看板顶部：所有频道的汇总表，可点 ⬇️ Download CSV 导出
6. 看板下方：每个频道可展开查看明细（含最近视频列表）

## 频道输入支持的格式

- `https://www.youtube.com/@handle`
- `@handle`
- `https://www.youtube.com/channel/UCxxx...`
- `UCxxx...`（24 位 channel ID）
- `https://www.youtube.com/c/customname` 或 `/user/name`

## 美食类型识别

代码内置 15 类港式美食关键词（茶餐廳、點心、燒臘、火鍋、海鮮、甜品、麵食、街頭小食、日式、西餐、中菜、韓式、東南亞、Cafe、飲品），从最近 20 条视频的标题里命中关键词。要扩展类别，编辑 `YTMetrics.py` 顶部的 `HK_FOOD_TYPES` 字典即可。

## API 配额估算

每分析一个频道大约消耗 3 quota units：
- `channels.list` × 1（含 statistics、contentDetails）
- `playlistItems.list` × 1（最近 20 条视频）
- `videos.list` × 1（视频统计）

若用户输入的是 handle 而非 channel ID，会额外消耗 1 unit 做解析。日 quota 10k = 约 3,000 个频道的余量。

## 故障排查

| 现象 | 处理 |
|---|---|
| 顶部显示 `⚠️ 未设置 YOUTUBE_API_KEY` | 确认 `.env` 在 `YTMetrics.py` 同目录且格式正确 |
| `quotaExceeded` 错误 | 等 24 小时重置，或在 Console 申请提额 |
| 中文 handle 解析失败 | YouTube 内部不一定有 ASCII handle，建议用 channel ID 或 `@英文handle` |
| Streamlit 启动报 `Address already in use` | 改端口：`PORT=8502 ./run.sh` |

## Root Cause Notes

### 2026-05-15：`Analysis` 按钮后白屏 / 只有光标 / 没有流式状态

这次问题的**主根因不是 YouTube API，也不是代理配置**，而是 Streamlit 的 rerun 模型被错误使用了。

#### 根因 1：`YTMetrics.py` 只做了 `import *`，rerun 后页面主体根本不会重新执行

旧入口文件只有：

```python
from YTMetrics_网页框架 import *
```

第一次打开页面时，`YTMetrics_网页框架.py` 在导入阶段执行，所以界面能显示。

但 Streamlit 后续每一次交互都会触发 **script rerun**。这时 Python 会复用已缓存模块，`YTMetrics_网页框架.py` 不会因为 `import *` 再次执行，结果就是：

- 顶部 `Deploy / Main menu` 还在
- 主内容区不再重新生成
- 页面看起来像“白屏 / 空白 / 只有光标”

这就是这次白屏的**第一性根因**。

#### 根因 2：点击 `Analysis` 后又去改已实例化输入框的 session key

旧逻辑在 `yt_url_input` 文本框已经创建后，又执行：

```python
st.session_state.yt_url_input = url
```

这会触发 Streamlit 的 `StreamlitAPIException`：

```text
st.session_state.yt_url_input cannot be modified after the widget with key yt_url_input is instantiated
```

如果前端没有把异常明显显示出来，用户看到的也会像“点了按钮后页面空掉了”。

#### 根因 3：之前的全局任务表 / 背景线程方案不符合这个页面的稳定需求

之前尝试过把分析过程放到模块级全局任务表和后台线程里，再靠频繁 rerun 轮询状态。

这套方案的问题是：

- 状态来源分散
- UI 依赖多次 rerun 才能稳定展示
- 一旦页面 rerun 链路本身有问题，就会把“任务丢失 / 状态不显示 / 页面空白”混在一起

它不是最终白屏的唯一根因，但它确实让问题更难定位，也不适合作为这个页面的最终结构。

### 最终修复原则

1. `YTMetrics.py` 改为显式调用 `main()`，保证每次 rerun 都重新渲染页面。
2. 不再在 widget 创建后反向改写 `yt_url_input`。
3. `Analysis` 点击后在**同一次运行**里直接显示状态卡、进度条和步骤列表，分析完成后再切到 dashboard。
4. 优先使用“更笨但稳定”的 Streamlit 同步渲染流程，而不是复杂的任务轮询状态机。

### 后续开发注意事项

- Streamlit 页面入口不要只靠“导入时顺带执行”。
- 所有页面主体渲染都应该放进可重复调用的 `main()` 或等价入口函数。
- 不要在 widget 已实例化后再去直接改它的同 key `session_state`。
- 如果 UI 需要流式状态，先证明“同次运行内可稳定显示”，再考虑异步化。

## 安全提醒

- **不要把 `.env` 提交到 git**（已在 `.gitignore`）
- **不要把任何真实的百度 / OpenAI / DeepSeek 密钥写死进代码**
- 在 Cloud Console 给 API key 加 IP/Referrer 限制
- 若 key 不慎泄露，立即去 Console regenerate
