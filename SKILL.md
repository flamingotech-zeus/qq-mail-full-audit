---
name: qq-mail-full-audit
description: 对 QQ 邮箱做全维度核查（MCP/IMAP/POP3 三通道交叉验证 + 5 个文件夹 × 已读未读全覆盖），突破 qq-mail MCP 连接器的 30 天/4 文件夹限制。当用户要求"检查邮箱未读""把邮箱所有未读都看一遍""全量维度都要检查""QQ邮箱有多少未读""邮箱里有什么重要邮件/待办"，或需要绕过 MCP 接口取不到历史邮件时使用。含三条通道的真实边界实测结论、modified-UTF-7 编解码、只读拉取（不标记已读）脚本与 8 条踩坑清单。
agent_created: true
---

# QQ 邮箱 IMAP 全量未读核查

把 QQ 邮箱翻到底、不漏邮件的标准流程。核心价值：**先测边界，再下结论**，避免"我查完了"其实只查了 5% 还信誓旦旦。

## 一、开场必做：先确认交付边界（别急着说"查完了"）

用户常在手机/网页看到"未读 380+"，而第三方接口只能拿到几十封。**差额不是 bug，是协议限制**。动手前先明确：

1. 用户看到的未读数是在哪看到的？（网页版首页 / 手机 App 角标 / 收件箱内）
2. 有没有开通 IMAP 授权码？

## 二、QQ 邮箱的三条硬边界（2026-09 实测）

| 边界 | 实测结论 |
|---|---|
| 文件夹白名单 | **只暴露 5 个**：`INBOX`、`Junk`、`Drafts`、`"Sent Messages"`、`"Deleted Messages"`，外加一个常为空的 `其他文件夹/QQ邮件订阅` |
| 拿不到的文件夹 | **「广告邮件」「订阅邮件」在协议层根本不存在** —— 用 modified-UTF-7 编码后硬试 12 组候选名，服务器明确回 `NO Folder not exist!`。这正是"未读 380+ 却只能拿到 73"的原因 |
| 时间窗口 | **约 30 天**。`UID SEARCH BEFORE <30天前>` 一律返回 0，无论已读未读 |

判据技巧：`SELECT` 返回的 **UIDNEXT** 是历史累计分配过的最大编号。若 `UIDNEXT=2670` 而 `EXISTS=80`，说明 2589 封邮件被搬走了（QQ 邮箱的广告邮件自动分类会把它们搬进不可见的文件夹）。

### ★ 三通道交叉验证（结论可信度的关键）

同一件事用三条独立路线各查一遍，结果收敛才敢下结论：

| 通道 | 协议 / 端点 | 实测结果 |
|---|---|---|
| MCP 连接器 | HTTPS API | 窗口内收件箱 87 封，最早 08-29 |
| IMAP 直连 | `imap.qq.com:993` SSL | 收件箱 **80 封**（69 未读 + 11 已读），最早 08-30 |
| POP3 直连 | `pop.qq.com:995` SSL | 收件箱 **80 封**，最早 08-30（与 IMAP 逐封对应） |

三条通道结果一致 → 限制在 QQ 邮箱服务端策略，**换通道是白费力气，不要重复尝试**。POP3 认证成功说明 POP3 服务也开着；用 `STAT`/`LIST` 计数、`TOP n 0` 取头（不下载正文、不改状态）。

## 二·四、批量删除邮件的标准流程（2026-09-28 实测 63 封成功）

用户确认删除后，**用 `UID MOVE` 移入 `"Deleted Messages"`（网页端"已删除"，可恢复），绝不用 EXPUNGE**。流程：

1. **只读探测**：先用目标 UID 集合核对每封是否存在（`UID SEARCH UID a,b,c` 分批 ≤20 个），缺失必须先报告，不许带着缺失执行
2. **试水 1 封**：先 MOVE 一封最不重要的，`SELECT` 前后对比 EXISTS 验证落位，通过才批量
3. **批量分批**：每批 ≤20 个 UID 逗号拼接，`M.uid("MOVE", ",".join(chunk), '"Deleted Messages"')`，批间 sleep 0.4s
4. **三重校验**：原文件夹 UID SEARCH 应为空 + `Deleted Messages` EXISTS 增量 = 目标数 + **POP3 `STAT` 复核数量**

### ★★ 重大陷阱：MOVE 后 IMAP 的 INBOX 视图会"隐藏"部分邮件（假丢失）

