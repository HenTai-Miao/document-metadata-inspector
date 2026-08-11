# Windows x64 Git 内置 Java 运行时设计

## 状态与已确认决策

- 日期：2026-08-11。
- 实施分支：`dev-yx/design-spec-style-polish-20260810`。
- 目标系统：Windows 10/11 x64。
- 目标构建机只要求预先安装 `uv` 和 `nvm`，并允许首次联网下载 Python、Node、pnpm、
  Electron 及其他非 Java 构建依赖。
- 目标构建机现有 Java 17 不参与正式构建，不修改其安装、`JAVA_HOME` 或系统 `PATH`。
- Java Worker 和最终应用继续使用 Java 21 契约，不把产品运行时降级到 Java 17。
- Windows x64 Temurin JRE 21 和 Apache Worker shaded JAR 作为受校验的 Git 二进制提交并
  推送，不使用 Git LFS。
- 本设计只解决 Windows x64 构建机的 Java 前置条件和构建入口，不夹带扫描失败或子进程
  CMD 窗口问题；这些问题等待目标机器的新日志后单独诊断。

## 背景与约束

当前 `java-worker/pom.xml` 使用 `maven.compiler.release=21`，生产代码和测试中还各有一处
Java 21 `List.getFirst()` 调用。`tools/manifest.json` 同时把 Apache Worker 的运行要求锁定为
Eclipse Adoptium Temurin `21.0.12+8`。因此目标机器上的 Java 17 不能原样构建当前 Worker。

把 Worker 改为 Java 17 技术上可行，但不能消除最终应用携带私有 JRE 的要求，还会扩大到
编译目标、源代码 API、`jlink`、运行时清单、CI 和跨平台发布矩阵。本轮已经明确选择提交
Windows x64 JRE 与 JAR，因而保留 Java 21，避免引入无关的运行时降级。

提交二进制会永久增加 Git 历史体积。当前同类本机产物中，Worker JAR 约为 57 MiB，裁剪
JRE 约为 52 MiB；实际提交以 Windows x64 官方 JRE ZIP 的真实字节数为准。远程仓库可能
设置单文件、单次请求或仓库大小限制。本轮仍按用户选择直接提交；若远程拒绝，保留本地
提交并报告服务器的原始错误，不擅自改用外部对象存储或未批准的下载地址。

## 目标

1. 在没有系统 JDK 21 的 Windows x64 机器上，仅使用 `uv` 和 `nvm` 完成桌面安装版、
   便携版和 CLI 支持包构建。
2. 构建与最终运行都使用 Git 中固定、可验证的 Windows x64 JRE 与 Worker JAR，不读取或
   回退到系统 Java 17。
3. JRE/JAR 缺失、被修改、版本不一致、架构不符或 Worker 源码已变化时失败关闭，禁止
   悄悄联网补 Java 或继续发布旧 JAR。
4. Python、Node、pnpm、Electron 和其他非 Java 构建依赖允许首次联网取得并缓存，后续可以
   复用缓存。
5. 保留现有安装版、便携版、CLI 包的名称、内容边界、冻结后自检、SHA-256 和最终发布
   验证契约。
6. 提供一条可复制执行的 PowerShell 总入口，并在每个阶段输出清晰的中文状态和失败位置。

## 非目标

- 不把 Java Worker 或所有平台整体迁移到 Java 17。
- 不提交完整 JDK、Maven 发行包、Python、Node.js、pnpm store、Electron 缓存或最终发布包。
- 不支持 Windows x86、Windows ARM64 或 Windows 7。
- 不改变 PDF、Word、Excel 解析逻辑、公共模型、JSON 协议、错误码或证据完整度语义。
- 不在最终用户运行时加入联网下载、系统 Java 回退或动态修复。
- 不在本轮修复 `scan:start` 失败或 Windows CMD 窗口闪现；二者需要目标机器证据和独立
  回归测试。
- 不配置 Git LFS、外部制品库、GitHub Release、对象存储或 Authenticode。
- 不修改父工作区或相邻项目。

## Git 中的预构建资源

### 文件布局

