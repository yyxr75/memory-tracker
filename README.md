# 📊 行业追踪器 — 部署指南

从零开始,15 分钟把这个系统跑起来。完全免费。

---

## 🎯 你将得到什么

- ✅ 每个工作日早上 7:30(布里斯班时间)收到一封邮件
- ✅ 覆盖 **存储芯片 / 商业航天 / 电力电网** 三大板块，共 20 只标的
- ✅ 每只股票的当日涨跌、月度走势、PE 估值
- ✅ 三板块相关新闻摘要(过去 24 小时)
- ✅ 智能警报(单日波动 >5% 等异常)+ DeepSeek AI 今日观点
- ✅ 每周日早上有更深度的周报 + 动态思考清单
- ✅ **完全免费,完全自动化**

### 💾 存储芯片

| 代码 | 名称 | 类型 |
|------|------|------|
| MU | 美光 Micron | 存储原厂 |
| 005930.KS | 三星电子 Samsung | 存储原厂 |
| 000660.KS | SK海力士 SK Hynix | 存储原厂 |
| TSM | 台积电 TSMC | 代工/封装 |
| ASML | 阿斯麦 ASML | 半导体设备 |
| AMAT | 应用材料 Applied Materials | 半导体设备 |
| NVDA | 英伟达 NVIDIA | 客户端(GPU) |
| AMD | AMD | 客户端(GPU) |
| SOXX | iShares 半导体ETF | 行业指数 |
| SMH | VanEck 半导体ETF | 行业指数 |

### 🚀 商业航天

| 代码 | 名称 | 类型 |
|------|------|------|
| RKLB | 火箭实验室 Rocket Lab | 运载火箭 |
| ASTS | AST SpaceMobile | 卫星互联网 |
| LUNR | Intuitive Machines | 月球探索 |
| PL | Planet Labs | 卫星遥感 |
| UFO | Procure 太空ETF | 行业指数 |

### ⚡ 电力电网

| 代码 | 名称 | 类型 |
|------|------|------|
| GEV | GE Vernova | 电力设备 |
| PWR | Quanta Services | 电网基建 |
| AMSC | 美国超导 AMSC | 电网技术 |
| NEE | NextEra Energy | 新能源公用事业 |
| GRID | First Trust 智能电网ETF | 行业指数 |

---

## 📋 准备工作 (5 分钟)

### 1. 准备一个 Gmail 账号

如果你已经有 Gmail,跳过这步。

**注意**:不要用你的主邮箱密码!Google 不允许 SMTP 直接用主密码,我们要用"应用专用密码"。

### 2. 启用 Gmail 的"应用专用密码"

1. 打开 https://myaccount.google.com/security
2. 找到 **"两步验证"** — 必须先打开两步验证,否则无法生成应用密码
3. 进入两步验证设置后,滚动到底部找到 **"应用密码"** (App passwords)
4. 直接访问也可以:https://myaccount.google.com/apppasswords
5. 选择应用 "邮件",设备 "其他",名称写 "Memory Tracker"
6. 点击生成,**会得到一个 16 位的密码**,形如 `abcd efgh ijkl mnop`
7. **把这串密码保存下来**(去掉空格,变成 `abcdefghijklmnop`)— 我们等下要用

### 3. 准备一个 GitHub 账号

如果没有,去 https://github.com 注册一个,免费。

---

## 🚀 部署步骤 (10 分钟)

### 步骤 1:创建 GitHub 仓库

1. 登录 GitHub,点击右上角 **"+" → "New repository"**
2. 仓库名:`memory-tracker`(随便起,但建议这个)
3. **重要**:选择 **Public**(公开仓库才能免费使用 GitHub Actions 的全部时长)
4. 不要勾选 README、.gitignore 等任何选项
5. 点击 **"Create repository"**

### 步骤 2:上传代码

最简单的方法是在网页上直接上传:

1. 在新创建的仓库页面,点击 **"uploading an existing file"** 链接
2. 把以下 3 个文件拖进去:
   - `tracker.py`
   - `requirements.txt`
   - `.github/workflows/tracker.yml` (注意路径!)

**关于 `.github/workflows/tracker.yml` 这个路径**:
- 直接在网页上,把 `tracker.yml` 文件名改成 `.github/workflows/tracker.yml`,GitHub 会自动创建文件夹
- 或者用 Git 命令行(如果你会的话)

3. 在底部点击 **"Commit changes"**

### 步骤 3:配置 GitHub Secrets(关键!)

这是把你的邮箱密码安全地告诉 GitHub。

1. 在你的仓库页面,点击 **"Settings"**(顶部菜单)
2. 左侧栏点击 **"Secrets and variables" → "Actions"**
3. 点击 **"New repository secret"**,依次添加 3 个 secret:

| Name | Value |
|------|-------|
| `EMAIL_USER` | 你的 Gmail 地址,如 `youremail@gmail.com` |
| `EMAIL_PASSWORD` | 步骤 2 生成的 16 位应用密码,**去掉空格** |
| `EMAIL_TO` | 收件邮箱(可以和发件相同) |

