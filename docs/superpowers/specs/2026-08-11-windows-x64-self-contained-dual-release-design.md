# Windows x64 全离线双交付设计

## 状态与已确认范围

- 日期：2026-08-11
- 目标系统：Windows 10/11 x64，不兼容 Windows 7 或 32 位 Windows。
- 交付形态：同时提供桌面安装版和桌面便携版；保留命令行包作为支持工具。
- 分发范围：组织内部使用，当前不配置 Windows Authenticode 代码签名。
- 最终用户零运行时依赖：不要求安装 Python、Java、Perl、ExifTool、
  Microsoft Office、LibreOffice、Node.js 或其他开发工具。
- 修改范围严格限定为 `document-metadata-inspector/`，不移动或修改父工作区的
  GitHub Actions 配置。
- 本设计延续现有 Python、Java Worker、ExifTool 和 Electron 架构，不改变公共模型、
  JSON 序列化、错误码、证据来源或解析完整度契约。

## 目标

把现有 Windows x64 自包含核心打包链路补齐为一套可重复、可校验的内部桌面发布：

1. 普通用户运行安装程序后即可启动“文档元数据核验”。
2. 无安装权限的用户完整解压便携包后即可启动相同桌面程序。
3. 两种桌面交付物包含同一版本、同一哈希的离线核心，行为和报告一致。
4. 软件启动和扫描时只使用包内 Python、私有 Java 运行时、Java Worker 和 ExifTool，
   不查询或回退到系统工具，也不在最终用户机器上下载依赖。
5. 每次正式构建均在原生 Windows x64 环境完成，并用冻结成品真实验证 PDF、Word、
   Excel 及原生、Apache、ExifTool 三条解析链。
6. 正式交付物带统一 SHA-256 和不包含敏感构建机信息的构建说明。

## 非目标

- 不支持 Windows x86、Windows 7、Windows ARM64、Linux 或 macOS 交付物的本轮改造。
- 不把完整 JDK、Maven、uv、Node.js、pnpm 或项目源码放入最终用户包。
- 不引入 Nuitka、cx_Freeze、WiX、MSIX、Inno Setup 或新的自动更新系统。
- 不配置 Authenticode 证书、时间戳服务或对外可信发布。
- 不增加运行时联网下载、系统 Java/Python/ExifTool 回退或动态依赖安装。
- 不改变扫描功能、证据模型、报告界面或文档解析安全边界。
- 不把当前子项目的工作流复制到父 Git 仓库根目录；这需要单独授权和仓库级决策。

## 方案决策

### 采用：PyInstaller 单文件核心加 Electron Forge 双 Maker

继续使用现有 `onefile` 核心。PyInstaller 把 Python 应用及解释器、裁剪后的私有 JRE、
Java Worker JAR 和 Windows ExifTool 作为受控数据打入 `docmeta.exe`。Electron Forge
把这个已验证的核心作为 `extraResource` 放入桌面应用，并在同一次 Windows x64 构建中
同时运行：

- Squirrel Maker：生成桌面安装包；
- ZIP Maker：生成完整桌面应用目录的便携 ZIP。

选择该方案是因为现有仓库已经具备资源锁定、PyInstaller 构建、冻结后自检、核心哈希
校验、Electron 运行时解析和 Squirrel 打包。新增 Windows ZIP 目标能够复用同一 packaged
app，不需要建立第二套运行时或安装体系。

### 暂不采用：PyInstaller `onedir` 核心

`onedir` 可减少大型单文件核心每次扫描启动时的临时释放成本，但会把当前单文件哈希
边界扩大为目录树边界，同时要求修改运行时复制、解析、完整性校验和清理逻辑。本轮先用
真实 Windows 机器测量冷启动和扫描启动开销；只有达不到本设计的性能验收标准时，才另行
设计 `onedir` 迁移，不在本轮静默切换。

### 不采用：替换打包技术栈

手工嵌入 Python、携带完整 JDK 或改用其他冻结/安装器工具不能提高本轮核心能力，却会
增加版本漂移、供应链校验和测试成本，因此不纳入实现。

## 运行时组成与边界

### 构建机组件