受版本控制的 Windows x64 Java 资源固定放在：

```text
tools/prebuilt/windows-x86_64/
├── OpenJDK21U-jre_x64_windows_hotspot_21.0.12_8.zip
└── document-metadata-apache-worker.jar
```

JRE 保留 Adoptium 官方 ZIP 的原始字节，不把解压后的成百上千个运行时文件分别提交到 Git。
这样既保留官方归档哈希，又减少 Git 树对象数量和 Windows 文件权限差异。JAR 使用 Maven
Shade 生成的最终 `document-metadata-apache-worker.jar`，不提交 `original-*.jar`、`target/`
或 Maven 缓存。

新增二进制属性规则，至少覆盖上述目录中的 `*.zip` 和 `*.jar`，将其明确标记为非文本，
避免换行转换或无意义文本差异。项目继续使用普通 Git blob；不生成 LFS 指针。

### 单一清单

`tools/manifest.json` 继续作为版本、来源和哈希的唯一权威清单，不再新增第二份会漂移的
预构建资源清单。Windows x64 项目需要在现有 Temurin JRE 与 Apache Worker 配置中记录：

- 仓库相对路径；
- 精确字节数；
- 小写十六进制 SHA-256；
- 目标 `windows-x86_64`；
- Java vendor、major 和 exact runtime version；
- JRE 官方 URL 与官方归档 SHA-256；
- Worker artifact version；
- Worker 输入树 SHA-256；
- 生成 Worker 时使用的 JDK 版本和固定 Maven 命令。

清单不得记录构建机用户名、主机名、绝对路径、环境变量值、私有下载地址或凭据。JRE 的
仓库文件哈希必须等于其现有官方归档哈希；不允许重新压缩后使用一个只在本仓库成立的新
哈希。

### Worker 输入树指纹

Worker JAR 不能只靠自身哈希判断是否过期。构建工具对以下输入形成稳定树指纹：

```text
java-worker/pom.xml
java-worker/mvnw
java-worker/mvnw.cmd
java-worker/.mvn/**
java-worker/src/main/**
java-worker/src/test/**
```

算法按规范化 POSIX 相对路径排序，对每个普通文件依次加入路径、文件长度和原始内容，使用
NUL 分隔后计算 SHA-256。禁止跟随目录外符号链接，禁止把 `target/`、IDE 文件、操作系统
缓存或文件修改时间纳入指纹。

把测试源和 Maven Wrapper 一并纳入指纹意味着：任何 Worker 生产代码、测试、依赖、构建
插件或构建入口发生变化后，旧 JAR 都会被拒绝。维护者必须重新运行 Java 测试并生成新的
预构建 JAR，不能只手工更新清单哈希。

## 组件边界

### 预构建资源读取器

新增一个小型 Python 模块，只负责：

1. 从 `tools/manifest.json` 解析 Windows x64 JRE/JAR 描述；
2. 解析仓库相对路径并确认目标仍位于项目根目录内；
3. 拒绝符号链接、目录、稀疏占位文件和非普通文件；
4. 校验文件大小与 SHA-256；
5. 重新计算 Worker 输入树指纹；
6. 安全解压 JRE 到项目缓存；
7. 返回已验证的 `java.exe`、JRE 根目录和 Worker JAR 路径。

它不负责运行 Maven、不负责下载 Java、不负责 PyInstaller 或 Electron 打包，也不读取系统
Java。调用方只消费已验证的路径，避免各打包脚本分别实现一套哈希和路径规则。

### 维护者生成入口

新增维护命令，用于更新 Git 中的两份二进制。该命令必须：

1. 从清单中的 Adoptium 官方 URL 取得 JRE ZIP，并先验证官方 SHA-256；
2. 使用清单锁定的精确 Temurin JDK 21；
3. 运行 Maven Wrapper `verify`，只有全部 Java 测试通过后才接受 shaded JAR；
4. 对生成的 JAR 和 Worker 输入树计算 SHA-256；
5. 先写入临时文件，在所有检查通过后再替换预构建文件并更新清单；
6. 输出新增二进制的大小和哈希，不自动提交或推送。

