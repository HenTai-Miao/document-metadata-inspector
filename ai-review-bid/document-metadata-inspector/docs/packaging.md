# 离线发布与构建依赖

## 最终用户需要安装什么

不需要安装任何东西。发布包内已包含 Python 应用、Temurin/OpenJDK 21、Apache Worker、ExifTool，以及 macOS/Linux 所需的私有 Perl。Microsoft Office、LibreOffice、Java、Python、Perl、ExifTool 均不是运行前置条件，程序也不会在用户电脑上联网下载依赖。

最终用户只需：

1. 解压与其系统/CPU 对应的发布包；
2. 校验同目录 SHA-256；
3. 运行 `docmeta`（Windows 为 `docmeta.exe`）。

## 仅使用当前 Mac 生成 Windows 10/11 x64 安装包

这条构建路线完全不启动、不访问 Parallels 或其他 Windows 虚拟机。Mac 下载固定版本的
Windows x64 CPython 3.12.13、Temurin JRE 21.0.12+8、ExifTool 13.55 和 Electron
43.3.0，把锁定的 Windows x64 wheels 与项目源码一起放进 Electron `resources`，最后由
Mac 原生 NSIS 编译器生成 Windows 安装程序。最终用户不需要安装 Python、Java、Node.js、
ExifTool 或项目依赖。

最终包只保留运行组件：Java 使用 JRE，不携带 JDK 编译工具；Python 去掉开发头文件、
链接库、pip、venv、Tk/Tcl、IDLE 和演示组件；Electron 只保留简体中文与英文回退语言包。
ExifTool 的格式模块和 Electron 的核心兼容 DLL 保持完整，避免因过度裁剪导致文档核验或
启动失败。

构建机首次执行前安装 NSIS：

```bash
brew install nsis
```

随后在仓库根目录执行一条命令：

```bash
uv run python scripts/windows_embedded_release.py
```

完成后 `release/windows-x64/` 包含：

```text
DocumentMetadataInspector-0.1.0-win-x64-Setup.exe
DocumentMetadataInspector-0.1.0-win-x64-Portable.zip
SHA256SUMS
BUILD-INFO.json
THIRD_PARTY_NOTICES.md
```

安装版和便携版携带同一套完整应用资源。Mac 构建门会校验全部运行时文件清单，并要求
Electron、Python、Java、ExifTool、DLL、PYD 和 Node 原生模块的 PE 机器类型均为 AMD64。
NSIS 安装器自身使用 NSIS 的标准引导程序，但安装时会拒绝非 x64 Windows。Mac 只能证明
资源完整性和 x64 二进制架构；在用户提供的真实 Windows x64 电脑上首次运行安装与文档核验，
仍是最终原生验收步骤。

## Windows 10/11 x64：构建和交付桌面双版本

> **仅限内部、未签名交付。** 当前 Windows 包尚未配置 Authenticode 证书。SmartScreen、
> 未知发布者或终端防护提示可能出现，不能视为恶意软件结论，也不能替代 SHA-256 核验。
> 以下是原生 Windows x64 构建与验收流程，不表示 Windows 产物已经构建或验证完成。

在原生 Windows 10 或 Windows 11 x64 构建机的仓库根目录按以下顺序运行。

- 完整 JDK、构建机 Python 解释器及工具链、Node.js 和 pnpm 是构建机工具；它们不是最终用户的系统前置条件。
- 产品会有意内置冻结的 Python 解释器，以及私有的 `jlink` JRE、Apache Worker 和 ExifTool
  运行时。
- 最终用户不需要系统 Python、Java 或 ExifTool，也不会在运行时下载组件。

最后两条命令中的 `-Mode All` 不可省略。

```powershell
uv python install 3.12.13
uv sync --all-groups --locked
uv run python scripts/build_release.py --mode onefile
Set-Location desktop
pnpm install --frozen-lockfile
pnpm make
Set-Location ..
uv run python scripts/package_release.py
uv run python scripts/assemble_windows_release.py
pwsh -File scripts/verify_windows_release.ps1 `
  -ReleaseDirectory release/windows-x64 `
  -Mode All
```

第一次 `build_release.py --mode onefile` 是独立的质量与自检门。随后 `pnpm make` 会通过
`prepare-runtime.mjs` 刻意执行最终的干净 onefile 重建与六项自检，再把这一版核心嵌入
Electron；它不是对第一次构建产物的复用。返回仓库根目录后，`package_release.py` 才把同一
最终冻结核心归档为 CLI ZIP，避免桌面包与 CLI ZIP 分别携带 A/B 两版核心。最终用户收到的是
嵌入的 Python，以及私有的 `jlink` JRE、Apache Worker 和 ExifTool 运行时，不依赖系统
Python、Java、ExifTool 或运行时下载。

组装成功时，待内部交付目录的预期内容为 `release/windows-x64/` 中的六个文件：

```text
DocumentMetadataInspector-<version>-win-x64-Setup.exe
DocumentMetadataInspector-<version>-win-x64-Portable.zip
DocumentMetadataInspector-<version>-win-x64-CLI.zip
SHA256SUMS
BUILD-INFO.json
THIRD_PARTY_NOTICES.md
```

