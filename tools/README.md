# Bundled parser tools

This directory contains build inputs for the offline application. It is not an
end-user installation directory.

## ExifTool

- Locked version: `13.55`
- Official source artifact and SHA-256: `manifest.json`
- Development source tree: `vendor/exiftool/13.55/source/`
- Bootstrap command: `uv run python scripts/bootstrap_tools.py`

The bootstrap command runs only on developer/build machines. It checks the
vendored tree first and downloads the official artifact only when that tree is
missing. It never runs from an installed application.

Release builds must populate the matching `packaged` manifest entry with a
self-contained platform command and SHA-256 for every runtime file. macOS and
Linux packages must include a private Perl runtime; Windows packages use the
controlled standalone ExifTool runtime. A release may not fall back to a
system `exiftool`, `perl`, Python, Java, Office, or LibreOffice installation.

The relocatable Unix runtime also pins Archive::Zip 1.68 so ExifTool can inspect
compressed Word and Excel OPC packages instead of reporting only their ZIP
inventory.

## Java

### Windows x64 Java 维护

Windows x64 的目标构建只消费 Git 跟踪的 JRE ZIP 和 Apache Worker JAR；它不在目标机下载
JDK、运行 Maven 或从 Java 源码生成 Worker。只有维护者在受控的开发环境中才可刷新这些二进制
输入，使用以下命令：

```bash
uv run python scripts/vendor_windows_java.py \
  --cache tools/build-cache/windows-java-vendor
```

该维护入口要求精确的 Eclipse Temurin JDK 21.0.12+8，使用 Maven Wrapper 执行 Worker 的
`verify`，下载并校验官方 Windows x64 JRE ZIP 的 SHA-256，并把 Worker 的 Java 生产源、测试、
POM、Wrapper 和 Maven 配置写入来源指纹。仅在所有校验通过后，它才原子更新
`tools/prebuilt/windows-x86_64/` 下的
`OpenJDK21U-jre_x64_windows_hotspot_21.0.12_8.zip` 和
`document-metadata-apache-worker.jar`，以及清单中的哈希和指纹。

任何 Java 生产源、测试、POM、Wrapper、依赖/插件、Worker 版本或 Temurin 补丁变化，都必须重新
运行 `vendor_windows_java.py` 并提交更新后的二进制和清单。仅 Python 或 UI 变更不触发此刷新。
目标构建从 Git 验证这些文件，并且只执行其中经验证的 `java.exe` 探针；因此绝不运行这条维护
命令，避免目标机出现 Maven/JDK 下载或不受控的 Java 产物。

### macOS 和 Linux Java 维护

`scripts/bootstrap_jdk.py` 检测精确的 Eclipse Temurin 21.0.12+8 JDK，并且只在没有兼容候选时
将经过哈希锁定的官方归档下载到忽略的构建缓存。macOS 和 Linux 使用该 JDK 通过 `jlink` 生成
随附运行时。Maven 3.9.11 由 `java-worker/` 下经过校验的 Maven Wrapper 提供。

At runtime the resolver verifies all declared hashes before starting the tool.
The application invokes ExifTool with fixed read-only arguments, sends the
temporary source path and optional password through standard input, and runs
without network access or write-tag arguments.