这个命令供具备 JDK 21 的维护环境使用，不属于目标 Windows 构建机的日常命令。本轮首次
纳管可以使用当前已验证的 Temurin 21 构建缓存生成 JAR；Windows JRE 仍必须是清单固定的
官方原始 ZIP。

### Windows x64 打包入口

新增 `scripts/build_windows_x64.ps1`，作为目标电脑的唯一推荐入口。它只把以下两个程序视为
系统前置条件：

- `uv`；
- `nvm`。

Windows 自带的 Windows PowerShell 5.1 视为操作系统组件，不构成额外安装前置条件。新增
总入口以及现有 `verify_windows_release.ps1` 必须同时兼容 Windows PowerShell 5.1 和
PowerShell 7；不得要求用户另行安装 `pwsh`。文档中的标准调用使用 `powershell.exe`，在
已经安装 PowerShell 7 的机器上也允许使用 `pwsh` 执行同一脚本。

脚本按顺序执行：

```text
确认 Windows 10/11 x64、项目根目录、uv 与 nvm
  -> 校验 Git 内置 JRE/JAR 与 Worker 输入树指纹
  -> nvm 安装或选择 Node.js 24
  -> 准备固定 pnpm 11.10.0
  -> uv 安装或选择 Python 3.12.13
  -> uv sync --all-groups --locked
  -> 运行 Python 与 Electron 质量门
  -> 使用 Git 内置 JRE/JAR 生成最终冻结核心并执行真实 verify
  -> Electron Forge 生成安装版与便携版
  -> 生成 CLI 包并汇总 Windows x64 发布目录
  -> verify_windows_release.ps1 -Mode All
  -> 输出发布目录、文件大小与 SHA-256
```

脚本使用 `Set-StrictMode -Version Latest` 和 `$ErrorActionPreference = "Stop"`。每一阶段用固定
名称输出开始、成功或失败，异常时保留原始命令退出码和最后一个阶段名。脚本不吞掉 `uv`、
pnpm、PyInstaller、Electron 或发布验证的标准错误。

`nvm` 只负责安装/选择 Node.js 24。pnpm 使用项目声明的 `11.10.0`，不能使用不受约束的
全局最新版。`uv` 继续遵守 `.python-version` 和 `uv.lock`，不读取系统 Python。

### 原有打包流程接入

Windows x64 的资源准备阶段改为调用预构建资源读取器，而不是 `ensure_jdk()`、Maven Wrapper
和 `jlink`。它把经过验证并安全解压的 JRE 与 JAR复制到：

```text
tools/packaged/windows-x86_64/apache/jre/
tools/packaged/windows-x86_64/apache/worker.jar
```

后续 PyInstaller、冻结后自检、Electron `extraResource`、CLI 归档和发布汇总流程保持现有
接口。Linux、macOS 及其他目标继续使用原有 JDK/Maven/`jlink` 路径，不因 Windows x64 的
Git 内置资源改变行为。

现有 macOS 交叉组装 Windows x64 资源的路径也复用同一个读取器，避免一条路径使用 Git
资源、另一条路径仍联网下载 JRE 或重新构建 JAR。无论从 macOS 交叉组装还是 Windows 原生
构建，最终放入包内的 JRE/JAR 必须具有相同哈希。

## 缓存策略

Git 中的 ZIP/JAR 是不可变输入，不是构建缓存。可删除、可重建的内容仍放在已忽略的
`tools/build-cache/` 中：

- 解压后的 JRE：按预构建清单整体指纹分目录保存；
- `uv` 下载缓存；
- pnpm store；
- Electron 的首次依赖下载缓存；
- Windows ExifTool 和其他现有受校验资源缓存。

Maven 仅在维护者或 CI 重新生成、验证 Worker JAR 时使用，不是目标 Windows x64 日常打包
流程的一部分，也不由 PowerShell 总入口下载。

缓存记录至少包含来源 JRE ZIP 哈希、读取器版本和解压目录树哈希。命中缓存时重新验证记录
和必要文件；记录缺失、清单变化或目录被修改时在临时目录重建，再原子替换旧缓存。缓存损坏
不能回写 Git 中的预构建 ZIP/JAR。