实测：MOVE 63 封后 `SELECT INBOX` 从 80 掉到 **9**，但按算术应剩 20 —— 11 封"消失"且不在任何 IMAP 可见文件夹、不在 Deleted Messages。**用 POP3 `STAT` 复核 = 20 封，逐封 `TOP` 取主题核对，11 封全部真实存在**。

- 原因：QQ 邮箱 IMAP 在批量 MOVE 后索引未刷新，把一部分邮件从 IMAP 视图隐藏；**POP3 与网页端不受影响，邮件没丢**
- **判据**：IMAP 数量对不上时，第一反应查 POP3，不要慌着"恢复"
- 邮件序号计数：POP3 的 `STAT` 数量 = 真实收件箱数量，以此为准
- 后续基于 IMAP 的操作会"看不到"这些邮件，**要么等索引恢复，要么改用 POP3/让用户在网页版操作**

### 删除相关其他坑

- `M.select("Deleted Messages")` 会报 `BAD Select parameters!` —— **含空格的文件夹名必须带引号**：`M.select('"Deleted Messages"')`
- `UID MOVE` 响应 data 为 `[None]`，判断成败只看 typ == "OK"
- 移动前快照三个文件夹的 EXISTS（INBOX/Junk/Deleted Messages），移动后对比，是最可靠的核验方式

## 二·五、全维度覆盖清单（"全量维度检查"指的就是这个）

用户说"全量维度都要检查"时，不要只拉未读。必须覆盖六个维度：

1. **通道维度**：MCP / IMAP / POP3 至少两条交叉验证
2. **文件夹维度**：INBOX、Junk、Drafts、"Sent Messages"、"Deleted Messages" 全部走一遍（含空格的名字要加引号）
3. **状态维度**：**未读 + 已读都要拉** —— ★ 重要内容经常藏在已读邮件里（实测中"服务器入侵告警""赛事方案回复""公安备案数据码"全在已读）
4. **时间维度**：记录最早/最新邮件时间，明确窗口边界
5. **内容维度**：对关键邮件拉正文纯文本摘要（见下）
6. **附件维度**：注意超大附件的**到期时间**（QQ 邮箱超大附件到期即永久失效，无法恢复）

### 正文提取要点

- `BODY.PEEK[]` 取全文，再用 `email.message_from_bytes` 解析
- multipart 优先取 `text/plain`；没有则取 `text/html` 并正则去标签、去 `script/style`
- 每个 part 用 `get_content_charset()` 解码，失败退回 `utf-8` → `gb18030`
- 正文摘要留 1500 字符足够判断价值，避免报告过长

## 三、操作步骤

### 1. 让用户开 IMAP 并给授权码

官方路径（help 明确写：默认关闭，需手动开）：登录 mail.qq.com → **设置 → 帐户** → 找到 POP3/IMAP/SMTP 服务段 → 开启 **IMAP/SMTP 服务** → 手机短信验证 → 得到 **16 位纯字母授权码**（只显示一次）。

给码方式二选一：直接发消息（本地会话）；或写进本地 txt 由脚本读取后删除。

**安全约定（必须主动声明并遵守）**：
- 用 `BODY.PEEK[]` 取信，**绝不触发已读标记**；只执行 SELECT(只读)/SEARCH/FETCH
- 不发送、不回复、不转发、不删除、不移动、不改设置
- 授权码不写入报告、不写入记忆文件、不外传
- 告诉用户随时可在「设置 → 帐户」关闭 IMAP 或重新生成授权码来立即收回

### 2. 先跑连通性 + 文件夹探测

```python
import socket
s = socket.socket(); s.settimeout(6)
s.connect(('imap.qq.com', 993)); s.close()      # 先确认网络通
```

然后 `M.list('""', '"*"')` 列文件夹。**必须用 XML/JSON 存到文件再读**，Windows 控制台直接 print 中文会 GBK 报错。

### 3. 全量拉取

可直接复用本 skill 附带的脚本（见下），命令：

```bash
<managed-python> qqmail_imap_pull.py "<邮箱>" "<授权码>" "<输出.json>"
```

## 四、踩坑清单（每一条都真实踩过）

