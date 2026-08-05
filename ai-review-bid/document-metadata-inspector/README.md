# Document Metadata Inspector（文档元数据核验器）

离线提取、核验并对比 PDF、Word、Excel 文件元数据的取证型工具。核心命令行功能已经实现，桌面界面将在核心能力稳定后单独设计。

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

每个平台必须在对应操作系统上原生构建，因为 PyInstaller 不是跨平台编译器。发布树会内置：

- 当前平台的 Python 应用及解释器；
- 经 `jlink` 裁剪的 Temurin/OpenJDK 21；
- Apache Worker 的 shaded JAR；
- macOS/Linux 私有 Perl 5.44.0 + ExifTool 13.55，或 Windows 官方独立 ExifTool 13.55；
- 全部运行时文件的 SHA-256 清单和第三方许可说明。

生成的程序会先做真实 PDF、DOCX、XLSX 离线自检，验证三条解析链和源文件哈希均正常，才生成 `SHA256SUMS`。详细步骤见 [docs/packaging.md](docs/packaging.md)。

当前平台一键构建与归档：

```bash
uv run python scripts/build_release.py --mode onefile
uv run python scripts/package_release.py
```

## 安全边界

- 输入文件一律视为不可信；ZIP/OLE/XML/PDF 读取均有大小、条目、时间和内存预算。
- Java Worker 另有进程树 RSS、输出大小、嵌入深度/数量/累计字节上限，并在整个 JVM 内禁止 URL、HTTP 客户端、DNS、Socket、监听和组播；超限会终止整个工作进程并明确标记，不返回伪完整结果。
- 不执行宏、脚本、嵌入对象或外部关系，不联网解析文档内容。
- 批注正文不进入报告，只保留字符数和 SHA-256；作者、日期、修订类型等取证字段保留。
- 扫描前后复核源文件大小、时间和 SHA-256，检测扫描期间被替换或修改的文件。
- 发布模式绝不回退到系统 Java、Perl 或 ExifTool；内置文件哈希不匹配时直接失败。
- 构建缓存也以来源指纹和完整目录哈希校验；发布归档与校验文件作为一对更新，失败时恢复旧版本。