Windows x64 构建机使用以下固定工具：

- Python 3.12.13 和锁定的 `uv.lock`；
- PyInstaller 6.21.0；
- Eclipse Temurin JDK 21.0.12+8；
- Maven Wrapper 3.9.11；
- Node.js 24、pnpm 11.10.0；
- Electron 43.3.0、Electron Forge 7.11.2；
- Windows x64 ExifTool 13.55 standalone。

这些组件只用于构建。构建脚本继续通过固定 URL、版本、归档哈希和目录树哈希验证外部
资源，禁止使用未验证的替代归档。

### 最终用户组件

最终用户得到：

- Electron 桌面运行时和已构建的 Renderer/Main/Preload；
- `docmeta.exe`，其中包含 Python 解释器、Python 依赖和应用代码；
- 由 JDK 21 的 `jlink` 生成的最小 Windows x64 Java 运行时；
- 已验证的 Apache Worker shaded JAR；
- Windows x64 ExifTool 13.55 standalone；
- 第三方通知、核心哈希和桌面发布哈希。

完整 JDK 不进入最终包。最终用户只需要执行 Java Worker，因此携带私有 JRE 能减少体积和
攻击面，同时满足“无需安装 Java”的目标。

### 运行时解析

打包后的 Electron 主进程只解析：

```text
process.resourcesPath/docmeta-runtime/docmeta.exe
```

启动扫描前，主进程必须验证该文件是普通文件、不是符号链接，并同时满足应用内固化的
预期 SHA-256 与 `docmeta-runtime/SHA256SUMS`。校验失败时显示现有稳定的“离线分析组件
缺失或损坏”错误并拒绝扫描；不得下载、修复或回退到系统命令。

开发模式仍可使用现有 `dist/<platform>/onefile/docmeta` 和显式 `uv run docmeta` 回退，
但该分支不能出现在 packaged 应用的运行决策中。

## 构建与数据流

```text
固定源码与锁文件
  -> 验证/取得 Windows x64 ExifTool 与 Temurin JDK
  -> Maven Wrapper 验证并构建 Java Worker
  -> jlink 生成私有 Windows x64 JRE
  -> 组装 tools/packaged/windows-x86_64 并生成资源哈希
  -> 首次 PyInstaller onefile 构建与六项真实 verify 作为独立质量门
  -> pnpm make 的 prepare-runtime 执行最终干净 onefile 重建与六项真实 verify
  -> 校验并复制最终 docmeta.exe 到 desktop/.runtime/docmeta-runtime
  -> Electron Forge package 生成唯一的 win32-x64 packaged app
  -> Squirrel Maker 生成安装版
  -> ZIP Maker 从同一 packaged app 生成便携版
  -> package_release.py 将同一最终冻结核心归档为 CLI ZIP
  -> 发布汇总器验证、标准化命名并生成统一 SHA256SUMS/BUILD-INFO.json
```

桌面扫描数据流保持不变：Renderer 通过受限 Preload 调用主进程；主进程从已确认的文件清单
写入临时输入清单，启动一次包内 `docmeta.exe compare`，读取有大小上限的临时 JSON 报告，
验证边界后返回页面模型，并在完成、失败或停止后清理临时目录。

## 交付物与命名

正式内部发布目录为：

```text
release/windows-x64/
├── DocumentMetadataInspector-<version>-win-x64-Setup.exe
├── DocumentMetadataInspector-<version>-win-x64-Portable.zip
├── DocumentMetadataInspector-<version>-win-x64-CLI.zip
├── SHA256SUMS
├── BUILD-INFO.json
└── THIRD_PARTY_NOTICES.md
```

规则如下：

- `<version>` 取项目发布版本；Python `pyproject.toml` 与桌面 `package.json` 版本必须相同，
  不同则构建失败。
- 安装版和便携版必须来自同一次 Forge packaged app，且必须携带同一核心 SHA-256。
- `CLI.zip` 沿用现有命令行发布包，主要用于运维、自检和批处理，不作为普通用户入口。
- 发布汇总器只接受预期目录内恰好一个 Windows x64 Setup、一个桌面 ZIP 和一个 CLI ZIP；
  缺失、重复、符号链接、架构不符或文件名无法判定时失败关闭。
