# RSSHub · 懒猫微服自动更新适配器

现有应用 **`cloud.lazycat.app.rsshub`** 的独立 GitHub 适配仓库。上游为
[DIYgod/RSSHub](https://github.com/DIYgod/RSSHub)，执行器为
[`wcaqrl/lazycat-action@v1`](https://github.com/wcaqrl/lazycat-action)。无需修改上游。

## 流程

每六小时检查正式 Release 对应 Git 标签 → 锁定完整提交号的 Chromium 镜像及 amd64 摘要
→ Runner 新装/真实旧包升级/Redis 缓存/Chromium 测试 → 官方镜像转存 → LPK
→ 官方商店审核与独立 GitHub Release → 提交状态锁。

- 推送代码仅检查；定时任务真实处理新版本；手动默认勾选 `dry-run`。
- `dry-run` + `verify-image` 可只验证镜像与升级，不转存、不打包、不送审。
- 真实运行不用勾选 `verify-image`，正式流程本身强制测试。
- Release 仅上传带应用版本的 `.lpk`，失败不会阻止送审。GitHub 自动附带的 Source code 压缩包不能由发布脚本关闭。
- 已处理或被拒的同一上游版本不自动重提；修复拒绝后手动选择 `retry-rejected`。

## 配置

本仓库 Settings → Secrets and variables → Actions → Repository secrets 设置
`LZC_API_TOKEN`（开发者 PAT），对应账号须有应用开发者/协作者权限。
**不需要 `LAZYCAT_AUTO_PUBLISH` 或 Docker 仓库账号。**

Actions → **Update RSSHub for LazyCat** → Run workflow，选择 `main`。
保留 `dry-run` 查看计划；取消勾选后才真实执行。
北京时间约 **02:53、08:53、14:53、20:53** 检查，GitHub 可能延迟或跳过繁忙时段。

## 特殊版本规则

上游示例 `v2026.11.06-8596.4be79cd` 是正式版本，不是 SemVer 预发布。
`lazycat-action >= v1.9.0` 的显式 Git 映射将其转换为 **2026.11.8596**：年、月、上游构建序号。
数字比较避免 9/10 字符串排序问题；保留完整标签、Git SHA、目标平台镜像摘要。
严格选择 `ghcr.io/diygod/rsshub:chromium-bundled-<40位提交号>`。
不会换用不带浏览器的镜像或 `latest`/日期滚动标签，也不会把 `package.json` 的固定 `1.0.0` 当更新标识。

`package.yml` 初始保留已上线 `1.0.0`。首次成功运行才由执行器更新版本并生成
`.lazycat-action.lock.yml`，该状态文件必须提交，不得伪造或删除以强制重试。

## 与旧包兼容

基线来自用户提供的原始 `cloud.lazycat.app.rsshub-v1.0.0.lpk`，包格式是 ZIP，包含旧版 Manifest。
保留 `rsshub` / `redis` 服务、`rsshub` 子域名、1200 端口、后台运行和
**`/lzcapp/var/redis:/data`**；保留商店原方形 PNG 图标。

旧 RSSHub 实际提交 `2070264d57563c93296402aa5c156c1c7d5f7a16`，2024-11-20 构建。
首次使用该商店原镜像验证迁移；之后使用状态中记录的上一版官方交付镜像作为升级基线，
避免未来一直依赖已不再被线上版本引用的 2024 年镜像。
Redis Stack **6.2.6-v17** 固定为商店原摘要，本次不升级 Redis 或清空缓存。
修正 Redis URL 为带 `redis://` 的完整地址，RSSHub 已带 Chromium。
只验证并交付 `linux/amd64`；上游支持 arm64 不等于该旧应用的升级已完成 arm64 验证。
LPK v2 使用最低系统版本 1.6.0。

RSSHub 是订阅生成服务，RSS 阅读器需要直接请求路由，因此保留原访问方式。
部分路由所需 Cookie、API 密钥、限流或网站反爬限制仍由相应上游站点决定。

## 测试与更新日志

镜像测试只在 Runner 的临时容器和目录运行，不接触微服生产数据。
使用旧官方镜像启动 Redis 与 RSSHub，从可控本地 JSON 源生成真实 RSS，再验证应用实际写入的
Redis 缓存经过保存、容器重建和升级后保留；验证新旧 RSS、Chromium 页面脚本、再建容器及空数据新装。
仅测试容器开启转换路由所需的 `ALLOW_USER_SUPPLY_UNSAFE_DOMAIN`；应用默认配置不改变此开关。
打包脚本核对测试摘要、配置内容和版本，不允许跳过运行验证直接打新包。

更新日志取两个实际提交之间的 `git log`，首次从上述旧包提交开始，后续从状态记录的提交开始。
最多提交最近 80 条非合并提交，并附完整 compare 地址及范围提交数量；不使用整页 Release 或整个 CHANGELOG。
服务端负责补齐中英文翻译，adapter 不伪造另一语种。

本机轻量检查：

```bash
python3 -m pip install -r requirements-test.txt
python3 -B -m unittest discover -s tests -v
```

旧官方镜像通过只监听 Runner 回环地址的只读桥接从懒猫官方静态 CDN 获取，锁定 Manifest、配置和分层摘要；
不需要懒猫仓库登录，不替换为别的重建镜像。下载、日志、证明和 LPK 都已 ignore。

许可证及图标来源见 [NOTICE.md](NOTICE.md)。
