# 离线发布与构建依赖

## 最终用户需要安装什么

不需要安装任何东西。发布包内已包含 Python 应用、Temurin/OpenJDK 21、Apache Worker、ExifTool，以及 macOS/Linux 所需的私有 Perl。Microsoft Office、LibreOffice、Java、Python、Perl、ExifTool 均不是运行前置条件，程序也不会在用户电脑上联网下载依赖。

最终用户只需：

1. 解压与其系统/CPU 对应的发布包；
2. 校验同目录 SHA-256；
3. 运行 `docmeta`（Windows 为 `docmeta.exe`）。

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