- `SHA256SUMS` 使用小写十六进制 SHA-256，覆盖上述三个归档/安装文件、
  `BUILD-INFO.json` 和 `THIRD_PARTY_NOTICES.md`，按文件名稳定排序。
- 发布文件先写入同目录临时位置，全部验证成功后再成组发布，避免部分更新覆盖上一组有效
  产物。

`BUILD-INFO.json` 只记录发布追溯所需的非敏感信息：schema version、产品版本、Git commit、
目标平台 `windows-x86_64`、Python/JRE/ExifTool/Electron/Forge 版本、核心 SHA-256 和 UTC
构建时间。它不得记录用户名、机器名、工作区绝对路径、环境变量、下载凭据或文档路径。

## 安装版行为

- Squirrel 安装包显示产品名“文档元数据核验”，安装完成后启动同一桌面入口。
- 安装和卸载只管理应用自身文件，不删除用户选择的文档、导出报告或工作目录。
- 当前内部未签名包可能出现 SmartScreen 或组织终端防护提示；发布说明应明确 SHA-256 校验
  方法，不得把未签名产物描述为系统信任。
- 本轮不实现自动更新；升级通过新的完整内部安装包完成。

## 便携版行为

- 用户必须先完整解压 ZIP，再运行顶层桌面可执行文件；不支持从压缩包预览器内直接运行。
- 便携版不要求管理员权限，不安装 Python/JRE/ExifTool，不写系统 `PATH`，不注册系统服务，
  也不创建运行时下载缓存。
- Electron/Chromium 自身可能按照平台默认行为写用户级缓存和偏好。不得宣称“完全零写入”；
  核心任务临时文件仍必须写系统临时目录并在任务结束后按现有安全规则清理。
- 应用可以从包含中文、空格和长路径的普通本地目录启动；不能依赖当前工作目录。
- 便携目录内任一核心资源缺失或被修改时必须拒绝扫描并显示完整性错误。

## 完整性、安全与错误处理

- 所有输入文档继续视为不可信；不得提取归档到不受控位置、执行宏/脚本/嵌入对象、访问
  外部关系或放宽 Java Worker 的 JVM 全局网络拒绝边界。
- PyInstaller 打包资源保持 DATA 语义，不能由签名或重写步骤改变已锁定 JRE、Worker、
  ExifTool 字节。
- 核心冻结自检、核心 SHA-256 校验、Electron 内嵌预期哈希和最终交付物 SHA-256 是分层
  边界，不能以其中一个替代其他边界。
- 构建或打包失败时不得发布半套安装版/便携版，也不得保留名称上看似正式但未经验证的
  新产物。
- 运行时缺失、损坏、超时、输出超限、停止失败及临时目录清理失败继续使用现有桌面错误
  分类和中文消息，本轮不扩展 Python 公共错误码。
- 未签名仅影响 Windows 信任提示，不允许跳过哈希、自检或 Defender 开启状态下的验收。

## 原生构建边界

PyInstaller 和 Electron 最终产物必须在 Windows x64 上构建。macOS 开发机只能修改并运行
与平台无关的测试，不能生成或宣称验证正式 Windows 交付物。

仓库内现有 Windows runner 配置可在以下任一条件成立时使用：

1. `document-metadata-inspector/` 成为独立 Git 仓库，使本目录 `.github/workflows/` 位于
   仓库根；或
2. 上层仓库拥有者另行批准并接入父仓库根工作流。

在这两个条件均不成立时，使用受控 Windows 10/11 x64 构建机执行相同锁定命令。本轮实现
只维护当前项目内脚本和工作流，不擅自修改父仓库。

## 测试与验收

### 代码质量门

正式构建前必须通过：

```text
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run basedpyright
uv lock --check
uv build
java-worker/mvnw.cmd --batch-mode --no-transfer-progress verify
desktop: pnpm test, pnpm typecheck, pnpm lint, pnpm format:check, pnpm build
```

### 核心冻结验收

