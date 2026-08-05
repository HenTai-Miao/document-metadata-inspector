# 跨平台离线文档元数据提取方案调研

> 调研日期：2026-08-05
> 目标平台：Windows、Linux、macOS
> 目标格式：PDF；Word `DOC/DOCX/DOCM/DOT/DOTX/DOTM`；Excel `XLS/XLSX/XLSM/XLSB/XLT/XLTX/XLTM`
> 本文只讨论可离线运行、可随桌面程序分发的方案，不把云 API 作为依赖。

## 结论先行

没有一个现成库能同时做到以下全部目标：覆盖所有目标格式、枚举所有原始属性、解析批注与修订、递归嵌入对象、验证数字签名、处理各种加密、保留法证来源，而且对恶意文件安全。

推荐采用“多解析器、统一证据模型”的混合方案，而不是把项目整体重写为某一种语言：

1. 保留 Python 作为桌面程序编排层和现有法证数据模型；现有 OOXML/OPC、OLE 原始结构解析继续负责“原值 + 来源位置 + 未解析项”。
2. 增加隔离的 Java 工作进程，以 Apache Tika + POI + PDFBox 作为全格式基线解析器；它们对目标 Office 家族和 PDF 的覆盖最成熟。
3. 内置 ExifTool 作为独立交叉验证器，补充 PDF、OLE、OOXML 常见属性和未知标签，但不把它当成批注/修订/签名验证引擎。
4. 对 PDF 可用 PDFBox 为主、`pikepdf`/`pypdf` 只读交叉验证；对 OOXML 继续直接读取 ZIP/XML，专门实现 Word 修订、Word/Excel 批注、签名部件、嵌入对象清单。
5. 每个平台分别构建离线安装包。接受“一个安装程序/一个应用包”，不要承诺运行时只有一个物理可执行文件；PyInstaller one-file 会在运行时解包，ExifTool 和 Java 运行时也天然包含配套文件。

若必须只保留一种运行时，第二选择是纯 Java（Tika/POI/PDFBox + JavaFX/Swing + `jpackage`）。纯 Rust 或纯 Python 都能做出较小原型，但要达到同等格式深度和证据完整度，需要重新实现大量格式规范，风险明显更高。

项目名建议从只表示 XLSX 的名称改为 `document-metadata-inspector`（产品中文名可用“文档元数据核验器”）。该名称不暗示无法兑现的“完整取证”或“身份鉴定”。

## 1. “完整元数据”应如何定义

“提取完整元数据”不能定义为“恢复文件的全部历史事实”。一个可靠、可验收的定义应是：

> 在声明支持的格式版本、密码和资源上限内，枚举文件中所有可到达且已识别的元数据承载结构；同时保留原始值、规范化值、来源部件/流/对象、解析器和告警。对未知、加密、损坏、超限、签名未验证和未递归内容明确报告，不静默丢弃。

必须区分四个层次：

- **检测**：文件真实容器、格式、是否加密、是否存在签名/宏/嵌入对象。
- **清单**：属性、批注、修订、XMP 包、OLE 属性集、关系部件、嵌入对象等位于哪里。
- **解释**：把格式专有值归一为作者、时间、应用、修订号等公共字段，但保留原值。
- **验证**：哈希/签名数学验证、证书链、信任锚、时间戳、撤销状态。检测到签名不等于签名有效，更不等于作者身份可信。

以下边界无法由任何解析器消除：

