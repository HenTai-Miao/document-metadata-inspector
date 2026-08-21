# 文档元数据核验核心设计

## 状态与范围

- 日期：2026-08-05
- 已确认项目名：`document-metadata-inspector`
- 已确认 Python 包名：`document_metadata_inspector`
- 已确认命令名：`docmeta`
- 本阶段只实现无界面的功能核心、命令行和报告导出。
- 桌面 GUI、HTTP 服务、数据库和云服务均不在本阶段。
- 修改范围严格限定为当前 `xlsx-metadata-forensics/` 目录；目录最终在父目录内重命名为 `document-metadata-inspector/`。

## 目标

把现有 Excel 专用、尚不可运行的 Python 项目演进为跨格式文档元数据核验核心。它必须在完全离线的前提下批量读取 PDF、Word、Excel 文件，完整枚举声明范围内仍然存在且可验证的元数据结构，保留原始值和证据来源，并对作者相关痕迹做可解释的跨文件比对。

“完整”采用以下可验收定义：在支持的格式、正确密码和资源上限内，枚举所有可到达且已识别的元数据承载结构；对未知、加密、损坏、超限、解析器冲突和未验证签名显式报告。项目不承诺恢复已经删除的历史、不破解密码，也不把自报作者字段解释为自然人身份的证明。

## 支持格式

- PDF：`.pdf`
- Word：`.doc`、`.docx`、`.docm`、`.dot`、`.dotx`、`.dotm`
- Excel：`.xls`、`.xlsx`、`.xlsm`、`.xlsb`、`.xlt`、`.xltx`、`.xltm`

CSV、RTF、ODS、WPS ET/ETT 和 PowerPoint 不在本阶段。文件真实格式必须由容器、MIME、魔数和内部结构共同确认，不能只相信扩展名。

## 架构

### 1. Python 证据编排核心

Python 3.12 继续作为公共 API、任务编排、统一模型、比对和导出层。现有安全 OPC/ZIP、XML、OLE 读取逻辑保留并修复，不立即推倒重写。

公共入口：

```python
scan_documents(request: ScanRequest) -> ScanReport
compare_documents(request: CompareRequest) -> ComparisonReport
export_report(report: ScanReport | ComparisonReport, target: ExportTarget) -> Path
```

所有公共模型不可变、拒绝未知字段并可稳定序列化。任何引擎的私有异常都必须在边界转换为稳定错误或告警。

### 2. 原始结构解析器

原始解析器负责保留法证来源和当前项目已有的安全边界：

- OOXML/OPC：`docProps/*`、关系、Word 批注与修订、Excel 普通/线程批注、签名、嵌入对象、VBA/ActiveX 存在性和未知部件清单。
- OLE/CFB：目录、SummaryInformation、DocumentSummaryInformation、自定义属性集、Office 主流身份、加密标识、嵌入流和未知属性类型。
- PDF：Info dictionary、Trailer ID、Catalog、可达 XMP metadata streams、annotations、AcroForm、EmbeddedFiles、signature dictionaries、Encrypt dictionary 和增量更新迹象。

解析器只读源文件，不执行宏、JavaScript、PDF action、公式、OLE 对象或外部关系。

### 3. Apache Java Worker

独立 Java 工作进程内固定版本集成 Apache Tika、POI、PDFBox 和签名所需的受控依赖。它负责：

- 真实格式和 MIME 基线识别；
- PDF、Word、Excel 的标准/自定义属性；
- DOC/DOCX、XLS/XLSX 的批注、嵌入对象和可用修订信息；
- PDF annotations、XMP、附件、加密、权限和签名字段；
- 递归嵌入文档的独立元数据。

Worker 使用逐行 JSON 请求/响应协议，通过标准输入接收任务，通过标准输出只返回结构化结果；日志写标准错误且不得包含密码、正文或敏感属性值。每个任务有墙钟时间、堆内存、输出字节和递归预算，超限后可被主进程终止。

### 4. ExifTool Worker

内置、固定版本和哈希的 ExifTool 只运行读取命令。调用时启用重复标签、未知标签、分组来源、嵌入信息和 JSON 输出。其职责是补充或交叉验证原始标签，而不是解释 Word 修订、Excel revision records 或验证签名。

运行时禁止写入参数；源文件分析前后都计算 SHA-256，任何变化视为严重失败。

### 5. 合并器

合并器不采用“最后写入覆盖”。每个观察值独立保留：

```text
canonical_name
raw_name
raw_value 或 raw_bytes_sha256
normalized_value
value_type
source_kind
part_stream_or_object
parser_name / parser_version
status
warnings
```

