# Java Worker 从 JDK 21 降至 JDK 17 的兼容性评估

> 调研日期：2026-08-10
> 范围：`java-worker/`、依赖与 Maven 插件、Python Worker 启动边界、JRE 裁剪、离线打包、CI、测试及现行文档
> 来源边界：只采用 OpenJDK/Oracle Java、Apache Tika/POI/PDFBox、Maven、Adoptium 及各依赖项目的官方文档或官方源码。为验证 Java 17，曾临时修改两处 `List` 调用；测试后已还原，运行代码和配置未留下变更。

## 结论先行

**技术上可以从 JDK 21 降至 JDK 17，工作量较小，但当前仓库不能原样在 JDK 17 上构建。**

源码和本机打包的直接阻点有三类：

1. `java-worker/pom.xml:14` 把 `maven.compiler.release` 固定为 `21`。
2. 生产代码和测试各有一个 Java 21 才加入的 `List.getFirst()`；改为 `get(0)` 后即可按 Java 17 编译。`Deque.getFirst()` 不是阻点。
3. `scripts/prepare_platform_resources.py:146` 使用 JDK 17 不接受的 `jlink --compress=zip-6`；应改成 JDK 17 官方支持、语义同为 ZIP 压缩的 `--compress=2`。

依赖和 Maven 插件没有要求 Java 21。临时兼容改动后，真实 JDK 17 上 Maven 的 9 个 Java 测试全部通过，98 个解析/运行依赖 JAR 未发现 class major version 高于 Java 17 的 61；使用裁剪后的 JDK 17 运行时，Python 到 Java Worker 的 PDF、DOCX、XLSX、XLS 四个真实集成测试也全部通过。