用户可以删除 `tools/build-cache/` 重新开始；只要 Git 工作树中的 JRE/JAR 完整，Java 部分
不需要联网或系统 JDK。Python、Node、pnpm、Electron 和其他未提交依赖仍可能在首次构建时
联网。

## 安全与失败行为

- JRE ZIP 解压必须拒绝绝对路径、`..` 穿越、驱动器路径、重复冲突条目、符号链接、硬链接、
  设备文件和目标目录外写入。
- 解压完成后必须确认存在普通文件 `bin/java.exe`，并验证其 PE 架构为 AMD64。
- 所有主机都通过 JRE 的 `release` 文件校验 OS、架构、image type、vendor、major 和 exact
  runtime version。Windows x64 原生构建还必须实际运行私有
  `java.exe -XshowSettings:properties -version` 复核这些值，输出有大小和超时上限；macOS
  交叉组装不得尝试执行 Windows PE 文件。
- Worker JAR 必须是普通文件，大小、哈希和输入树指纹全部匹配后才允许复制。
- Git 内置资源校验失败时禁止回退到系统 Java、`JAVA_HOME`、PATH、网络 JRE 或旧缓存。
- 最终应用继续只解析包内 Java 与 Worker，不增加运行时下载或系统工具回退。
- Java Worker 的 JVM 全局网络拒绝、安全管理参数、进程超时、输出预算和临时文件清理保持
  不变。
- 失败构建不得覆盖上一组已验证的正式发布文件；新产物先进入临时位置，全部验证成功后再
  成组发布。
- 构建日志不得打印环境变量全集、用户文件路径、凭据或内部地址。

## 二进制更新规则

出现以下任一变化时，必须重新生成并同时提交 JAR、清单和相关测试：

- `java-worker/` 输入树指纹变化；
- Java依赖、Maven插件或 Worker 版本变化；
- 目标 Temurin JRE 补丁版本变化；
- Windows x64 JRE 官方归档或预期哈希变化；
- Worker 的运行模块要求变化。

只修改 Python、Electron UI 或普通文档时无需重新生成 JAR。JRE 版本不变时也无需重新提交
JRE ZIP。维护脚本必须拒绝“只更新清单、不提供匹配文件”以及“只替换文件、不更新清单”
两种半更新状态。

## 测试与验收

### 自动测试

新增或扩展测试，至少覆盖：

1. 正常解析预构建清单并校验 JRE/JAR；
2. 文件缺失、大小错误、哈希错误、符号链接和仓库外路径；
3. Worker 生产源、测试源、POM 或 Wrapper 变化造成输入树指纹失配；
4. JRE ZIP 路径穿越、绝对路径、链接条目和重复冲突条目；
5. 缓存命中、清单变化、缓存损坏和原子重建；
6. Windows x64 资源准备不调用 `ensure_jdk`、Maven或 `jlink`；
7. 非 Windows x64 平台仍走现有源码构建路径；
8. macOS 交叉组装和 Windows 原生组装得到相同 JRE/JAR 哈希；
9. PowerShell 入口固定使用 Node 24、pnpm 11.10.0、Python 3.12.13 和最终 `-Mode All`
   验证，并通过静态兼容性检查避免 PowerShell 7 专有参数；
10. 发布目录仍只接受一套安装版、便携版、CLI 包及其元数据。

### 提交前质量门

代码与二进制提交前在可用环境中运行：

```text
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run basedpyright
uv lock --check
uv build
java-worker/mvnw --batch-mode --no-transfer-progress verify
desktop: pnpm test, pnpm typecheck, pnpm lint, pnpm format:check, pnpm build
```

Java Maven验证使用精确 Temurin JDK 21 完成，是生成预构建 JAR 的必要证据。目标 Windows
机器日常打包不重复编译 JAR，但冻结后的 `docmeta verify` 必须实际启动 Git 内置 JRE 与 JAR，
完成受控 PDF、DOCX 和 XLSX 的原生、Apache、ExifTool 六项检查。

