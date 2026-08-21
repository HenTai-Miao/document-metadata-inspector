# 离线发布与构建依赖

## 最终用户需要安装什么

不需要安装任何东西。发布包内已包含 Python 应用、Temurin/OpenJDK 21、Apache Worker、ExifTool，以及 macOS/Linux 所需的私有 Perl。Microsoft Office、LibreOffice、Java、Python、Perl、ExifTool 均不是运行前置条件，程序也不会在用户电脑上联网下载依赖。

最终用户只需：

1. 解压与其系统/CPU 对应的发布包；
2. 校验同目录 SHA-256；
3. 运行 `docmeta`（Windows 为 `docmeta.exe`）。

## Windows 10/11 x64：构建和交付桌面双版本

> **仅限内部、未签名交付。** 当前 Windows 包尚未配置 Authenticode 证书。SmartScreen、
> 未知发布者或终端防护提示可能出现，不能视为恶意软件结论，也不能替代 SHA-256 核验。
> 以下是原生 Windows x64 **目标构建机**的唯一构建入口，不表示 Windows 产物已经构建或
> 验证完成。它不是 Java 维护者入口。

在 Windows 10 或 Windows 11 x64 的仓库根目录运行。Git 是源码同步与发布元数据前置条件，需
预先安装并确保可由 `PATH` 找到。构建工具链仍只有 `uv`、`nvm` 和内置 PowerShell 5.1。构建机
必须可以写入仓库的 `tools/build-cache/`；它不需要系统 Python、系统 Java 或 Maven。尤其，
目标构建**不使用系统 Java 17**；即使已安装，也不会把它用于构建或验证。

### 一条命令构建

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\build_windows_x64.ps1
```

该入口在成功时执行完整 Python、桌面和冻结交付验证，并输出每个交付文件的相对名称、大小和
SHA-256。失败信息以阶段名开始；先修复该阶段，再从同一条命令重试，不要手工拼接旧的构建命令。

### 使用 Git 中的 Java 输入

Git 已提供两项经过清单校验的 Windows Java 输入：

- `tools/prebuilt/windows-x86_64/OpenJDK21U-jre_x64_windows_hotspot_21.0.12_8.zip`；
- `tools/prebuilt/windows-x86_64/document-metadata-apache-worker.jar`。

在 Java 输入预检和材料化阶段，目标构建只执行这份随附 JRE 中经验证的 `java.exe` 探针；不会
启动 Maven、不会下载 JDK，也不会运行 Java Worker 的源码构建。清单哈希、JRE 内部版本、JAR
及其 Java 源输入指纹任一不符，都会在冻结或打包前失败。

首次联网构建可能下载的非 Java 项目仅为 Python 3.12.13、Node 24、pnpm 11.10.0、锁定的
Python/Node/Electron 依赖，以及 ExifTool。它不会联系 Java/JDK 下载 URL。后续构建复用项目内
缓存：`tools/build-cache/uv`、`tools/build-cache/corepack`、
`tools/build-cache/pnpm-store`、`tools/build-cache/electron` 和
`tools/build-cache/windows-vendored-java`。删除其中任一目录只会使对应输入重新准备；不会改变
Git 跟踪的 Java 输入。

### 获取交付物

组装成功时，待内部交付目录的预期内容为 `release/windows-x64/` 中的六个文件：

```text
DocumentMetadataInspector-<version>-win-x64-Setup.exe
DocumentMetadataInspector-<version>-win-x64-Portable.zip
DocumentMetadataInspector-<version>-win-x64-CLI.zip
SHA256SUMS
BUILD-INFO.json
THIRD_PARTY_NOTICES.md
```

### 排查目标构建

- Git 不可用时，先修复源码同步或仓库安装；组装阶段需要它生成可追溯的发布元数据。
- `uv`、`nvm` 或 PowerShell 5.1 不可用时，安装或修复该目标构建机的预先条件后重试；不要用
  系统 Python、Java 或 Maven 替代它们。
- 若随附 JRE 或 Worker 的完整性预检失败，先还原 Git 跟踪输入，然后重试：

  ```powershell
  git restore -- tools/prebuilt/windows-x86_64/OpenJDK21U-jre_x64_windows_hotspot_21.0.12_8.zip `
    tools/prebuilt/windows-x86_64/document-metadata-apache-worker.jar
  ```

- 仅在 Java 输入确实需要更新时，按[工具维护说明](../tools/README.md)由维护者刷新；目标构建机
  不应运行该维护命令。

### 维护与验收

Java 二进制刷新是维护者职责；适用变更、命令和产物校验见[工具维护说明](../tools/README.md)。
目标构建后，只有冻结 `docmeta verify` 的六项检查和 PowerShell 交付验证均通过，才可把该目录
视为有效的 Windows x64 内部交付物。安装版和便携版来自同一次 Electron Forge packaged app；CLI
ZIP 供运维、自检和批处理使用，而非普通用户入口。交付前还应按照
[Windows x64 手工验收清单](windows-x64-release-acceptance.md)在干净账户中执行并保留不含敏感
数据的记录。

仓库内的子工作流文件仅当此目录是 Git 仓库根目录时才会被 GitHub 自动发现。若父仓库拥有者
需要集中运行该工作流，必须由其单独集成到父仓库的 `.github/workflows/`；不要未经确认复制
或移动工作流文件。

## 开发/打包机器的自动检测（macOS/Linux）

