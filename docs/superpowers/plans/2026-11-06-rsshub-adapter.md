# RSSHub Adapter Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将 RSSHub 官方 Release 自动更新为兼容原商店应用的、经过验证的 LPK 并真实送审。
**Architecture:** 显式 Git 标签映射支持由通用执行器负责，应用部署和不可变镜像测试由独立 adapter 负责。
**Tech Stack:** Go、Python 标准库、Docker、GitHub Actions、LazyCat SDK。
**Spec:** `../specs/2026-11-06-rsshub-adapter-design.md`

## Global Constraints

- 包名 `cloud.lazycat.app.rsshub`，现有版本 `1.0.0`。
- 保留 Chromium、RSSHub+Redis Stack、`/lzcapp/var/redis:/data`；仅 amd64，本次不升级 Redis。
- 仅使用完整提交号镜像与平台摘要，官方仓库交付，禁止伪造 state。
- Runner 运行容器；现有微服无安装变更。

## Review Focus

- 非 SemVer Git 标签不能被默认为预发布过滤；新增显式映射与回归测试。
- 同日多个构建按数字比较，镜像短 SHA、完整 SHA 必须一致。
- 新源未发布镜像必须失败，不能回退 latest。
- 升级必须保留 Redis 原持久数据和缓存内容。
- 官方转存改变来源标签时不得误判成文件系统变化。

### Task 1: Git 标签映射

Files: `lazycat-action/internal/source/discover.go`、`internal/config/load.go` 及对应测试和配置说明。
- [x] 先测试日期标签映射、9/10顺序、peeled SHA，以及只允许 Git tag 策略使用映射。
- [x] 执行失败测试；复用现有 versioning 映射规则，仅显式配置启用。
- [x] 执行核心完整测试与 lint；发布兼容的 v1 新版本。

### Task 2: RSSHub adapter

Files: `lazycat-action.yml`、`lzc-manifest.yml`、`package.yml`、`lzc-build.yml`、图标、`scripts/`、`tests/`、`.github/workflows/update.yml`、README。
- [x] 先测试源 tag→提交镜像转换、不可变验证记录与配置约束。
- [x] 实现 Runner 旧版/新版 Redis 升级与 HTTP/RSS/Chromium 验证，成功才生成打包证明。
- [x] 本地轻量测试和 Runner verify-only，核对元数据。
- [x] 推送工作流，验证 PAT 权限，真实执行、核对审核、状态提交与 Release 下载。

## 执行记录

- 核心日期标签映射及 previous-source changelog 环境经 RED→GREEN 验证；完整 Go 测试、vet、bootstrap 和 Release 发布器测试通过。
- 应用来源/镜像内容/打包 guard/真实缓存完整性共 9 项单元测试通过，工作流 actionlint 通过。
- 独立只读审查发现的缓存验证及交付核验缺口已通过先失败后通过测试补齐；审查无剩余阻塞项。
- 实现选择：保留旧 470×470 正方形 PNG 字节，保持原应用图标；不重新生成品牌图案。
- 实现选择：旧版与新版的缓存键规则已经变化，验证旧实际缓存字节保留，并额外验证新版独立缓存的离线命中，不要求上游实现跨缓存键迁移。
- 核心 dd582ad 已通过远程 CI，v1.9.0 发行成功且浮动 v1 已更新。
- 真实运行 42191632917 完成旧版升级/Redis/Chromium 验证、镜像转存、LPK 打包、送审及独立 Release。
- 应用 2026.11.8596，审核编号 22676，提交时 waiting；LPK SHA-256 为 1b5c6ab169251bf6c6cb144348ef3849b42294c5535c561e63b44d33f08eea5f。
- 补充后续版本测试：首次用原商店基线，之后自动以 state 的上一版官方镜像升级，避免原始旧镜像回收导致长期任务失效；10 项单元测试通过。

- 后续基线 Runner 独立验证 42194119010 已通过（使用上一版官方镜像；生成验证 Artifact，不重复打包送审）。
- 提交后检查 42193941823 成功，送审和 Release 均跳过同一源版本。