**(可选)** 如果你用的不是 Gmail,还要加:
- `SMTP_SERVER`:如 QQ 邮箱用 `smtp.qq.com`、Outlook 用 `smtp.office365.com`
- `SMTP_PORT`:通常是 `587`

### 步骤 4:测试运行

1. 在仓库页面点击 **"Actions"** 标签
2. 如果提示需要启用 Actions,点击 **"I understand my workflows, go ahead and enable them"**
3. 左侧栏选择 **"📊 存储芯片追踪器"**
4. 右侧点击 **"Run workflow"** 按钮
5. 模式选 `daily`,点击绿色的 **"Run workflow"**
6. 等待 2-3 分钟,刷新页面会看到运行结果

如果是绿色 ✅ — 恭喜!打开邮箱看邮件。

如果是红色 ❌ — 点击进去看错误日志,常见问题在下方"故障排查"。

---

## ⏰ 自动运行时间表

部署成功后,系统会自动:

| 日子 | 时间(布里斯班) | 报告类型 |
|------|------------------|---------|
| 周一到周五 | 早上 7:30 | 每日早报 |
| 周日 | 早上 9:00 | 周末深度报告 |

不需要你做任何事,邮件会自动送达。

**注意**:GitHub Actions 的定时任务有时会延迟 5-15 分钟,这是正常的。

---

## 🛠️ 常见问题 / 故障排查

### Q1: 邮件没收到?

1. 先检查垃圾邮件文件夹
2. 在 Actions 页面查看运行日志,看是否有 "✅ 邮件已发送" 的提示
3. 如果显示 "邮件发送失败:Username and Password not accepted":
   - 确认你用的是**应用密码**,不是 Gmail 登录密码
   - 确认应用密码去掉了空格
   - 确认 Gmail 账号开启了两步验证

### Q2: 想换收件邮箱?

去 Settings → Secrets → Actions,编辑 `EMAIL_TO` 这个 secret。

### Q3: 想加更多股票?

打开 `tracker.py`,找到顶部的 `TICKERS = { ... }` 字典,按相同格式添加。

举例,要加铠侠(在东京上市)和西部数据:
```python
"285A.T": {"name": "铠侠 Kioxia", "category": "存储原厂"},
"WDC":    {"name": "西部数据 WD", "category": "存储原厂"},
```

提交修改,下次自动运行就会包含新股票。

### Q4: 想改运行时间?

打开 `.github/workflows/tracker.yml`,找到 `cron` 行:
```yaml
- cron: '30 21 * * 0-4'  # 改这里
```

格式是 `分 时 日 月 星期`,**注意是 UTC 时间**(布里斯班 UTC+10)。

举例,想改成布里斯班早上 6:00 → UTC 前一天 20:00:
```yaml
- cron: '0 20 * * 0-4'
```

### Q5: 想用 QQ 邮箱发?

可以。QQ 邮箱需要:
1. 进入 QQ 邮箱 → 设置 → 账户 → 开启 SMTP 服务
2. 生成授权码(类似 Gmail 的应用密码)
3. 在 GitHub Secrets 添加:
   - `EMAIL_USER`: 你的 QQ 邮箱
   - `EMAIL_PASSWORD`: 授权码
   - `SMTP_SERVER`: `smtp.qq.com`
   - `SMTP_PORT`: `465`(QQ 用 465,不是 587)

**注意**:QQ 邮箱用 465 端口的话,Python 代码需要把 `starttls()` 改成 SSL 模式。如果你需要用 QQ 邮箱,告诉我,我帮你改代码。

---

## 💰 真的免费吗?

是的。

GitHub Actions 对**公开仓库**完全免费,无限制。

私有仓库每月有 2000 分钟免费额度。这个脚本一次运行约 1 分钟,一天最多用 2 分钟,一个月 60 分钟,远低于 2000 分钟。

总结:**只要仓库公开,完全免费,永远免费**。

不放心代码公开?里面没有任何敏感信息,密码全部存在 Secrets 里,不会泄露。

---

## 🎁 进阶玩法：接入 DeepSeek AI（可选）

代码已内置 DeepSeek API 集成，只需添加一个 Secret 即可激活：

1. 在 https://platform.deepseek.com 注册并创建 API key
2. 在 GitHub Secrets 添加 `DEEPSEEK_API_KEY`（Value 填你的 key）

激活后，报告会自动新增两项智能内容：

| 功能 | 说明 |
|------|------|
| **AI 今日观点** | 每日报告中，DeepSeek 根据当天行情和新闻生成 3-4 句中文分析 |
| **动态思考清单** | 周报中的 5 个问题不再是固定的，而是引用本周具体涨跌数据和新闻 |

即使不添加 API key，周报也会用纯 Python 规则生成一份动态清单（引用实际涨幅数据），不会退回到静态文案。

---

## ✨ 完成!

享受你的全自动追踪系统吧。

有任何问题,直接问我。