**产品发布另有一个当前不能由代码修改解决的阻点：** 仓库 JDK 源清单覆盖 Windows、Linux、macOS 的 arm64/x86_64 六组 Temurin JDK，而 Temurin 17.0.20+8 官方 release 资产有 Linux arm64/x86_64、macOS arm64/x86_64 和 Windows x86_64，未提供 Windows arm64（[Temurin 17.0.20+8 release](https://github.com/adoptium/temurin17-binaries/releases/tag/jdk-17.0.20%2B8)）。当前 CI 实际发布四组（Linux x86_64、Windows x86_64、macOS arm64/x86_64），这四组可迁；但在不换厂商、不取消 Windows ARM64、也不做混合 JRE 版本的前提下，**当前无法保持仓库声明的六平台能力完全等价**。

不过，**不建议仅以“后端优化”为理由立即降级**：产品本来就内置 JRE，降级不会降低终端机器的 Java 前置条件。同为 Oracle、同模块的本机 macOS arm64 探针从 JDK 21 的 51,000 KiB 降至 JDK 17 的 46,400 KiB，约节省 4,600 KiB（9.0%）；相对于当前 197,104 KiB 的整棵平台运行时，只约占 2.3%。仓库现有 Temurin 21 JRE 为 53,300 KiB，但不能把它与 Oracle 17 直接当作同厂商基准。当前还没有三平台、同厂商同补丁周期的安装包体积、启动、RSS 和吞吐对比。与此同时，Adoptium 当前公布的 Temurin 17 可用更新至少到 2027-10，Temurin 21 至少到 2029-12，降级会缩短约两年的社区更新窗口（[Adoptium support](https://adoptium.net/support/)）。

建议采用条件决策：

- 如果目的只是让 Worker 兼容 JRE 17，优先把源码和字节码目标改为 17、在 CI 同时测试 17/21，但继续随包交付 Temurin 21；这样能先获得向后兼容性，不牺牲生产运行时支持窗口和 Windows ARM64。
- 如果部署规范明确只允许 JDK 17，或最终获批平台矩阵的受控基准证明体积收益达到产品门槛，可以迁移。
- 如果没有外部 JDK 17 约束，且目的只是笼统的“优化”，继续使用 JDK 21 更稳妥；先完成受控基准再决定。
- 如果 Windows ARM64 是必须交付的平台，应先决定保留该平台的 JDK 21、改用经审查的 JDK 17 厂商，还是暂停整体迁移；不能假造缺失的 Temurin 17 资产或跳过哈希固定。

## 1. 当前版本约束清单

| 范围 | 当前约束 | 降至 17 的影响 |
|---|---|---|
| 编译 | `java-worker/pom.xml:14` 为 `release=21` | 必须改为 17，否则 JDK 17 报“不支持发行版本 21” |
| 语言/API | `TikaExtractor.java:123`、`TikaExtractorTest.java:97` 使用 `List.getFirst()` | 两处改为 `get(0)` |
| 依赖 | Tika 3.3.2、POI 5.5.1、PDFBox 3.0.8、Jackson 2.20.1 等 | 无需为 JDK 17 降依赖版本 |
| Maven | Wrapper 3.3.4 下载 Maven 3.9.11；compiler 3.14.1、Surefire 3.5.4、Shade 3.6.1 | 均可在 JDK 17 运行 |
| 运行时清单 | `tools/manifest.json` 固定 Java major 21、Temurin `21.0.12+8` 和六个平台归档/哈希 | Temurin 17.0.20+8 只有所需六组中的五组；Windows arm64 需先做产品/厂商决策 |
| JRE 裁剪 | `--compress=zip-6`；固定十个 Java 模块 | 压缩参数必须改为 `2`；现有模块在 JDK 17 均存在 |
| 运行时校验 | `resources.py` 校验 exact major、vendor、runtime version | 逻辑可复用，但 manifest 不能残留 21 |
| CI | 两个 `setup-java` 步骤固定 `21.0.12+8` | 统一目标时都切到同一 exact JDK 17；混合目标时按平台显式区分 |
| 文档/声明 | `AGENTS.md`、`README.md`、`docs/packaging.md`、`tools/README.md`、`THIRD_PARTY_NOTICES.md` 声明 Java 21 | 实施迁移时同步更新；历史设计/计划文档宜保留并补充替代决策 |

## 2. 语言与 JDK API

### 2.1 确认的 Java 21 阻点

[JEP 431: Sequenced Collections](https://openjdk.org/jeps/431) 在 Java 21 交付，并为 `List` 增加了 `getFirst()`/`getLast()`。JEP 也明确展示，Java 21 以前读取 `List` 首元素的惯用方式是 `list.get(0)`。

| 位置 | 接收者静态类型 | JDK 17 结论 | 修改 |
|---|---|---|---|
| `java-worker/src/main/java/io/docmeta/worker/TikaExtractor.java:123` | `List<Metadata>` | `List.getFirst()` 不存在 | `documents.get(0)` |
| `java-worker/src/test/java/io/docmeta/worker/TikaExtractorTest.java:97` | `List<EmbeddedResource>` | `List.getFirst()` 不存在 | `embeddedResources().get(0)` |
| `java-worker/src/main/java/io/docmeta/worker/BoundedEmbeddedDocumentExtractor.java:91` | `Deque<String>` | 可用；JDK 17 的 `Deque` 已定义 `getFirst()` | 不改 |

`Deque.getFirst()` 的兼容性可由 [Java 17 `Deque` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Deque.html#getFirst()) 直接确认，不能机械地替换仓库内所有 `getFirst()`。

### 2.2 其余语法/API

源码中的 record、文本块、switch 表达式分别在 Java 16、15、14 成为正式特性（[JEP 395](https://openjdk.org/jeps/395)、[JEP 378](https://openjdk.org/jeps/378)、[JEP 361](https://openjdk.org/jeps/361)）；`Stream.toList()` 自 Java 16 提供，`HexFormat` 自 Java 17 提供（[Java 17 Stream API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#toList())、[Java 17 HexFormat API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HexFormat.html)）。因此两处 `List.getFirst()` 修正后，当前源码的自然最低版本就是 Java 17。

POM 应继续使用 `maven.compiler.release`，而不是只设置 `source`/`target`。Maven Compiler Plugin 官方说明 `--release` 会同时约束语言、目标 class 版本和目标 JDK 的公开 API，可防止再次误用 17 不存在的 API（[Compiler Plugin 3.14.1 `--release`](https://maven.apache.org/plugins-archives/maven-compiler-plugin-3.14.1/examples/set-compiler-release.html)；[JDK 17 `javac --release`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html#option-release)）。

## 3. 依赖兼容性

| 依赖 | 仓库版本 | 官方最低版本证据 | JDK 17 结论 |
|---|---:|---|---|
| Apache Tika | 3.3.2 | 官方源码把 compiler source/target/release 设为 11（[Tika 3.3.2 parent POM](https://github.com/apache/tika/blob/3.3.2/tika-parent/pom.xml#L275-L278)） | 兼容 |
| Apache POI | 5.5.1 | 官方首页说明 4.0.1 起要求 Java 8 或更高（[Apache POI](https://poi.apache.org/)） | 兼容 |
| Apache PDFBox | 3.0.8 | 3.0 迁移文档说明最低 Java 8（[PDFBox 3.0 migration](https://pdfbox.apache.org/3.0/migration.html)） | 兼容 |
| Jackson Databind | 2.20.1 | 官方兼容表说明 Jackson 2.x 基线为 JDK 8（[jackson-databind compatibility](https://github.com/FasterXML/jackson-databind#compatibility)） | 兼容 |
| JUnit Jupiter | 5.14.1 | 官方 overview 说明运行时需要 Java 8 或更高（[JUnit 5.14.1](https://docs.junit.org/5.14.1/overview.html#supported-java-versions)） | 兼容 |
| Log4j 2 | 2.24.3 | 官方安装文档说明 Log4j 2 运行时最低 Java 8（[Log4j installation](https://logging.apache.org/log4j/2.x/manual/installation.html#java-requirements)） | 兼容 |
| SLF4J | 2.0.18 | 官方 FAQ 说明 2.0.x 要求 Java 8（[SLF4J requirements](https://www.slf4j.org/faq.html#requirements)） | 兼容 |
| Bouncy Castle `jdk18on` | 1.85（传递依赖） | 官方下载页说明 `jdk18on` 表示 JDK 1.8 及以上，不是 Java 18（[Bouncy Castle Java](https://www.bouncycastle.org/download/bouncy-castle-java/)） | 兼容 |

除官方最低版本外，本次还扫描了实际解析出的 98 个依赖 JAR，未发现 class major version 大于 61（Java 17）。这能排除当前锁定依赖图中隐藏的 Java 21 字节码，但依赖升级后仍应在 CI 重复扫描和真实启动测试。

## 4. Maven 与插件

`java-worker/.mvn/wrapper/maven-wrapper.properties` 固定 Maven 3.9.11。Maven 官方版本历史说明 3.9.x 的运行最低要求是 Java 8（[Maven release history](https://maven.apache.org/docs/history.html)）。

| 插件 | 版本 | 官方系统要求 | JDK 17 结论 |
|---|---:|---|---|
| Maven Compiler Plugin | 3.14.1 | Maven 3.6.3、JDK 8（[plugin info](https://maven.apache.org/plugins-archives/maven-compiler-plugin-3.14.1/plugin-info.html#system-requirements)） | 兼容 |
| Maven Surefire Plugin | 3.5.4 | Maven 3.6.3、JDK 8（[plugin info](https://maven.apache.org/surefire-archives/surefire-3.5.4/maven-surefire-plugin/plugin-info.html#system-requirements)） | 兼容 |
| Maven Shade Plugin | 3.6.1 | Maven 3.6.3、JDK 8（[plugin info](https://maven.apache.org/plugins-archives/maven-shade-plugin-3.6.1/plugin-info.html#system-requirements)） | 兼容 |

在临时修正 `release` 和两处 List API 后，仓库 Maven Wrapper 在真实 JDK 17 上完成编译、Surefire 测试和 shaded JAR 打包，说明当前插件组合不存在只在文档层面“看似兼容”的阻点。

## 5. 运行时与离线打包

### 5.1 manifest 和运行时解析

`tools/manifest.json` 同时固定：Worker 的 `java_major_version=21`、exact runtime `21.0.12+8`、厂商 `Eclipse Adoptium`，以及 `darwin/linux/windows × arm64/x86_64` 六个 Temurin JDK 归档和 SHA-256。`src/document_metadata_inspector/resources.py` 会核对 exact major、vendor 和 runtime version。因此迁移不是只改 POM；这些值必须按选定的 JRE 策略原子更新，否则打包或启动会拒绝新的 JRE。

这里存在发布矩阵缺口：Temurin 17.0.20+8 官方 release 当前没有 Windows arm64 JDK 资产。可选方向只有显式取舍：取消 Windows ARM64 17 包、让该平台暂留 21 并把 manifest/验证模型改为按平台表达版本，或评估另一家提供 Windows ARM64 JDK 17 的厂商。后两项都会扩大测试、许可证和供应链范围，不能作为本次“小版本优化”的隐含改动。

`scripts/bootstrap_jdk.py` 和 `scripts/build_release.py` 的实质检测流程由 manifest 驱动，可继续使用；前者模块注释中的“JDK 21”及 `scripts/prepare_platform_resources.py:136` 的错误消息需要同步改成 17 或中性措辞。

### 5.2 `jlink`

当前固定的十个模块在 JDK 17 都存在。对临时 Java 17 shaded JAR 运行 `jdeps --multi-release 17 --print-module-deps --ignore-missing-deps` 得到：

```text
java.base,java.compiler,java.desktop,java.naming,java.net.http,java.scripting,
java.security.jgss,java.sql,java.xml.crypto
```

这与当前 Java 21 JAR 的静态模块结果相同；脚本额外保留 `jdk.crypto.ec`，应继续保留以支持 EC 加密提供者。

真正的 JDK 17 打包阻点是压缩参数。JDK 17 官方只定义 `--compress={0|1|2}`，其中 `2` 是 ZIP（[JDK 17 `jlink`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jlink.html#options)）。实测 JDK 17 对 `zip-6` 报 `Invalid compression level zip-6`，改为 `--compress=2` 后成功生成运行时并启动 Worker。

本机 macOS arm64 的同厂商 Oracle 探针中，同模块 JRE 从 JDK 21 的 51,000 KiB 降到 JDK 17 的 46,400 KiB，约减少 9.0%。仓库现有 Temurin 21 JRE 是 53,300 KiB，但它与 Oracle 17 不是严格可比样本。该探针只证明“存在有限体积收益的可能”，不能外推至 Windows/Linux 安装包，也不能证明启动、内存或解析吞吐更优。

### 5.3 CI 与文档

`.github/workflows/build-offline-releases.yml` 的 quality 和 release 两个 job 都固定 `21.0.12+8`。如果目标矩阵统一为 17，两处必须一起换成 manifest 选定的 exact Temurin 17；如果 Windows ARM64 暂留 21，则 CI 与 manifest 需要明确表达按平台版本，不能用一个全局 major 掩盖差异。发布仍须在 Windows、Linux、macOS 原生构建，因为最终产物包含平台专用运行时。

实施后应更新 `AGENTS.md`、`README.md`、`docs/packaging.md`、`tools/README.md` 和 `THIRD_PARTY_NOTICES.md`。`docs/superpowers/specs/` 与 `docs/superpowers/plans/` 是历史设计记录，不建议无差别改写；可保留原文并由本报告或单独决策记录说明后续变更。

## 6. 测试与安全边界

### 6.1 已完成的临时验证

| 验证 | 结果 |
|---|---|
| 当前 HEAD 直接在 JDK 17 执行 Maven verify | 失败：POM 请求 release 21；符合预期 |
| 仅覆盖 `maven.compiler.release=17` | 失败：生产代码的 `List.getFirst()` 不存在；定位到真实 API 阻点 |
| 临时把两处 List 调用改为 `get(0)`，按 release 17 verify | 成功：9/9 JUnit 测试通过，shaded JAR 构建成功 |
| 98 个实际依赖 JAR 的 class major 扫描 | 全部 `<=61` |
| 现有模块集 + JDK 17 `jlink --compress=2` | 成功生成并启动裁剪运行时 |
| 裁剪 JRE + 临时 Java 17 JAR + Python 真实 Worker 集成 | 成功：PDF、DOCX、XLSX、XLS 4/4 通过 |

这些验证证明了主链路的兼容性，但尚不等于发布验收：还没有在最终获批的平台/架构矩阵生成离线包，也没有完成冻结应用前后的 `docmeta verify`、全量 Python 质量门禁、受控性能基准及完整恶意/加密样本回归。当前四平台 CI 可迁，不代表缺少 Temurin 17 Windows arm64 资产的六平台能力已被验证。

### 6.2 网络拒绝边界

Worker 通过 `NetworkAccessDeny` 安装 URL handler 和 `SecurityManager`，阻断 URL、socket、DNS、listen、accept 和 multicast；Python 启动命令及 Surefire 都传入 `-Djava.security.manager=allow`。JDK 17 已把 `SecurityManager` 标记为 deprecated for removal；当前显式 `allow` 参数下的动态安装已由真实 JDK 17 测试验证，应继续保留（[Java 17 `SecurityManager`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/SecurityManager.html)、[Java 17 `System.setSecurityManager`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#setSecurityManager(java.lang.SecurityManager))、[JEP 411](https://openjdk.org/jeps/411)）。

临时 JDK 17 Maven 验证中的网络拒绝测试通过，生产参数下的裁剪运行时也能完成四类真实文档集成。因此降至 17 没有破坏现有边界。反过来，这也不应被解释为 `SecurityManager` 已成为长期方案：JDK 24 已永久禁止启用它，而 JDK 21 是此变化前最后一个 LTS；降到 17 不会消除这项架构债，只会缩短受支持运行时窗口（[JEP 486](https://openjdk.org/jeps/486)）。Tika 官方也明确说明它自身不是安全边界，处理不可信输入仍需要进程隔离、资源限制和最小权限（[Tika security model](https://tika.apache.org/security-model.html)）。迁移时不得删除网络回归测试或放宽 Python 子进程边界。

## 7. 建议的迁移清单

若决定迁移，建议按以下顺序做一个独立变更，不夹带依赖升级：

1. **源码与编译目标**
   - 只把两处 `List.getFirst()` 改为 `get(0)`，保留 `Deque.getFirst()`。
   - 把 `maven.compiler.release` 改为 17；继续依赖 `--release` 防止 API 越界。
2. **精确运行时清单**
   - 选择一个仍受支持的 exact Temurin 17 补丁版本。
   - 先决定 Windows ARM64：取消该目标、暂留 JDK 21，或审批另一厂商；Temurin 17.0.20+8 不能填满当前六平台矩阵。
   - 对最终支持的每个平台同时更新 Java major/runtime/vendor 校验及 JDK URL、文件名、SHA-256；不允许运行时下载或系统 Java fallback。
3. **JRE 裁剪与脚本**
   - 把 `--compress=zip-6` 改为 `--compress=2`。
   - 保持当前模块白名单及 `jdk.crypto.ec`；更新硬编码的 JDK 21 文案。
4. **CI、测试夹具与文档**
   - 统一目标时 quality/release 两个 job 使用同一 exact Temurin 17；混合目标时显式增加平台版本矩阵。
   - 更新 `test_runtime.py`、`test_tool_resources.py`、`test_bootstrap_jdk.py` 中的 21 版本夹具/断言。
   - 更新现行使用文档、维护指南和第三方声明；历史计划保留历史语义。
5. **发布前门禁**
   - JDK 17 Maven verify、class major 扫描、`jdeps`/`jlink`、网络拒绝测试。
   - 全量 `uv run pytest`、Ruff、BasedPyright、lock/build 门禁。
   - 对最终获批的平台/架构矩阵做原生离线构建；断网启动并执行 `docmeta verify`。
   - 对正常、损坏、加密、嵌入、资源超限和联网尝试样本做回归，确认错误码、JSON 协议和证据模型不变。
6. **受控优化验收**
   - 用同厂商、同补丁周期、相同模块和相同压缩策略比较 17/21 的 JRE、最终安装包、冷启动、RSS、PDF/Office 吞吐。
   - 预先定义体积或性能门槛；未达门槛且无部署硬约束时回到 JDK 21。

## 8. 最终决策建议

| 决策情形 | 建议 |
|---|---|
| 只要求 Worker 可在 JRE 17 运行，不强制生产随包 JRE 为 17 | **优先采用兼容性分层**：源码/字节码目标设为 17，CI 测 17/21，生产继续随包交付 21 |
| 运行环境、采购或安全基线强制 JDK 17，且不要求 Windows ARM64 | **Go**。兼容性证据充分，按完整迁移清单实施 |
| JDK 17 与 Windows ARM64 都是硬要求 | **Blocked on distribution choice**。Temurin 当前资产不满足，先审批厂商或平台策略 |
| 目标是显著缩小离线包，且获批平台矩阵的基准确认收益 | **Go with measurement**。记录门槛和支持期退出计划 |
| 只是希望“版本低一点可能更快/更兼容” | **No-go for now**。自带 JRE 不增加终端兼容性，性能收益尚未证明 |
| 更重视长期安全更新窗口和较少维护动作 | **保留 JDK 21**。Temurin 21 的社区更新窗口更长 |

综合判断：**JDK 17 是可行的 Worker 编译/运行目标，不是当前六平台能力的无损替换，也不是自动成立的性能优化。** 如果业务确有 JDK 17 约束，源码和依赖迁移风险低且无需降级 Tika/POI/PDFBox，但必须先解决 Windows ARM64 分发选择；如果没有硬约束，建议先把 Worker 做成 Java 17 字节码兼容、继续随包交付 JDK 21，并用跨平台成品基准判断约 4.5 MiB 的同厂商单平台 JRE 探针收益是否值得换取更短的支持窗口和额外平台复杂度。