### Windows x64 原生验收

在目标 Windows 10/11 x64 电脑上：

1. 临时从当前 PowerShell 会话移除系统 Java 17 的 `JAVA_HOME` 和 PATH 可见性；
2. 保留联网能力，执行唯一 PowerShell 构建入口；
3. 确认构建过程没有要求安装 JDK，也没有访问 Java 下载地址；
4. 确认安装版、便携版和 CLI 包全部生成；
5. 执行 `verify_windows_release.ps1 -Mode All` 并全部通过；
6. 断网后再次运行安装版和便携版，扫描受控 PDF、Word、Excel；
7. 删除构建缓存后重新构建，确认 Java 部分仍仅使用 Git 内置资源；
8. 修改 JAR 一个字节后确认构建在打包前失败，再恢复 Git 文件；
9. 保留不含敏感信息的命令退出码、发布文件哈希和错误日志。

当前 macOS 环境可以完成 Python 单元测试、清单/哈希验证和跨平台资源组装验证，但不能把
这些结果表述为 Windows 原生安装、启动和扫描已经验收。正式 Windows 结论以目标机器的
`-Mode All` 结果为准。

## 文档与操作交付

实现时更新 `README.md`、`docs/packaging.md`、`tools/README.md` 和 Windows x64 验收文档，
明确区分：

- 目标构建机前置条件：Windows 自带 PowerShell 5.1、`uv`、`nvm` 和首次联网；
- Git 已携带组件：Windows x64 JRE、Worker JAR；
- 首次联网下载组件：Python、Node、pnpm、Electron、Python/Node依赖及其他构建依赖；
- 最终用户前置条件：无；
- Worker/JRE 更新维护命令；
- 常见失败的检查命令和需要回传的最小日志。

最终交付给目标电脑的标准命令保持为一个仓库根目录 `powershell.exe` 调用。实现计划确定
脚本参数后，文档给出精确可复制命令，不要求用户安装 PowerShell 7、手工执行 Maven、设置
`JAVA_HOME` 或组合多段打包命令。

## 分支集成与提交边界

当前分支先保留本设计提交。实施阶段把
`dev-yx/windows-x64-dual-release-20260811` 的既有 Windows x64 打包能力合并到当前分支，
然后在当前分支实现 Git 内置 Java 资源。合并不得覆盖当前分支已有自定义标题栏变化，也不得
暂存父工作区或相邻项目的未跟踪文件。

实现至少分为以下可审计提交：

1. 合并现有 Windows x64 双发布能力；
2. 增加预构建资源读取、维护命令和测试；
3. 加入经过校验的 Windows x64 JRE/JAR 与清单；
4. 增加 PowerShell 总入口、文档和工作流接入。

如果远程在二进制提交处拒绝推送，停止远程交付并报告限制；不得把二进制拆成隐蔽编码文本、
绕过服务端限制或推送到未经授权的位置。

## 完成标准

- Git 跟踪 Windows x64 官方 Temurin JRE ZIP 和与当前 Worker 输入树一致的 shaded JAR。
- `tools/manifest.json` 对两份文件的路径、大小、SHA-256、版本、架构和 Worker 输入树指纹
  提供单一权威记录。
- Windows x64 打包不安装、不查找、不执行系统 Java 17，也不下载 Java/JDK。
- 目标构建机只需 `uv`、`nvm` 与首次联网，即可通过一条 PowerShell 命令生成三种发布物。
- Git 内置资源任一缺失、篡改或过期都会在打包前失败，且没有系统/网络/缓存回退。
- 安装版、便携版和 CLI 包内使用同一哈希的 JRE/JAR，并通过冻结自检和最终 `-Mode All`
  验证。
- Python、Java、Electron 质量门及相关新增回归测试全部通过。
- 当前分支的源码、设计、二进制和文档提交成功推送到远程；如果服务器拒绝大对象，已保留
  可复现的本地提交并报告准确阻塞原因。
- 没有提交构建缓存、最终发布包、真实用户文档、敏感配置或父工作区文件。
