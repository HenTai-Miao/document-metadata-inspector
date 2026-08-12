# 围标串标投标人名称一致检测工具

离线提取、核验并对比 PDF、Word、Excel 文件元数据的取证型工具。最终产品名为“围标串标投标人名称一致检测工具”，同时提供 `docmeta` 命令行核心与 Electron 桌面程序。

## 支持范围

- PDF：`.pdf`
- Word：`.doc`、`.docx`、`.docm`、`.dot`、`.dotx`、`.dotm`
- Excel：`.xls`、`.xlsx`、`.xlsm`、`.xlsb`、`.xlt`、`.xltx`、`.xltm`

程序不会只按扩展名判断文件，而会校验 PDF、OLE、OPC/ZIP 的真实容器身份。每个文件由三条相互独立的解析链处理：

1. 原生安全解析器：Office 核心/扩展/自定义属性、包清单、Word/Excel 批注与修订作者、PDF Info/XMP/标识符等。
2. Apache Java Worker：Tika 3.3.2，并使用 POI 5.5.1、PDFBox 3.0.8 等解析器补充格式覆盖。
3. ExifTool 13.55：保留其原始分组、字段名和值，作为独立证据来源。

合并结果不会用一个解析器覆盖另一个解析器。每条观察值保留解析器、来源位置、原始键、原始值、规范化值、可信度和警告；比较采用精确值与证据来源，可导出 JSON、XLSX、HTML。嵌入文件按稳定资源 ID 建立独立子报告，记录父级、深度、内部路径、类型、大小和 SHA-256，避免把嵌入文档的作者误算成主文档作者。

“完整”表示在资源限制内，所有已识别且可访问的元数据通道均已成功读取。加密、损坏、未知二进制修订流或不支持的结构会明确标记为 `partial`、`encrypted`、`corrupt` 或 `unknown`，不会伪装成完整结果。

## 本地运行

开发环境使用 Python 3.12 和 `uv`：

```bash
uv sync --all-groups
uv run python scripts/bootstrap_tools.py
uv run docmeta verify
```

`bootstrap_tools.py` 会先验证项目内的 ExifTool 13.55 源码，只在缺失时从清单中的官方固定地址下载并校验 SHA-256。`bootstrap_jdk.py` 对 Temurin JDK 21.0.12+8 采用相同的“先检测、缺失才下载”策略。它们只服务于开发/打包，最终用户不需要安装 Python、Java、Perl、ExifTool、Office 或 LibreOffice。

常用命令：

```bash
# 扫描一个或多个文件
uv run docmeta scan a.pdf b.docx c.xlsx --json scan-report.json

# 对比作者、修改者、时间、应用程序等可比元数据
uv run docmeta compare a.docx b.xlsx c.pdf --json comparison.json

# 招投标目录：根目录下每个一级子目录视为一个投标人
# 同一投标人内部的重复值不会形成匹配，只有跨投标人的痕迹会保留
uv run docmeta compare -r 4-投标文件 --group-by-top-level-dir --json comparison.json

# 将已有 JSON 报告导出为审阅文件
uv run docmeta export comparison.json --format xlsx --output comparison.xlsx
uv run docmeta export comparison.json --format html --output comparison.html

# 检查三条解析链和受控 PDF/Word/Excel 样本
uv run docmeta verify
```

加密文件只支持交互式 `--prompt-password`。密码仅保存在当前进程内存中，不提供明文命令行参数，不记录、不写入报告，也不尝试破解。

退出码稳定为：`0` 完整成功，`2` 错误，`3` 部分成功，`4` 离线自检失败。

## 离线发布

每个平台必须在对应操作系统上原生构建，因为 PyInstaller 不是跨平台编译器。Windows x64
构建使用 Git 随附并预检的 JRE 与 Apache Worker；macOS/Linux 保留从 Java 源码构建 Worker 并
用 `jlink` 生成运行时的路线。发布树会内置：

- 当前平台的 Python 应用及解释器；
- Windows x64 已验证的随附 Temurin/OpenJDK 21 JRE，或 macOS/Linux 经 `jlink` 裁剪的运行时；
- Apache Worker 的 shaded JAR；
- macOS/Linux 私有 Perl 5.44.0 + ExifTool 13.55，或 Windows 官方独立 ExifTool 13.55；
- 全部运行时文件的 SHA-256 清单和第三方许可说明。

生成的程序会先做真实 PDF、DOCX、XLSX 离线自检，验证三条解析链和源文件哈希均正常，才生成 `SHA256SUMS`。详细步骤见 [docs/packaging.md](docs/packaging.md)。