相同来源和值去重；不同来源的相同规范值并列保留并建立 corroboration 关系；冲突值全部保留并产生 `parser_value_conflict` 告警。任何解析器失败都不会伪装成空字段成功。

## 统一报告模型

### 文件身份

- 显示名、绝对路径的安全摘要、文件大小、SHA-256；
- 声明扩展名、实际格式、MIME、容器类型；
- 是否加密、是否需要密码、解析完整状态；
- 每个解析器的名称、版本、开始/结束状态和预算使用量。

### 规范元数据

- 作者、最后修改者、公司、经理、应用及版本；
- 创建、修改、打印、签名和批注时间；
- 标题、主题、说明、关键词、类别、语言、标识、模板；
- 修订号、编辑时长、页数/字数/工作表数等格式适用统计；
- 所有自定义属性及未知属性。

每个时间保留原字符串、解析后的时间、原时区信息和时区是否推断。没有时区时不得猜测本地时区。

### 取证证据

- Word/Excel/PDF 批注或 annotation 的作者、时间、位置和回复关系；默认不导出正文，仅保留正文哈希和长度。
- Word 跟踪修订的作者、时间、类型、位置和数量；默认不导出正文。
- PDF 的全部可达 XMP、Trailer ID、增量更新、表单、附件、签名和权限。
- Office 的宏、ActiveX、外部关系、隐藏表、嵌入对象、签名部件和路径痕迹。
- 嵌入对象只记录身份、类型、大小和哈希；递归解析使用独立子报告并受深度限制。

### 签名状态

签名结果必须分层表示：`present`、`byte_range_intact`、`crypto_valid`、`certificate_valid_at_signing_time`、`trusted_by_selected_store`、`revocation_checked`。检测到签名不能简化为“签名有效”。

## 作者痕迹比对

比对只处理身份相关的可解释字段：作者、最后修改者、批注/修订作者、公司、经理、应用/版本、模板、签名者证书标识和可确认的用户名路径痕迹。

规范化规则：Unicode NFKC、首尾空白清理、连续空白折叠和大小写无关匹配；原值始终保留。不进行拼音、模糊人名或语义猜测，避免把不同人员误合并。

输出按规范值分组，列出涉及的文件、字段、原值、来源和证据数量。默认高亮至少出现在两个不同文件中的完全匹配值。结果使用“相同元数据痕迹”，不输出“同一作者”或串标定性结论。

## 密码与加密

- CLI 支持对单文件从安全终端提示读取密码，也支持调用方传入内存密码提供器。
- 禁止命令行明文密码参数，避免进入 shell history 和进程列表。
- 密码不得写入日志、缓存、报告或临时文件；任务结束后释放引用。
- 未提供密码、密码错误、不支持的加密算法分别返回稳定状态。
- 无密码时仍报告能够从外围容器可靠确认的格式、大小、哈希和加密信息，但完整状态必须为 `encrypted_unreadable`。

## CLI

```text
docmeta scan FILE... --json REPORT.json
docmeta compare FILE... --json REPORT.json
docmeta export REPORT.json --format xlsx|html --output TARGET
docmeta verify
```

- `scan` 和 `compare` 接受多个文件或目录；目录默认不递归，显式 `--recursive` 才递归。
- 标准输出只输出机器可读 JSON 或简洁进度；错误写标准错误并使用稳定退出码。
- 单个文件失败不丢弃其他文件结果；命令只有在全部文件成功或明确允许部分成功时才返回零。
- `verify` 在断网模式下生成受控样本并真实调用三类解析器，输出逐项 PASS/FAIL。

## 导出

- JSON 是无损权威格式，包含完整证据、冲突、错误和解析器状态。
- XLSX 是人工审阅格式，包含文件汇总、规范属性、作者痕迹、原始标签、取证证据、错误告警和覆盖状态工作表。
- HTML 是单文件只读报告，内嵌样式和数据，不引用网络资源。
- 导出使用临时文件后原子替换目标；不得覆盖输入文件，输出路径与任一输入相同则拒绝。

## 安全和资源预算

- 输入一律视为不可信，解析器默认无网络。
- 限制文件大小、ZIP/OLE 条目数、单部件和累计读取量、XML 深度/节点数、PDF 对象数、嵌入深度/数量/总字节、Worker RSS、墙钟时间和输出大小。
- XML 禁止 DTD、外部实体和外部 schema；外部 URI 只记录不访问。
- Worker 使用任务级临时目录，完成后清理；源文件只读打开。
- 解析前后校验 SHA-256；报告中记录是否一致。
- 超限是显式 `partial` 或失败，不能静默返回空结果。

