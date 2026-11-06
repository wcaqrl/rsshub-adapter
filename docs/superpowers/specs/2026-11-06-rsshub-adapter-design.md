# RSSHub 自动更新适配器

沿用已确定的 GitHub adapter → lazycat-action@v1 → 官方镜像转存 → LPK → 官方审核与独立 Release 流程。

## 目标与兼容边界

- 包名 `cloud.lazycat.app.rsshub`，已有商店版本 `1.0.0`，只面向官方商店。
- 保留服务名 `rsshub`、`redis`，子域名 `rsshub`、1200 端口、后台任务及 `/lzcapp/var/redis:/data`。
- 沿用 Chromium bundled 功能，不替换成不带浏览器的镜像；Redis Stack 保留已安装的 6.2.6-v17 镜像与固定摘要，本次不做数据库大版本迁移。
- Runner 执行镜像及升级测试，本机仅做轻量单元测试，不安装到用户微服。

## 更新来源与版本

上游实际稳定 Release 标签为 `v2026.11.06-8596.4be79cd`，并发布完整提交号镜像。
沿用用户已确定的 Release/tag 优先，不监控主分支、不直接使用滚动 latest 或日期镜像。

为通用执行器添加显式 Git `version_regex` / `version_template` 映射，默认普通 SemVer 行为保持不变。
本应用按年、月、上游 workflow 构建号映射，例如 `2026.11.8596`；构建号按数字比较。
完整 tag 和 peeled commit SHA 保存在 state，镜像选择 `chromium-bundled-<完整SHA>`，额外核对标签短 SHA。
Release 页面只提供镜像信息，更新日志使用精确两个已处理提交间的 git log；首次从旧包镜像标记的 `2070264d57563c93296402aa5c156c1c7d5f7a16` 起算。

## 方案选择

采用 Release 对应提交镜像，因为它有不可变源身份且符合既定版本判断规则。
滚动 Chromium 或日期镜像无法对应同一天多次发布；本次不采用。
从源码重建镜像增加依赖维护和资源消耗，官方已经提供 Chromium 镜像，本次不需要。

## 部署与交付

迁移成 LPK v2 的 Manifest / Package / Build，中文、英文 usage，保留原图标并以明确图标规范交付。
RSSHub 对 Redis 的地址使用带 `redis://` 的正式 URL，保留旧数据挂载。
不对 RSS 订阅入口新增账号登录门槛；现有访问规则保持兼容。
每 6 小时检查，push 与手动默认 dry-run；真实执行强制验证镜像后转存、打包、送审。
`LZC_API_TOKEN` 只在 adapter Secrets；真实送审前检查协作者权限。
状态只由实际执行生成并提交；被处理/拒绝源版本不重复提交；Release 只上传版本化 `.lpk`，与送审独立。

## 验证

核心测试覆盖日期前导零、构建号9/10排序、annotated tag、默认 SemVer 回归、配置限制。
应用测试覆盖旧版→新版同一 Redis 持久目录、Redis 真实缓存读写、HTTP 首页/healthz、离线可控 RSS 输出和 Chromium 执行。
打包 guard 绑定测试过的提交及目标平台摘要，拒绝未验证的镜像或缺失配置；转存后核对实际 LPK 与审核记录。

## 实现选择

当前交付 `linux/amd64`，与旧包一致；上游 arm64 不能推导现有应用已经完成 arm64 升级兼容验证。
通用执行器映射属于 opt-in，仅 RSSHub 使用新规则。发布版本后更新浮动 `v1`，其它适配器无需改动。