只有冻结 `docmeta verify` 的六项检查均通过，且上述 PowerShell 交付验证以 `-Mode All`
通过时，才可把最终产物视为有效的 Windows x64 内部交付物。安装版和便携版来自同一次
Electron Forge packaged app；CLI ZIP 供运维、自检和批处理使用，而非普通用户入口。交付前
还应按照[Windows x64 手工验收清单](windows-x64-release-acceptance.md)在干净账户中执行并保留
不含敏感数据的记录。

CI 的 Windows x64 job 也以同一条 `scripts/verify_windows_release.ps1` 命令和 `-Mode All`
完成交付验证后才上传 Windows 交付目录。

仓库内的子工作流文件仅当此目录是 Git 仓库根目录时才会被 GitHub 自动发现。若父仓库拥有者
需要集中运行该工作流，必须由其单独集成到父仓库的 `.github/workflows/`；不要未经确认复制
或移动工作流文件。

## 开发/打包机器的自动检测

一条命令完成当前平台的依赖检测、资源组装、冻结和真实自检：

```bash
uv run python scripts/build_release.py --mode onefile
uv run python scripts/package_release.py
```

构建流程按以下顺序工作：

1. 验证项目内 ExifTool 13.55 源码；缺失时才从固定官方 URL 下载，并验证归档和源码树哈希。
2. 检查项目缓存、显式候选、`JAVA_HOME` 和 PATH 中是否已有精确的 Eclipse Temurin 21.0.12+8；没有才下载到 `tools/build-cache/temurin/`。不会替换系统 Java。
3. 使用 Maven Wrapper 3.9.11 构建 Java Worker；Wrapper 自己下载 Maven，并用固定发行包 SHA-256 校验。
4. Windows 获取官方独立 ExifTool 13.55；macOS/Linux 编译可重定位 Perl 5.44.0，并内置 Archive::Zip 1.68 与 ExifTool 13.55。构建缓存同时校验平台、构建脚本/清单来源指纹和完整目录哈希；旧缓存缺少完整性记录或任一文件变化时会自动重建。
5. `jlink` 生成当前平台最小 JRE，物化安全的内部许可证链接，并对每个发布文件写入 SHA-256。
6. PyInstaller 生成程序。私有 JRE/Perl 作为字节不变的 DATA 加入，避免 macOS 重签名破坏哈希。
7. 在冻结成品上创建受控 PDF、DOCX、XLSX，要求原生、Apache、ExifTool 三条解析链均提取到预设作者，并复核源文件哈希。
8. 生成程序 `SHA256SUMS` 和可交付 `.tar.gz`/`.zip` 及其 SHA-256。归档与校验文件以事务式成对发布；任何一步失败都会恢复上一对有效文件。

Unix 构建私有 Perl 需要本机 C 编译器、`make` 和 POSIX shell；GitHub 托管的 macOS/Ubuntu runner 已提供这些构建工具。它们只用于发布构建，不会进入最终用户的安装要求。

## 原生平台矩阵

PyInstaller 不能从一个操作系统交叉生成另一个系统的程序，因此每个平台必须在对应 runner 上构建。仓库提供 `.github/workflows/build-offline-releases.yml`：

- Linux x86_64：`ubuntu-24.04`
- Windows x86_64：`windows-2025`
- macOS ARM64：`macos-15`
- macOS Intel x86_64：`macos-15-intel`

工作流可手动触发，也会在 `v*` 标签上执行。它先运行完整 Python/Java 与 Electron 质量门，再并行构建四个平台的命令行归档和桌面安装包。Windows 生成 Squirrel 安装器，Linux 生成 DEB/RPM，macOS 生成 DMG/ZIP；每个 Electron 包都会重新构建并自检当前源码对应的离线核心。Windows/Linux/macOS 的实际产物必须由相应 runner 的自检结果证明；不能用 macOS 本地产物冒充三平台已构建。

当前项目位于一个更大的本地 Git 工作区中。为保持修改范围只在本项目内，工作流文件保存在本目录；GitHub 只会从仓库根目录的 `.github/workflows/` 发现工作流，因此应将 `document-metadata-inspector/` 作为独立仓库发布后再运行该矩阵。不要在未经确认时把它复制到上层工作区根目录。

## 手动分步构建

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

Windows 使用 `scripts/build_windows_exiftool.py`，总入口会自动选择，不需要用户手工拼接命令。

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

Java 侧运行 `java-worker/mvnw verify`。冻结成品还必须运行 `docmeta verify` 并获得 6 个 PASS。任何组件不可用、哈希不一致、PDF/Word/Excel 任一解析链缺失都会使构建失败。

## 签名说明

当前 macOS Electron 应用会施加 ad-hoc 结构签名，并在打包钩子中执行 `codesign --verify --deep --strict`；该签名用于封装完整性验证，不等同于 Apple Developer ID 签名或公证。尚未配置 macOS Developer ID/公证及 Windows Authenticode，正式外部分发前仍需使用组织证书完成可信签名；未取得证书前不将产物表述为已公证或受系统信任。