macOS/Linux 当前平台一键构建与归档：

```bash
uv run python scripts/build_release.py --mode onefile
uv run python scripts/package_release.py
```

### Windows 10/11 x64 桌面交付

Windows x64 内部交付包含安装版、便携版和命令行归档。安装版运行
`DocumentMetadataInspector-<version>-win-x64-Setup.exe`。便携版必须先完整解压
`DocumentMetadataInspector-<version>-win-x64-Portable.zip`，再运行
`docmeta-review.exe`；不要在 ZIP 预览器中直接运行。运维和支持人员使用
`DocumentMetadataInspector-<version>-win-x64-CLI.zip`，它不是普通用户入口。

两个桌面变体都不使用系统 Python、Java 或 ExifTool，也不会在运行时下载组件。Windows x64
目标构建同样使用已验证的随附 Java，不会使用系统 Java 17、下载 JDK 或在目标机运行 Maven。
内部复制或分发前，必须使用 `SHA256SUMS` 核对已下载/复制文件的 SHA-256。Windows 包目前仅用于
未签名内部交付，可能显示未知发布者、SmartScreen 或终端防护提示；这些提示不替代哈希校验。完整的
Windows 构建步骤和干净虚拟机验收记录见
[docs/packaging.md](docs/packaging.md) 与
[docs/windows-x64-release-acceptance.md](docs/windows-x64-release-acceptance.md)。

## Electron 桌面程序

桌面程序包含两个页面：先选择“投标文件”根目录并开始/停止核验，再按投标人展示结果。根目录下每个一级子目录视为一个投标人；同一投标人自己的文件只做组内归集，不会互相判定冲突。只有跨投标人的作者、最后修改者、批注者等人员痕迹使用红色，软件和环境线索保持中性色。

开发运行：

```bash
cd desktop
pnpm install --frozen-lockfile
pnpm start
```

构建当前平台应用或安装包：

```bash
cd desktop
pnpm package
pnpm make
```

`package` 和 `make` 会先调用现有发布流水线，重新构建并自检当前源码对应的 `docmeta` 核心，再将其放入 Electron 资源目录，避免误打包旧版本。macOS、Windows、Linux 必须分别在对应操作系统上原生构建；最终用户不需要安装 Node.js、Python、Java、Perl 或 ExifTool，也不会在运行时联网下载组件。

需要用外部真实文件查看同一套渲染页面、但不把文件或报告复制进仓库时：

```bash
pnpm preview:real -- --folder /path/to/4-投标文件 --report /path/to/comparison.json
```

发布前可用一条命令执行真实核心“停止→立即重启→完整扫描”，随后自动启动页面并运行浏览器交互验收。三项输入都保留在仓库外：

```bash
pnpm verify:real -- \
  --folder /path/to/4-投标文件 \
  --report /path/to/comparison.json \
  --runtime /path/to/packaged/docmeta
```

该验收会检查投标人边界、完整提取数、跨投标人人员痕迹、环境线索、SVG 卡片连接、文件证据展开、开始/停止/重新开始，以及浏览器控制台错误。开发机没有 Playwright 浏览器时，此验收命令会为测试缓存下载 Chromium；它不会进入安装包，也不是最终用户依赖。`DOCMETA_REAL_FOLDER` 与 `DOCMETA_REAL_RUNTIME` 也可配合 `pnpm test:real-runtime` 单独运行生产 ScanService 集成测试；默认单元测试不会读取外部真实文件。

## 安全边界

- 输入文件一律视为不可信；ZIP/OLE/XML/PDF 读取均有大小、条目、时间和内存预算。
- Java Worker 另有进程树 RSS、输出大小、嵌入深度/数量/累计字节上限，并在整个 JVM 内禁止 URL、HTTP 客户端、DNS、Socket、监听和组播；超限会终止整个工作进程并明确标记，不返回伪完整结果。
- 不执行宏、脚本、嵌入对象或外部关系，不联网解析文档内容。
- 批注正文不进入报告，只保留字符数和 SHA-256；作者、日期、修订类型等取证字段保留。
- 扫描前后复核源文件大小、时间和 SHA-256，检测扫描期间被替换或修改的文件。
- 发布模式绝不回退到系统 Java、Perl 或 ExifTool；内置文件哈希不匹配时直接失败。
- 构建缓存也以来源指纹和完整目录哈希校验；发布归档与校验文件作为一对更新，失败时恢复旧版本。
