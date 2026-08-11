# Windows x64 扫描落盘与控制台窗口修复设计

## 状态与已确认决策

- 日期：2026-08-11。
- 实施分支：`dev-yx/design-spec-style-polish-20260810`。
- 用户提供的两张 Windows x64 截图分别确认了扫描失败和扫描期间反复出现终端窗口。
- 已在真实 Windows 环境用指定的 3 家投标人、9 份 PDF/DOCX/XLSX 文件复现并分层验证。
- 本轮只修复报告原子落盘和 Python 下游控制台子进程；不改变解析、比对、证据模型或界面设计。
- 采用测试驱动的最小改动，不重构所有导出器接口，不改用 `javaw.exe`，不引入新依赖。

## 已确认根因

### 报告落盘失败

`write_atomic_output()` 先关闭报告 writer，再以 `rb` 打开临时文件并对只读文件描述符调用
`os.fsync()`。Windows 内嵌 Python 对该描述符返回
`OSError: [Errno 9] Bad file descriptor`。异常被导出边界转换成
`The report could not be exported safely.`，CLI 返回退出码 `2`；Electron 扫描服务只接受
退出码 `0` 和 `3`，最终显示笼统的“离线核验组件运行失败”。

相同测试目录在不执行报告落盘，并按 x64 资源运行三个解析器时返回退出码 `0`。因此文件、
JRE、Worker JAR 和 ExifTool 都不是该错误的根因。

### 扫描期间终端窗口反复出现

Electron 启动内嵌 Python 时已经使用 `windowsHide: true`，但 Python 的四类下游启动没有传入
Windows 无窗口创建标志：

1. ExifTool 版本探测；
2. Java 版本探测；
3. 每份文档的 Apache Java Worker；
4. 每份文档的 ExifTool。

这些程序都是控制台子系统可执行文件。无控制台父进程直接启动它们时，Windows 可以创建
`conhost.exe` 或 Windows Terminal `OpenConsole.exe`，形成用户截图中的多个黑色窗口。
进程采样确认 Java 与 ExifTool 均由随包 `python.exe` 直接启动，并伴随控制台宿主进程。

## 目标

1. Windows 10/11 x64 能把比较报告安全写入临时 JSON，再原子替换目标文件。
2. macOS 和 Linux 保持现有原子导出语义。
3. Java 与 ExifTool 的版本探测和文档解析在 Windows 上全部使用
   `CREATE_NO_WINDOW`，其他平台使用创建标志 `0`。
4. 保留 `shell=False`、标准流管道、超时、输出预算和进程终止语义。
5. 使用用户指定的 9 份文件在绿色版中完成核验，不再出现 `scan:start` 错误或可见终端窗口。
6. 为两个缺陷加入能在修复前失败、修复后通过的自动化回归。

## 非目标

- 不处理 Parallels ARM64 对 x64 发布包的资源架构选择。
- 不支持从 Parallels `\\Mac\Home` 直接运行 Electron 主程序；绿色版仍应放在 Windows 本地盘。
- 不改变 Java、Tika、POI、PDFBox、ExifTool 或 Python 依赖版本。
- 不改变 `ScanServiceError` 公共错误码、报告 JSON 模型或 UI 文案。
- 不改变扫描并发度、文件发现规则、密码处理或解析器完整度判断。
- 不顺带清理当前工作区内其他任务留下的改动。

## 设计

### 可写句柄上的持久化

保留现有 writer 接口和原子替换顺序：

```text
创建同目录临时文件
  -> writer 写入并关闭
  -> 以 r+b 重新打开同一临时文件
  -> os.fsync(可写文件描述符)
  -> Path.replace(正式目标)
  -> finally 清理残留临时文件
```

`r+b` 不修改内容，只确保 Windows 为该描述符授予 `fsync` 所需的写权限。writer 关闭后再
同步仍能保证 Python 用户态缓冲已刷新，同时避免重构 JSON、XLSX 和 HTML 三个 writer 的
签名。任一写入、同步或替换步骤失败时，旧目标保持不变，临时文件仍由 `finally` 清理。

回归测试用一个包装后的 `os.fsync` 对文件描述符执行零字节 `os.write`。零字节写不会改变
报告内容，但只读描述符会以与 Windows 相同的 `EBADF` 失败，可在非 Windows CI 中稳定重现
这个句柄契约。

### 集中的后台子进程创建标志

新增一个小型通用模块，仅暴露：

```python
def hidden_subprocess_creation_flags() -> int:
    if os.name == "nt":
        return subprocess.CREATE_NO_WINDOW
    return 0
```

Windows 返回标准库的 `subprocess.CREATE_NO_WINDOW`，其他系统返回 `0`。四个生产启动点均
显式传入：

```python
creationflags=hidden_subprocess_creation_flags()
```

不使用 `shell=True`、不拼接命令字符串、不改变环境变量白名单，也不使用 `javaw.exe`；
Java/ExifTool 的 stdout、stderr、退出码和超时继续由现有代码捕获。

自动化测试在真实 worker 执行边界包裹 `Popen`，在资源解析边界包裹 `subprocess.run`，断言
收到的标志在 Windows 为 `CREATE_NO_WINDOW`、在其他系统为 `0`。这样四个调用点任一漏传
都会使对应测试失败。

## 错误与兼容性

- 报告写入失败仍使用既有 `ExportError` 清洗底层异常；成功路径不再因 Windows 只读句柄
  失败。
- `CREATE_NO_WINDOW` 只影响窗口创建，不改变子进程返回码、管道或终止行为。
- Python 3.12 的 `subprocess` 在 Windows 提供 `CREATE_NO_WINDOW`；非 Windows 分支不得访问
  该平台常量。
- 现有 macOS/Linux worker 测试会以创建标志 `0` 运行真实子进程，验证跨平台无回归。

## 测试与验收

### 自动化 RED→GREEN

1. `test_json_export.py`：旧实现因只读描述符触发 `EBADF`，新实现成功且内容正确。
2. `test_tool_resources.py`：ExifTool 与 Java 版本探测收到正确创建标志。
3. `test_apache_worker_adapter.py`：真实 Apache worker 子进程收到正确创建标志并成功解析。
4. `test_exiftool_adapter.py`：真实 ExifTool 适配器子进程收到正确创建标志并成功解析。

### 项目质量门

```text
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run basedpyright
uv lock --check
uv build
cd java-worker && ./mvnw --batch-mode --no-transfer-progress verify
cd desktop && pnpm test && pnpm lint && pnpm typecheck && pnpm package
```

### Windows 绿色版验收

1. 在 Windows 本地盘启动新绿色版。
2. 选择用户指定项目根目录；界面识别 3 家投标人、9 份文件。
3. 开始核验并监控 `python.exe`、`java.exe`、`exiftool.exe`、`conhost.exe` 和
   `OpenConsole.exe`。
4. 核验完成，生成和读取比较报告，不显示 `scan:start` 错误。
5. Java/ExifTool 运行期间没有非基线可见控制台窗口。
6. 应用关闭后没有遗留 Python、Java 或 ExifTool 进程。

## 成功标准

- 原始两类回归在旧实现上按预期失败，在新实现上通过。
- 指定 9 份文件在 Windows x64 运行时返回成功并生成有效 JSON 报告。
- 扫描过程中不再出现用户截图中的黑色终端窗口。
- 所有变更行都能追溯到这两个缺陷；现有其他任务的修改和未跟踪文件保持原样。