1. **含空格的文件夹名必须加引号**：`M.select('Sent Messages')` 会返回 `BAD EXAMINE parameters!`，要传 `'"Sent Messages"'`。
2. **search 返回的是 bytes**：`','.join(uids)` 会抛 `TypeError: sequence item 0: expected str instance, bytes found`。先 `.decode()`。
3. **中文文件夹名是 modified UTF-7**，如 `&UXZO1mWHTvZZOQ-` = "其他文件夹"。收发都要编解码，脚本里已内置 `enc_mutf7` / `dec_mutf7`。
4. **imaplib 没有 `xlist`**，调用会 `AttributeError: Unknown IMAP4 command`。用 `list` 即可。
5. **`M.select(name, readonly=True)`** 才是只读；`readonly=False` 会因无写权限或触发副作用。
6. **`M.untagged_responses`** 取 EXISTS/RECENT/UIDNEXT/UIDVALIDITY，注意它是累积的。
7. **批量 FETCH 分批**，每批 ≤15 个 UID，否则大邮箱容易超时。
8. **header 解码**要按 `cs → utf-8 → gb18030 → big5 → latin-1` 顺序试，QQ 邮箱老邮件有 gb18030。

## 五、结论怎么给用户

必须**先摆实测证据，再下结论**，并区分两类：

- **已拿到**：逐封列出（时间/发件人/主题/所在文件夹），按"银行流水 / 云服务 / 差旅 / 合规文书 / 推广订阅 / 垃圾邮件"分类，再抽出"真正需要动手的事"按紧急度排序。
- **拿不到**：说明在哪、为什么拿不到、给可行方案：
  - 方案 A（推荐）：用户自己在网页版左侧栏看各文件夹未读数，批量标记已读/删除（这些基本是推广邮件）
  - 方案 B：关掉 QQ 邮箱的广告邮件自动分类，邮件回到收件箱后 IMAP 就能看到（会改变邮箱行为，历史邮件不回流，谨慎）
  - 方案 C：浏览器自动化接管已登录的网页版会话（需用户明确同意动浏览器）

## 六、附带文件

- `scripts/qqmail_imap_pull.py` —— 隐藏文件夹探测 + 全量未读/已读邮件头拉取（只读），输出 JSON。

## 七、验收标准

- [ ] 三条边界都有实测数据支撑，不是推测
- [ ] 至少两条独立通道交叉验证，结果收敛
- [ ] 已读邮件与所有文件夹都覆盖到了（不许只筛未读就交差）
- [ ] 全程零写入（无已读标记、无移动、无删除）
- [ ] 交付物：分类报告（HTML/Word）+ 待办清单，并弹系统文件夹 + 给预览卡片

## 八、★ 网页版 API 通道（2026-09-29 重大突破：IMAP 的 941 封隐藏邮件靠这条路拿到）

**背景**：QQ 把收件箱 962 封里的 941 封从 IMAP 视图藏掉（SELECT 只报 21 封；UID 直取 1:2670 也返回 0；「广告邮件」「订阅邮件」文件夹协议层不存在）。**网页版才看得到全量**（收件箱 962 / 未读 328）。

### 通道搭建
1. CDP 起专用 profile Edge（不影响用户正在用的浏览器）：
   `msedge.exe --remote-debugging-port=9224 --user-data-dir=C:/Users/book/.workbuddy/profiles/qqmail-cdp https://mail.qq.com`（后台任务保活；首次需用户扫码登录一次，之后长期有效）
2. puppeteer-core connect `http://127.0.0.1:9224`，从页面 URL 取 `sid`。
3. **在 wx.mail.qq.com 页面上下文里 `page.evaluate(fetch(...))` 调 API**（同源带 cookie；NODE_PATH 指 node workspace 的 puppeteer-core，NO_PROXY=127.0.0.1,localhost）。

### 核心 API（都是 POST，body 为 URLSearchParams）
| 接口 | 参数 | 返回 |
|---|---|---|
| `/list/folderlist` | `sid&r&language=zh` | `body.list.sys_list[]`: dirid/name/unread_num/total_num —— 真实计数 |
| `/list/maillist` | `sid&r&language=zh&dir=<dirid>&dirid=<dirid>&func=1&sort_type=1&sort_direction=1&page_now=<N>&page_size=50&enable_topmail=true` | `body.{list,total_num,unread_num}`，条目含 **emailid(删除用)/unread(0,1)/ad(0,1)/subject/senders.item[].{nick,email}/totime(unix)/size** |

翻页拉全：`page_now` 从 0 递增，直到 `list.length<50` 或累计 ≥ total_num。实测收件箱 962/962 一次拉全。

### 注意
- 条目里的 `ad=1` 是 QQ 官方广告标志，`unread=1` 即未读 —— 分类和统计直接用，不用猜。
- **删除接口尚未抓取**：执行删除前先在网页版手动删 1 封并抓包确认接口，再批量。
- 本机工具通道可能被搅乱（路径/端口/变量名被改写）：关键结果一律写文件再读，校验用 Python 正则计数，别信 stdout。