- `docmeta.exe verify` 六项全部 PASS。
- 受控 PDF、DOCX、XLSX 分别由原生、Apache、ExifTool 引擎提取预期作者。
- 自检前后源文件 SHA-256 不变。
- 在未安装系统 Python、Java、ExifTool、Office 和 LibreOffice 的干净 Windows 10/11 x64
  环境中仍能完成自检和真实扫描。

### 安装版验收

- `Setup.exe` 能安装、启动、扫描、关闭、再次启动和卸载。
- 安装后临时移除系统 `PATH` 中的 Python、Java 和 ExifTool 不影响运行。
- 从中文、空格和长路径目录选择受控 PDF、Word、Excel 后能生成结果。
- 停止扫描能终止应用拥有的完整 Python/Java/ExifTool 进程树，不残留后台进程。
- 卸载后用户原始文档和显式导出的报告仍存在。

### 便携版验收

- 在全新目录完整解压后直接启动，无需管理员权限和运行时安装。
- 从普通本地目录、中文路径、空格路径和接近 Windows 常用长路径边界的位置启动并扫描。
- 移动整个已解压目录后仍能启动，证明没有写死构建机或首次解压路径。
- 删除或修改 `docmeta-runtime/docmeta.exe` 后应用拒绝扫描并显示稳定完整性错误。
- 便携版与安装版对同一受控输入产生规范化后相同的权威报告。

### 性能与终端防护验收

- 在指定内部基准 Windows x64 机器上，首次打开桌面窗口应在 10 秒内完成。
- 点击扫描后，核心进程应在 15 秒内进入实际解析阶段；真实文档总扫描时限仍由现有任务预算
  控制，不把文档解析耗时错误归因于打包启动。
- Windows Defender 保持开启；安装、解压、启动、自检和扫描期间不得出现确认的恶意检测。
  若只出现未知发布者或 SmartScreen 信誉提示，按内部未签名限制记录，不视为功能失败。
- 如果单文件释放导致连续三次基准均超过启动门槛，停止本轮发布，不在同一改动中临时切换
  `onedir`；另起设计评估目录式运行时。

### 发布验收

- `release/windows-x64/` 中只有一套目标版本正式产物，文件名和版本一致。
- 对每个文件重新计算 SHA-256 与 `SHA256SUMS` 完全一致。
- 从 Setup 和 Portable 中提取或读取的内嵌核心哈希一致，并等于 `BUILD-INFO.json` 记录值。
- `BUILD-INFO.json` 不包含用户名、主机名、绝对构建路径、环境变量值或凭据。
- 第三方通知随安装版、便携版或其可访问资源提供，并在发布目录保留独立副本。

## 预期实现范围

1. 调整 Electron Forge Maker 配置，使 `@electron-forge/maker-zip` 同时支持 `win32`，保留
   现有 Windows Squirrel 行为。
2. 为 Maker 配置和 Windows 产物增加窄范围测试，证明 Windows 构建会同时请求安装版与
   ZIP，其他平台行为不回归。
3. 增加独立发布汇总器，负责版本一致性、产物唯一性、标准化命名、统一 SHA-256、
   `BUILD-INFO.json` 和事务式发布；不把这些职责塞进运行时准备脚本或 Forge 配置。
4. 扩展 Windows CI 上传和本地 Windows 构建说明，使正式目录包含桌面安装版、便携版和
   CLI 支持包。
5. 增加 Windows 安装版、便携版的人工/自动验收清单，保留未签名内部发布限制。

## 完成标准

- Windows 10/11 x64 原生构建一次生成安装版、便携版和 CLI 支持包。
- 安装版与便携版共享同一哈希锁定的 `docmeta.exe`，且最终用户无需安装任何运行时。
- 便携版完整解压后可直接双击运行，移动目录后仍可运行。
- 冻结核心、安装版和便携版在 Defender 开启的干净 Windows 环境通过全部验收。
- 所有正式交付文件由统一 `SHA256SUMS` 和脱敏 `BUILD-INFO.json` 覆盖。
- 公共 Python/JSON/错误码契约和文档解析安全边界没有变化。
- 现有 Python、Java 和 Electron 质量门全部通过，且没有修改父工作区其他项目。