以下路线只用于 macOS/Linux 的依赖检测、资源组装、冻结和真实自检。Windows x64 必须使用上文
的一条 PowerShell 入口，不能把本节的 Java 源码构建步骤用于目标构建机：

```bash
uv run python scripts/build_release.py --mode onefile
uv run python scripts/package_release.py
```

构建流程按以下顺序工作：

1. 验证项目内 ExifTool 13.55 源码；缺失时才从固定官方 URL 下载，并验证归档和源码树哈希。
2. 检查项目缓存、显式候选、`JAVA_HOME` 和 PATH 中是否已有精确的 Eclipse Temurin 21.0.12+8；没有才下载到 `tools/build-cache/temurin/`。不会替换系统 Java。
3. 使用 Maven Wrapper 3.9.11 构建 Java Worker；Wrapper 自己下载 Maven，并用固定发行包 SHA-256 校验。
4. macOS/Linux 编译可重定位 Perl 5.44.0，并内置 Archive::Zip 1.68 与 ExifTool 13.55。构建缓存同时校验平台、构建脚本/清单来源指纹和完整目录哈希；旧缓存缺少完整性记录或任一文件变化时会自动重建。
5. `jlink` 生成当前平台最小 JRE，物化安全的内部许可证链接，并对每个发布文件写入 SHA-256。
6. PyInstaller 生成程序。私有 JRE/Perl 作为字节不变的 DATA 加入，避免 macOS 重签名破坏哈希。
7. 在冻结成品上创建受控 PDF、DOCX、XLSX，要求原生、Apache、ExifTool 三条解析链均提取到预设作者，并复核源文件哈希。
8. 生成程序 `SHA256SUMS` 和可交付 `.tar.gz`/`.zip` 及其 SHA-256。归档与校验文件以事务式成对发布；任何一步失败都会恢复上一对有效文件。

Unix 构建私有 Perl 需要本机 C 编译器、`make` 和 POSIX shell；GitHub 托管的 macOS/Ubuntu runner 已提供这些构建工具。它们只用于发布构建，不会进入最终用户的安装要求。

## 原生平台矩阵

PyInstaller 不能从一个操作系统交叉生成另一个系统的程序，因此每个平台必须在对应 runner 上
构建。手工 Windows 目标机使用本页的一条 PowerShell 入口。
CI 不调用 `scripts/build_windows_x64.ps1`。
`.github/workflows/build-offline-releases.yml` 采用独立路线：

- `actions/setup-java` 提供精确 JDK 21；
- 质量 job 使用 Maven Wrapper 验证 Java 源码；
- 各原生 runner 运行 `build_release.py --mode onefile`、桌面构建、归档与平台交付验证。

CI runner 矩阵为：

- Linux x86_64：`ubuntu-24.04`
- Windows x86_64：`windows-2025`
- macOS ARM64：`macos-15`
- macOS Intel x86_64：`macos-15-intel`

工作流可手动触发，也会在 `v*` 标签上执行。它先运行完整 Python/Java 与 Electron 质量门，再并行构建四个平台的命令行归档和桌面安装包。Windows 生成 Squirrel 安装器，Linux 生成 DEB/RPM，macOS 生成 DMG/ZIP；每个 Electron 包都会重新构建并自检当前源码对应的离线核心。Windows/Linux/macOS 的实际产物必须由相应 runner 的自检结果证明；不能用 macOS 本地产物冒充三平台已构建。

当前项目位于一个更大的本地 Git 工作区中。为保持修改范围只在本项目内，工作流文件保存在本目录；GitHub 只会从仓库根目录的 `.github/workflows/` 发现工作流，因此应将 `document-metadata-inspector/` 作为独立仓库发布后再运行该矩阵。不要在未经确认时把它复制到上层工作区根目录。

## macOS/Linux 手动分步构建

需要诊断某一步时可以使用：

```bash
uv sync --all-groups --locked
uv run python scripts/bootstrap_tools.py
uv run python scripts/bootstrap_jdk.py

# Java Worker
cd java-worker
./mvnw --batch-mode --no-transfer-progress verify
cd ..

# 最终推荐仍使用总入口，它会选择当前平台的正确参数
uv run python scripts/build_release.py --mode onefile
```

Electron Forge 默认从官方发行源取得当前平台 Electron ZIP，并使用自己的校验缓存。隔离网络环境中如已提前下载同版本官方 ZIP，可将其所在目录通过 `DOCMETA_ELECTRON_ZIP_DIR` 传给 `pnpm make`；文件名必须保持 `electron-v<版本>-<平台>-<架构>.zip`，该选项只影响构建机，不会成为最终用户依赖。

## 发布前检查

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run basedpyright
uv lock --check
uv build
uv run docmeta verify
```

macOS/Linux 的 Java 侧运行 `java-worker/mvnw verify`。冻结成品还必须运行 `docmeta verify` 并获得
6 个 PASS。任何组件不可用、哈希不一致、PDF/Word/Excel 任一解析链缺失都会使构建失败。Windows
x64 的对应质量与交付检查由其一条 PowerShell 入口执行。

## 签名说明

当前 macOS Electron 应用会施加 ad-hoc 结构签名，并在打包钩子中执行 `codesign --verify --deep --strict`；该签名用于封装完整性验证，不等同于 Apple Developer ID 签名或公证。尚未配置 macOS Developer ID/公证及 Windows Authenticode，正式外部分发前仍需使用组织证书完成可信签名；未取得证书前不将产物表述为已公证或受系统信任。