## 运行时依赖策略

- 最终用户机器不要求预装 Python、Java、Perl、Microsoft Office、LibreOffice 或 ExifTool。
- Windows、macOS、Linux 安装包分别内置 Python 应用、精简 Java 21 运行时、Apache Worker JAR、ExifTool 平台资源和全部本机 Python 依赖。
- 正式程序启动时只解析安装包内的组件清单并校验版本与 SHA-256；缺失或损坏时返回明确的安装损坏错误，不在离线用户机器上尝试联网下载。
- 开发/构建脚本先检测项目内固定资源和本机工具；缺失时可在构建机联网下载固定版本、校验官方来源与哈希后写入项目构建缓存。
- 生产解析始终优先使用随包资源，避免用户机器上不同版本的系统工具造成结果漂移；系统工具只允许作为显式开发模式回退。

## 错误模型

稳定错误至少包括：`unsupported_format`、`format_mismatch`、`invalid_document`、`encrypted_document`、`password_required`、`wrong_password`、`unsupported_encryption`、`corrupt_container`、`unsafe_document`、`resource_limit_exceeded`、`parser_timeout`、`parser_crashed`、`parser_output_invalid`、`source_changed`、`export_failed` 和 `internal_error`。

错误对象只包含稳定消息、文件显示名、解析阶段和安全统计，不包含密码、正文、完整本地路径或原始异常堆栈。

## 测试与验收

1. 先修复当前测试收集失败、Ruff、格式化、类型检查和缺失 CLI，建立可运行基线。
2. 每种扩展至少有真实或受控夹具，覆盖非 ASCII 属性、异常日期、自定义属性、批注、修订、嵌入、宏、签名、加密、损坏和超限。
3. 每个功能按 RED → GREEN → 重构实现；修复前先有能够证明缺陷的测试。
4. 差分测试记录三个解析器各自独有、相同和冲突的字段；未知项与未解析原因也是断言的一部分。
5. CLI 端到端测试真实启动 Worker，验证批量部分失败、密码提示、退出码和报告可反序列化。
6. 所有夹具分析前后 SHA-256 一致；测试证明没有网络、宏、脚本、公式或外部对象执行。
7. `pytest`、Ruff、BasedPyright、Java 单元测试、依赖锁检查、构建和离线 `verify` 全部通过。
8. 只有格式识别、正常/损坏/加密行为、字段覆盖矩阵、来源追溯和安全上限都有真实测试后，才宣称支持该格式。

## 迁移和保留策略

- 先在当前目录内建立新包和兼容层，修复当前基线；在功能测试通过前不删除现有 Python 源码和测试。
- 新的 `document_metadata_inspector` 成为唯一公共包；旧 `xlsx_metadata_forensics` 暂时只提供弃用兼容导入，稳定迁移后再由用户确认删除。
- 现有丰富但未填充的 `ForensicInfo` 模型转为新证据模型的输入，不再用空列表伪装支持。
- 当前 FastAPI、Uvicorn、openpyxl 等未被生产功能使用的依赖在确认无引用后移出运行依赖；测试夹具需要的依赖放开发组。
- 当前用户未提交、已暂存和未跟踪文件全部视为用户资产，迁移时按文件保留，不进行 reset、checkout、stash 或破坏性删除。

## 本阶段完成标准

- 项目和公共包使用新的通用名称，旧导入保持兼容。
- CLI 能批量扫描、比较和导出 PDF、Word、Excel 的受控样本。
- 三类解析来源均接入，或在缺少可选 Worker 时显式报告不可用而不伪装完整成功。
- 所有观察值包含来源、解析器、原值/规范值和状态；冲突不丢失。
- 作者痕迹比对无模糊猜测且可追溯。
- 密码只在内存中使用，源文件分析前后哈希一致。
- 当前 Python 测试和新增核心测试通过；静态检查和构建门禁通过。
- 桌面 UI 未加入核心层，未来只通过公共 API 调用。

## 已确认决策

- 仅修改本项目，不修改工作区其他项目。
- Windows、Linux、macOS 分别构建离线包。
- 桌面 GUI 后置，功能核心优先。
- 使用 Python 证据编排、Apache Java Worker 和 ExifTool 混合架构。
- 完整度优先于安装包体积。
- 加密文件支持安全密码提示，不破解密码。
- 最终用户零依赖安装；解析运行时和工具全部随平台安装包提供。