- 文件没有保存、已经清除或被重写的历史通常无法恢复。PDF 增量更新可能残留旧对象，但不能保证存在；ExifTool 也警告其 PDF 增量写入可能保留旧信息（[ExifTool PDF tags](https://exiftool.org/TagNames/PDF.html)）。
- Office 的 `RevisionNumber`/修订号只是一个属性，不等同于 Word 跟踪修订或 Excel 共享工作簿修订日志。二进制 XLS 的修订记录包含单元格、工作表、批注、冲突等多种记录，必须按专用规范解析（[MS-XLS Revision Records](https://learn.microsoft.com/en-us/openspecs/office_file_formats/ms-xls/9e91e8bc-e4f2-49b8-97d4-741481349d1b)）。
- “Comments”文档摘要属性、Word 批注、Excel 批注/备注、PDF annotation 是不同对象，不能合并成一个字符串。
- OOXML 加密时，`EncryptedPackage` 保存的是整个加密后的 ECMA-376 包；无密码只能报告加密容器和外围信息，不能声称内部元数据完整（[MS-OFFCRYPTO EncryptedPackage](https://learn.microsoft.com/en-us/openspecs/office_file_formats/ms-offcrypto/b60c8b35-2db2-4409-8710-59d88a793f83)）。
- PDF 的 XMP 不只存在于文档目录，还可附着于页面、字体、图片及任意对象；只读取目录 XMP 不算全枚举（[PDF Association：object metadata streams](https://pdfa.org/resource/pdf-2-0-application-note-003-use-of-object-metadata-streams/)）。
- 证书链/撤销状态可能需要外部信任库或网络。离线程序只能针对内置/本机信任锚与文件内材料给出验证范围；OPC 的签名校验和 X.509 证书校验本来就是两个步骤（[PackageDigitalSignatureManager.VerifySignatures](https://learn.microsoft.com/en-us/dotnet/api/system.io.packaging.packagedigitalsignaturemanager.verifysignatures)）。
- 作者、公司、最后保存者等字段是文件中的自报值，不是自然人身份的密码学证明。

## 2. 格式与承载结构

| 格式族 | 主要承载结构 | 应提取的对象 | 推荐主引擎 |
|---|---|---|---|
| PDF | Trailer/Catalog、Info dictionary、XMP metadata streams、annotations、AcroForm、EmbeddedFiles、signature dictionaries、Encrypt dictionary | Info/XMP 原值，全部可达 XMP 位置，批注/表单，嵌入文件，签名字段及验证结果，加密算法与权限 | PDFBox；原始对象遍历；pikepdf/pypdf/ExifTool 交叉验证 |
| DOC/DOT | OLE2/CFB streams、SummaryInformation、DocumentSummaryInformation、自定义属性、Word 二进制记录 | 标准/自定义 OLE 属性、作者/时间/修订属性、批注/修订能力说明、宏/嵌入流清单 | POI HPSF/HWPF + olefile 原始流清单 + ExifTool |
| DOCX/DOCM/DOTX/DOTM | OPC ZIP、`docProps/*`、WordprocessingML、关系、comments/people、signatures、embeddings、VBA | core/app/custom 属性、传统/现代批注、跟踪修订、嵌入对象、宏、数字签名部件 | 原始 OPC/XML + Tika/POI + ExifTool |
| XLS/XLT | OLE2/CFB、HPSF、Workbook BIFF、revision streams、VBA/embeddings | 标准/自定义属性、工作簿/工作表属性、批注、共享工作簿修订、隐藏项、宏/嵌入对象 | POI HPSF/HSSF + 专用 revision 解析 + olefile/ExifTool |
| XLSX/XLSM/XLTX/XLTM | OPC ZIP、`docProps/*`、SpreadsheetML、comments/threadedComments/persons、signatures、embeddings、VBA | core/app/custom 属性、传统/线程批注、工作簿/工作表元数据、宏、签名、嵌入对象 | 原始 OPC/XML + Tika/POI + ExifTool |
| XLSB | OPC ZIP + 二进制 workbook/worksheet parts | 包属性、关系、批注/工作簿信息、宏/签名/嵌入对象；二进制记录需专门读取 | Tika + POI XSSFBReader，原始 OPC 层兜底 |

OLE Property Set 标准本身包括标题、主题、作者、关键字、批注、模板、最后作者、修订号、总编辑时间、创建/保存/打印时间、页数/字数和安全性等字段（[MS-OLEPS SummaryInformation](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-oleps/f7933d28-2cc4-4b36-bc23-8861cbcd37c4)），并允许用户自定义属性集（[MS-OSHARED property sets](https://learn.microsoft.com/en-us/openspecs/office_file_formats/ms-oshared/8419d374-b2ec-49fb-b736-50dd19108910)）。因此只输出十几个“常用字段”不能视为完整。

## 3. 现成组件比较

### 3.1 Apache Tika + POI + PDFBox

这是覆盖面最广、最适合作为主基线的一组现成组件。

- Tika 的 OfficeParser/OOXMLParser 使用 POI 读取 OLE2 和 OOXML 的文本与元数据。官方格式表明确列出 Word document/template、DOCM/DOTM、Excel sheet/template、XLSM/XLTM 和 XLSB MIME；旧 DOC/XLS 由 OLE2 OfficeParser 处理（[Tika supported formats](https://tika.apache.org/3.3.2/formats.html)）。
- POI 的组件图覆盖 OLE2/POIFS、HPSF 属性集、HSSF/XLS、HWPF/DOC、OpenXML4J、XSSF/XLSX 和 XWPF/DOCX；HWPF 位于 scratchpad，官方也提示早期格式支持有限（[POI components](https://poi.apache.org/components/index.html)）。
- HPSF 能读写 OLE2 属性集，但仍有不支持的 Variant 类型，必须把未知类型作为原始证据保留而不是忽略（[HPSF guide](https://poi.apache.org/components/hpsf/index.html)，[HPSF package notes](https://poi.apache.org/apidocs/dev/org/apache/poi/hpsf/package-summary.html)）。
- POI 对 XLSB 的路径是只读、流式且标注为 experimental/internal 的 XSSFBReader，不等同于完整的 XSSF 对象模型（[POI XLSB package](https://poi.apache.org/apidocs/4.0/org/apache/poi/xssf/binary/package-summary.html)）。
- Tika 公共 Office 元数据字段包含作者、初始/最后作者、创建/保存/打印时间、自定义属性前缀、批注人员、隐藏工作表和对象计数等，但这些是归一化输出，不代替底层原值枚举（[Tika Office metadata API](https://tika.apache.org/3.2.3/api/org/apache/tika/metadata/Office.html)）。
- Tika PDF 元数据模型暴露 XMP、签名字段、嵌入文件、portfolio/collection 和 annotations 等检测结果（[Tika PDF metadata API](https://tika.apache.org/3.3.2/api/org/apache/tika/metadata/PDF.html)）。PDFBox 的 XMP 依赖 XmpBox，公钥加解密及签名/验签需要 BouncyCastle（[PDFBox dependencies](https://pdfbox.apache.org/3.0/dependencies.html)）。
- Tika app JAR 可直接 `java -jar` 运行并包含依赖，适合做隔离 sidecar，但仍需要随程序提供 Java 运行时（[Tika getting started](https://tika.apache.org/3.2.3/gettingstarted.html)）。

局限：Tika 主要提供归一化元数据和内容抽取；它不是“所有底层对象的法证转储器”。Word 跟踪修订、XLS 修订流、所有自定义命名空间、每个 PDF 对象的 XMP、Office/PDF 完整签名信任验证仍要专门实现或调用底层 POI/PDFBox。Tika 递归抽取嵌入对象很有价值，但应设置深度、数量、解压比率、单对象和总字节上限。

安全上必须把 Java 解析器放在独立低权限进程：Tika 官方明确说明解析不可信文件有风险，Tika 本身不是安全边界，并建议隔离、超时、内存限制和最小权限（[Tika security model](https://tika.apache.org/security-model.html)）。版本要跟进安全公告；例如 CVE-2025-54988 是通过 PDF XFA 触发的 XXE，受影响范围到 3.2.1（[Tika security](https://tika.apache.org/security.html)）。

许可：Tika、POI、PDFBox 均为 Apache Software Foundation 项目，使用 Apache-2.0；分发时保留 LICENSE/NOTICE 与第三方依赖声明（[POI legal](https://poi.apache.org/legal.html)，[Tika repository](https://github.com/apache/tika)，[PDFBox](https://pdfbox.apache.org/)）。

### 3.2 ExifTool

ExifTool 适合做快速属性扫描和独立交叉验证，不适合单独承担全部需求。

- 官方支持表列出 PDF 读写、DOC/DOCX/XLS/XLSX 读取；其 OOXML 模块读取包内 XML 属性，含 RevisionNumber、LastModifiedBy、TotalEditTime、DocSecurity 等（[ExifTool application docs](https://exiftool.org/exiftool_pod.html)，[OOXML tags](https://exiftool.org/TagNames/OOXML.html)）。
- PDF 模块支持 PDF 2.0、RC4/AES-128/AES-256 和 Password 选项，并可读取 Encrypt 字典及权限；但官方同页明确说明所列 PDF tags 只是全部 PDF tags 的一小部分（[ExifTool PDF tags](https://exiftool.org/TagNames/PDF.html)）。
- `-u/-U` 可输出未知标签，`-ee` 可深入部分嵌入信息，JSON 输出便于接入；这使它很适合发现主解析器遗漏，但不等于能够解释 Word 修订、Excel revision records 或验证签名。
- 官方 Windows 包带 Perl 运行时，但移动可执行文件时还必须一并移动 `exiftool_files` 目录；Unix 通常使用 Perl distribution，macOS 也提供安装包（[ExifTool installation](https://exiftool.org/install.html)，[ExifTool home](https://exiftool.org/)）。因此它可被安装程序内置，但不是严格的单文件运行时。

格式表没有逐一承诺 DOCM/DOTM/XLSM/XLSB 等所有扩展；OOXML 同构文件的 `docProps` 往往能读，但必须用每种扩展的真实样本验收，不能仅因 DOCX/XLSX 成功就宣布全部支持。ExifTool 也不应执行写操作，因为 PDF 增量写可能保留旧对象并改变证据文件。

许可：ExifTool 与 Perl 同条款分发；其发行元数据给出 Perl 5 / Artistic-1.0 或 GPL-1.0-or-later 的选择（[Image-ExifTool META](https://metacpan.org/dist/Image-ExifTool/view/META.json)，[ExifTool home](https://exiftool.org/)）。商用离线分发可行，但安装包必须携带选定许可及相应声明。

### 3.3 Python 组合：pypdf/pikepdf + olefile + 原始 ZIP/XML

这条路线最容易与现有项目融合，也最适合保留精确证据路径，但不应从零实现所有语义。

- `pypdf` 能读取 PDF Info 和 XMP（两者可同时存在）、附件、批注和加密 PDF（[pypdf metadata](https://pypdf.readthedocs.io/en/5.9.0/user/metadata.html)，[pypdf documentation](https://pypdf.readthedocs.io/en/stable/)）。其官方范围说明数字签名不是原生能力，建议使用 pyHanko（[scope of pypdf](https://pypdf.readthedocs.io/en/3.17.4/meta/scope-of-pypdf.html)）。
- `pikepdf` 基于 qpdf，能访问 XMP、DocumentInfo、附件和加密；便捷元数据 API 只覆盖常见特性，复杂 XMP 仍需读取原始 XMP。保存时默认会调整元数据，因此法证模式必须只读且禁止写回（[pikepdf metadata](https://pikepdf.readthedocs.io/en/latest/topics/metadata.html)，[pikepdf security/signatures](https://pikepdf.readthedocs.io/en/latest/topics/security.html)）。官方提供 Windows、Linux、macOS 常见架构 wheels，许可证为 MPL-2.0（[pikepdf repository](https://github.com/pikepdf/pikepdf)）。
- `olefile` 是纯 Python OLE/CFB 层，能列流和属性集/用户属性，BSD/PIL 风格许可、无外部依赖；它不是 DOC/XLS 语义解析器（[olefile repository](https://github.com/decalage2/olefile)）。
- OOXML 本质是 OPC ZIP + XML，直接读取能精确保留 `docProps`、关系、comments、threadedComments、revisions、signatures 和 embeddings 的部件路径（[Open XML SDK overview](https://learn.microsoft.com/en-us/office/open-xml/open-xml-sdk)）。Excel 线程批注还包含 author/person、mentions、parent/replies，不能退化成普通文本（[MS-XLSX threaded comments](https://learn.microsoft.com/en-us/openspecs/office_standards/ms-xlsx/e0fb917a-1107-409a-852f-13b47aea70dc)）。

优势是可复用当前项目的安全 ZIP/XML 与 provenance 逻辑；缺点是 DOC/XLS/XLSB、签名、PDF 全对象遍历都很重，维护规范实现的成本高。最佳定位是“法证原始层 + 专项解析器”，而非唯一引擎。

许可：`pypdf` 为 BSD-3-Clause（[pypdf LICENSE](https://github.com/py-pdf/pypdf/blob/main/LICENSE)）；`pikepdf` 为 MPL-2.0；`olefile` 为 BSD/PIL 风格。应生成第三方清单，并特别审查 MPL 组件是否被修改及其文件级源代码义务。

### 3.4 Rust/其他现成项目

#### Xberg（原 Kreuzberg）

[Xberg](https://github.com/xberg-io/xberg) 是目前最值得借鉴的 Rust 现成项目：其格式表声明覆盖 PDF，以及本项目要求的 Word 和 Excel 扩展（包括 DOC、DOCM、DOT、DOTM、XLS、XLSM、XLSB、XLT/XLTX/XLTM）；文档还暴露 DOCX core/app/custom properties、DOCX tracked revisions、PDF annotations/form/password 和 XLSX app properties（[Xberg API reference](https://docs.xberg.io/reference/api-dart/)）。许可证为 MIT。

可直接复用或移植的部分是：格式识别、OOXML 属性/修订解析、PDF/Office 内容抽取和测试样本设计。不能直接把它的通用 `metadata` 输出认定为法证完整结果：现有公开文档未承诺枚举所有 PDF 对象级 XMP、所有 OLEPS Variant、XLS revision streams、递归嵌入对象的原始证据、Office/PDF 签名信任验证或加密 Office 内部元数据。引入前应以本项目的“原值、来源、未知项、加密/截断状态”契约做差距测试。

#### calamine / lopdf

- [calamine](https://docs.rs/calamine/latest/calamine/) 是纯 Rust Excel 读取库，覆盖 XLS/XLSX/XLSB，能读取 sheet/cell/formula 和 VBA 工程；它不承诺 Word/PDF、Office 文档属性、签名及完整批注/修订，因此只能做 Excel 内容补充。
- [lopdf](https://docs.rs/lopdf/latest/lopdf/) 能处理 PDF 对象和基础 Info/加密信息，但文档说明仍存在加密算法等限制，常规加载还会把完整文档保存在内存中；它不是现成的完整 XMP/签名验证方案。
- Tauri 可以把外部二进制作为 sidecar 打包，但每个目标和 CPU 架构都需要对应的 sidecar 文件（[Tauri sidecar](https://v2.tauri.app/develop/sidecar/)）。它解决 UI/分发，不解决元数据引擎缺口。

纯 Rust 的主要优点是静态可执行文件和资源控制；主要缺点是格式覆盖深度。除非愿意长期维护 Office/PDF 规范实现，否则不建议现在整体重写。

## 4. 能力矩阵

符号：`●` 可作为主要能力；`◐` 有能力但不完整或需底层定制；`○` 仅检测/少量字段；`—` 不适合作为该能力来源。

| 能力 | Tika/POI/PDFBox | ExifTool | Python 原始层 | Xberg/Rust |
|---|:---:|:---:|:---:|:---:|
| 全部目标扩展的格式识别/基础抽取 | ● | ◐ | ◐ | ●/◐ |
| core/app/summary 标准属性 | ● | ● | ● | ● |
| 任意 custom properties 原值与来源 | ◐ | ◐ | ● | ◐ |
| 旧 OLE 属性集/流清单 | ● | ●/◐ | ● | ◐ |
| Word 跟踪修订 | ◐ | — | ●（需专用 XML） | ●（DOCX） |
| Word/Excel 批注及人员/回复关系 | ◐ | ○ | ●（需专用解析） | ◐ |
| XLS 共享工作簿 revision records | ◐（需底层定制） | — | ◐（实现成本高） | 未承诺 |
| PDF Info + XMP | ● | ●/◐ | ● | ●/◐ |
| PDF 全对象级 XMP | ◐（需遍历） | — | ◐（需遍历） | 未承诺 |
| 嵌入对象清单/递归解析 | ● | ◐ | ●（需编排） | ◐ |
| 宏存在性与原始部件 | ●/◐ | ◐ | ●（清单） | ◐ |
| 加密检测 | ● | ● | ● | ◐ |
| 有密码后的 PDF/Office 解密解析 | ●/◐ | PDF ● | PDF ●；Office 需另库 | ◐ |
| 签名字段/签名部件检测 | ● | ○ | ●（清单） | ◐ |
| 数学验签 + 证书/时间戳信任 | ◐（PDFBox+BC/专用实现） | — | ◐（pyHanko/专用实现） | 未承诺 |
| 原始值、对象路径、未知项法证保留 | ◐ | ◐ | ● | ◐ |
| 单一静态二进制 | — | — | —/◐ | ◐/● |

## 5. 三种产品架构方案

### 方案 A：Python 编排 + Java/ExifTool 隔离 sidecar（推荐）

组成：

- Python 桌面/UI、批量拖入、任务调度、统一证据模型、JSON/CSV/HTML 导出。
- 当前原始 OOXML/OLE 解析层负责 provenance、未知项、关系和专项修订/批注。
- Java sidecar：Tika/POI/PDFBox，负责全格式基线、递归嵌入内容、PDF 高级结构。
- ExifTool sidecar：独立属性交叉验证。
- 每个文件在无网络、低权限、只读、限时限内存的子进程中解析。

优点：最大化复用现有代码，覆盖与法证性最好；不同解析器结果可做差异告警。缺点：安装包最大，包含 Python、精简 JRE、JAR 和 ExifTool；构建/许可清单较复杂。

适合当前项目，因为核心目标是“可信、完整地报告可达元数据”，不是追求最小二进制。

### 方案 B：纯 Java 桌面程序

组成：JavaFX/Swing + POI/PDFBox/Tika，自定义 OPC/OLE/PDF 遍历，使用 `jpackage` 创建自带运行时的安装包。

优点：一套语言和对象模型，Office/PDF 生态成熟，部署时不要求用户安装 Java。缺点：需要迁移现有 Python 证据模型和安全解析逻辑；Tika 的归一化输出仍不够，专项修订/批注/证据路径仍要写。

`jpackage` 会创建自包含运行时和本机安装格式：Windows EXE/MSI、macOS PKG/DMG、Linux DEB/RPM；它不支持跨平台生成，必须在对应操作系统上构建（[Oracle jpackage packaging overview](https://docs.oracle.com/en/java/javase/25/jpackage/packaging-overview.html)，[jpackage man page](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jpackage.html)）。安装包可以是一个文件，安装后的应用仍是一个目录/应用包。

### 方案 C：Rust/Xberg 派生的本机程序

组成：Rust core + Xberg 可复用逻辑 + Tauri/原生 UI；缺失能力自行实现或继续带 Java/ExifTool sidecar。

优点：启动快、资源容易限制、可产出接近单一原生二进制的程序。缺点：一旦仍带 sidecar，“纯 Rust 单文件”优势消失；如果不带 sidecar，则 DOC/XLS/XLSB、PDF 签名/XMP、Office revision records 等深度最弱，重写成本和回归风险最高。

仅在后续已经建立覆盖所有格式与恶意样本的金标测试库，并证明 Xberg/Rust 输出满足证据契约后再考虑迁移。

## 6. 离线打包策略

推荐把“可离线使用”定义为：安装完成后无需联网、无需用户另装 Python/Java/Perl；程序及解析器只访问用户选择的本地文件。

| 平台 | 推荐产物 | 构建约束 | 关键说明 |
|---|---|---|---|
| Windows x64（可加 arm64） | 签名的 EXE/MSI 安装程序 | 在 Windows 对应架构构建 | 内置 PyInstaller 应用、精简 JRE/Tika JAR、ExifTool EXE + `exiftool_files` |
| macOS Intel/Apple Silicon | `.app` + DMG/PKG，签名/公证 | 在 macOS 构建；可分别构建或 universal UI + 双架构 sidecar | App bundle 本身是目录，不应宣传成单二进制 |
| Linux x86_64（按需 arm64） | AppImage 或 DEB/RPM | 在兼容的旧发行版/容器中构建 | 注意 glibc 基线、临时目录 `noexec`、桌面集成差异 |

PyInstaller 官方支持 Windows、macOS、Linux，但不是跨编译器，需要在每个目标系统分别构建（[PyInstaller manual](https://pyinstaller.org/en/stable/)）。其 one-file 模式会把二进制和数据解到临时 `_MEI...` 目录后运行，在 `noexec` 临时目录上还可能失败（[PyInstaller spec files](https://pyinstaller.org/en/stable/spec-files.html)，[usage notes](https://pyinstaller.org/en/stable/usage.html)）。因此建议默认使用 one-folder 放进平台安装包：启动更快、杀毒误报通常更少、sidecar 布局更诚实；如果产品要求下载物只有一个文件，就让“安装程序”单文件，而不是强行让运行时单文件。

安装包必须包含：

- 第三方 `LICENSE/NOTICE`、版本、源码主页、哈希和 SBOM。
- 每个平台/架构对应的 Java runtime、ExifTool 文件和所有本机 Python wheel；禁止启动后下载组件。
- 固定解析器版本并支持离线升级包；安全公告触发重打包。
- 启动时仅校验版本/哈希，不打印密码、文档内容或敏感属性到日志。

## 7. 安全与法证要求

输入文件一律视为不可信。最低要求：

1. **绝不执行**宏、JavaScript、OLE object、外部程序、PDF actions 或嵌入对象。
2. **不解析外链**：XML 禁止 DTD/外部实体，OPC/PDF 外部关系只记录 URI，不访问网络或本地路径。
3. **进程隔离**：每个文件或小批次使用可杀死的 worker；限制墙钟时间、CPU、RSS、输出字节、打开文件数和临时空间。
4. **递归上限**：限制 ZIP 条目数、单条目/总解压字节、压缩比、XML 深度/节点数、PDF 对象数、嵌入深度/总数；超限写入结果而不是返回“成功且无数据”。
5. **只读证据**：解析前后计算哈希；不调用 ExifTool/PDFBox/pikepdf 写入路径；临时副本与导出文件分开。
6. **密码处理**：密码仅驻留当前任务内存，不写日志/缓存/报告；错误密码、未提供密码和不支持的加密分别报告。
7. **签名结果分层**：`present`、`byte_range/intact`、`crypto_valid`、`certificate_valid_at_signing_time`、`trusted_by_selected_store`、`revocation_checked` 分开输出。
8. **来源可追溯**：每条记录至少含 `raw_name`、`raw_value/raw_bytes`、`normalized_value`、`source_kind`、`part_or_stream`、PDF object number、解析器/版本、告警；冲突值并列，不做静默覆盖。

## 8. 建议的实施顺序与验收门槛

1. 先把项目/API/包名从 XLSX 专用名称迁移为通用文档名称；保留兼容导入层或版本化输出 schema。
2. 建立格式金标样本：每个扩展至少包含标准属性、自定义属性、非 ASCII、异常日期、批注、修订、宏、嵌入、签名、无密码/有密码加密、损坏和 ZIP bomb 防护样本。
3. 接入 Tika/POI/PDFBox 只读 worker，输出原始 Tika metadata 和本项目统一模型；先完成 PDF、DOC(X/M)、XLS(X/M/B) 基线。
4. 接入 ExifTool JSON 交叉验证；只对每个样本实际支持的字段计分，不把扩展名推断当覆盖证据。
5. 扩展原始解析层：OOXML core/app/custom、Word revisions/comments、Excel legacy/threaded comments、OPC signatures/embeddings/VBA；OLEPS 全属性与未知 Variant；PDF 全对象 metadata streams。
6. 单独实现签名模块和明确的离线信任策略；不要把 Tika 的 `HAS_SIGNATURE` 当作验签结论。
7. 用差分测试统计每个解析器独有/冲突/未知字段，并把“未解析原因”纳入测试断言。
8. 在 Windows、Linux、macOS 的原生 CI/构建机分别产出安装包，断网执行同一套样本和恶意输入测试。

达到以下条件才可对外宣称“支持”某格式：

- 真实格式检测不依赖后缀；正常、损坏、加密三类样本行为有断言。
- 标准/自定义属性、批注、修订、嵌入、宏、签名、加密每项均明确为“完整解析 / 仅检测 / 不支持”。
- 所有输出可追溯到部件/流/对象；所有截断、未知和错误显式可见。
- 三个平台断网运行，不依赖系统预装 Python/Java/Perl。
- 恶意样本无法联网、执行代码、无限递归、耗尽磁盘/内存或覆盖原文件。

## 最终推荐

本项目应改造成通用的 `document-metadata-inspector`，但技术上不宜一次性推倒重写。采用方案 A：**Python 证据编排 + 原始 OOXML/OLE/PDF 专项解析 + 隔离的 Apache Tika/POI/PDFBox + ExifTool 交叉验证**。它最符合“多格式、离线、跨平台、尽量完整且能解释缺口”的目标。

交付形式应是 Windows、Linux、macOS 各自的一个离线安装包/应用包，而不是承诺不现实的跨平台单二进制。报告中将“完整”表述为“在声明范围和资源上限内，完整枚举可达且已识别的元数据结构，并显式报告未知/加密/超限项”，这样才可测试、可审计，也不会误导使用者。
