# Windows x64 内部交付手工验收

> **前置条件与范围：** 在干净的 Windows 10 或 Windows 11 x64 虚拟机或干净账户中执行。
> Windows 包为未签名内部交付；未知发布者或 SmartScreen 声誉提示与 Windows Defender 检测是
> 不同事件，必须分别记录。此清单是一次验收记录模板，不表示任何 Windows 产物已经构建或
> 验证。生成的包、真实文档和提取报告均不得提交到 Git。

## 记录

- [ ] 发布版本：
- [ ] Git commit：
- [ ] Windows 版本和版本号：
- [ ] CPU/架构（必须为 x64）：
- [ ] Windows Defender 已启用；状态/单独检测记录：
- [ ] 构建期间是否联系 Java/JDK 下载 URL：否 / 是（是即 FAIL）：
- [ ] `SHA256SUMS` 全部记录的 SHA-256 核验结果：
- [ ] 验收结论：PASS / FAIL

记录中不得写入用户名、主机名、绝对路径、报告内容或凭据。每项检查的最小证据统一为三个字段：
`stage` 是稳定阶段名，`exit_code` 是十进制退出码，`sha256` 是不含路径的小写 SHA-256；没有
对应产物时写 `null`。需要保留扫描报告时，只能保存于仓库外的受控位置。

## 在受控进程中构建

- [ ] 已安装的 Java 17 可以保留在机器上，但本次验收只在**当前 PowerShell 测试进程**清除
  `JAVA_HOME` 并移除 `PATH` 中的 Java 项；不要修改用户或系统环境变量。以下命令不输出或记录
  系统 Java 路径，并在仍可解析到 `java` 时停止：

  ```powershell
  $env:JAVA_HOME = $null
  $systemJavaPaths = @()
  $javaCommand = Get-Command java.exe -CommandType Application `
    -ErrorAction SilentlyContinue | Select-Object -First 1
  while ($null -ne $javaCommand) {
    $javaSource = [string]$javaCommand.Source
    $systemJavaPaths += $javaSource
    $javaDirectory = (
      Split-Path -LiteralPath $javaCommand.Source -Parent
    ).TrimEnd([char[]]'\')
    $remainingPathEntries = @()
    $removedJavaEntry = $false
    foreach ($pathEntry in @($env:Path -split ';')) {
      if ([string]::IsNullOrWhiteSpace($pathEntry)) {
        $remainingPathEntries += $pathEntry
        continue
      }
      try {
        $normalizedPathEntry = [System.IO.Path]::GetFullPath(
          $pathEntry.Trim().Trim([char[]]'"')
        ).TrimEnd([char[]]'\')
      }
      catch {
        $remainingPathEntries += $pathEntry
        continue
      }
      if ($normalizedPathEntry -ieq $javaDirectory) {
        $removedJavaEntry = $true
      }
      else {
        $remainingPathEntries += $pathEntry
      }
    }
    if (-not $removedJavaEntry) {
      throw "Resolved java.exe did not originate from a removable PATH entry"
    }
    $env:Path = $remainingPathEntries -join ';'
    $nextJavaCommand = Get-Command java.exe -CommandType Application `
      -ErrorAction SilentlyContinue | Select-Object -First 1
    if (
      $null -ne $nextJavaCommand -and
      [string]$nextJavaCommand.Source -ieq $javaSource
    ) {
      throw "Current-process Java PATH cleanup made no progress"
    }
    $javaCommand = $nextJavaCommand
  }
  ```

- [ ] 用本项目的唯一入口构建。构建日志仅用于本次检查，完成后删除；确认其中没有系统 Java
  路径，且网络/代理记录中没有 Java/JDK 下载 URL。若任一项不成立，标记 FAIL 并且不进入打包。

  ```powershell
  $buildLog = Join-Path $env:TEMP "docmeta-windows-build.log"
  try {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass `
      -File .\scripts\build_windows_x64.ps1 *>&1 |
      Tee-Object -FilePath $buildLog
    $buildExitCode = $LASTEXITCODE
    if ($buildExitCode -ne 0) {
      throw "Windows target build failed with exit code $buildExitCode"
    }
    foreach ($systemJavaPath in $systemJavaPaths) {
      if (Select-String -LiteralPath $buildLog -SimpleMatch $systemJavaPath) {
        throw "Build log contains a system Java path"
      }
    }
  }
  finally {
    if (Test-Path -LiteralPath $buildLog) {
      Remove-Item -LiteralPath $buildLog -Force -ErrorAction Stop
    }
  }
  ```

  在验收记录中写入“构建期间是否联系 Java/JDK 下载 URL：否”；该结论必须来自本次构建的网络或
  代理记录，而不是仅凭构建日志。目标构建只应执行 Git 随附、经校验 JRE 的 `java.exe` 探针，
  不运行 Maven、不下载 JDK，也不使用系统 Java 17。

- [ ] 在断开网络的测试环境中，删除 Java 运行时缓存并从 Git 随附的 Java 输入重建；该命令必须
  成功，证明缓存不是 Java 来源：

  ```powershell
  if (Test-Path -LiteralPath .\tools\build-cache\windows-vendored-java) {
    Remove-Item -LiteralPath .\tools\build-cache\windows-vendored-java -Recurse -Force
  }
  uv run --offline python scripts/windows_vendored_java.py `
    --cache tools/build-cache/windows-vendored-java
  ```

- [ ] 在可丢弃的工作副本中篡改 Git 跟踪的 Worker JAR 一个字节，确认 Java 预检在任何冻结或
  打包前失败；无论结果如何，都使用 `git restore` 恢复该工作副本中的跟踪文件：

  ```powershell
  $workerJar = "tools/prebuilt/windows-x86_64/document-metadata-apache-worker.jar"
  $bytes = [System.IO.File]::ReadAllBytes($workerJar)
  if ($bytes.Length -eq 0) { throw "Worker JAR is empty" }
  try {
    $bytes[0] = [byte]($bytes[0] -bxor 1)
    [System.IO.File]::WriteAllBytes($workerJar, $bytes)
    $preflightOutput = @(uv run --offline python scripts/windows_vendored_java.py `
      --cache tools/build-cache/windows-vendored-java 2>&1
    )
    $preflightExitCode = $LASTEXITCODE
    if ($preflightExitCode -eq 0) {
      throw "Tampered Worker JAR passed Java preflight"
    }
    $preflightText = $preflightOutput -join [Environment]::NewLine
    if ($preflightText -notmatch "Apache worker failed its integrity check") {
      throw "Worker JAR did not reach the expected Java preflight"
    }
  }
  finally {
    git restore -- $workerJar
    $restoreExitCode = $LASTEXITCODE
    if ($restoreExitCode -ne 0) {
      throw "git restore failed for the tracked Worker JAR"
    }
    $restoreDiff = @(git diff --exit-code -- $workerJar 2>&1)
    $restoreDiffExitCode = $LASTEXITCODE
    if ($restoreDiffExitCode -ne 0) {
      throw "Tracked Worker JAR was not restored cleanly"
    }
  }
  ```

- [ ] 保持 Windows Defender 启用。将 Defender 的实际检测单独记录；不要把未签名的未知发布者
  或 SmartScreen 声誉警告写成 Defender 检测，反之亦然。

- [ ] 在包含以下六个文件的 `release/windows-x64/` 目录重新计算 `SHA256SUMS` 中的每一条记录：

  ```text
  DocumentMetadataInspector-<version>-win-x64-Setup.exe
  DocumentMetadataInspector-<version>-win-x64-Portable.zip
  DocumentMetadataInspector-<version>-win-x64-CLI.zip
  SHA256SUMS
  BUILD-INFO.json
  THIRD_PARTY_NOTICES.md
  ```

  `SHA256SUMS` 覆盖前三个交付文件、`BUILD-INFO.json` 和
  `THIRD_PARTY_NOTICES.md`；使用以下命令逐项重新计算并在任一不匹配时停止：

  ```powershell
  Set-Location release/windows-x64
  Get-Content -LiteralPath SHA256SUMS | ForEach-Object {
    if ($_ -notmatch '^(?<expected>[0-9a-f]{64})  (?<name>.+)$') {
      throw "Invalid SHA256SUMS record: $_"
    }
    $actual = (Get-FileHash -LiteralPath $Matches.name -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -cne $Matches.expected) {
      throw "SHA-256 mismatch: $($Matches.name)"
    }
  }
  Set-Location ../..
  ```

- [ ] 运行冻结交付物的自动验证；必须使用 `All` 模式，而非仅便携版模式：

  ```powershell
  powershell.exe -NoProfile -File scripts/verify_windows_release.ps1 `
    -ReleaseDirectory release/windows-x64 `
    -Mode All
  ```

  失败时不分发该目录：按 `stage`、`exit_code`、`sha256` 三字段格式保留证据，回到构建机重新
  构建并重新验收。

## 验收安装版

- [ ] 在开始安装前断开该验收 VM 或测试账户的网络连接；安装版、便携版和 CLI 的启动、扫描及
  完整性故障验证都必须在断网状态下完成。重新联网只可在此次验收结束后进行。
- [ ] 从已核验目录运行
  `DocumentMetadataInspector-<version>-win-x64-Setup.exe`，完成安装。若出现未知发布者或
  SmartScreen 提示，按内部安全流程处理并保持与 Defender 检测记录分离。
- [ ] 在安装完成后 **10 秒内** 启动 GUI。选择位于包含中文、空格和长路径的目录中的受控
  PDF、DOCX、XLSX 文件，并在 **15 秒内** 到达实际解析开始状态。只使用可公开的受控样本；
  不在 Git 中保存样本或报告。
- [ ] 扫描过程中执行停止操作，确认不存在本应用拥有的 `docmeta.exe`、Java 或 ExifTool 进程。
  可用以下命令检查，再结合任务管理器确认进程所有权：

  ```powershell
  Get-Process docmeta, java, exiftool -ErrorAction SilentlyContinue
  ```

- [ ] 完成一次扫描，并只在仓库外保存其报告。卸载应用后，确认受控输入文件和仓库外报告仍然
  存在；安装程序和卸载程序不得删除用户文档或报告。

## 验收便携版和完整性故障

- [ ] 将 `DocumentMetadataInspector-<version>-win-x64-Portable.zip` **完整解压**到包含中文和
  空格的路径。不要在 ZIP 预览器中直接运行。启动 `docmeta-review.exe`，使用与安装版相同的
  受控输入完成扫描并关闭应用；移动整个解压目录后重复启动和扫描，确认不依赖当前工作目录。
- [ ] 仅对已解压便携版的**复制测试目录**进行篡改。不要修改已核验发布目录、安装版或原始
  便携版。将复制目录中的 `resources/docmeta-runtime/docmeta.exe` 改变一个字节后启动扫描，
  确认显示稳定错误消息“离线分析组件缺失或损坏”，且没有下载、修复或回退到系统命令：

  ```powershell
  $portableSource = (Resolve-Path -LiteralPath (Read-Host "已解压便携版目录")).Path
  $portableCopy = Join-Path $env:TEMP ("docmeta-tamper-test-" + [guid]::NewGuid())
  Copy-Item -LiteralPath $portableSource -Destination $portableCopy -Recurse
  $runtime = Join-Path $portableCopy "resources/docmeta-runtime/docmeta.exe"
  $bytes = [System.IO.File]::ReadAllBytes($runtime)
  if ($bytes.Length -eq 0) { throw "Copied docmeta.exe is empty" }
  $bytes[0] = [byte]($bytes[0] -bxor 1)
  [System.IO.File]::WriteAllBytes($runtime, $bytes)
  ```

  验证错误后删除该复制测试目录，不要删除原始交付物：

  ```powershell
  Remove-Item -LiteralPath $portableCopy -Recurse -Force
  ```

- [ ] 对同一组受控输入，比对安装版和便携版报告的语义内容，确认结果相同；不要把报告正文或
  可识别的文档元数据写入验收记录。
- [ ] 最终汇总只填写“记录”一节的字段；每个步骤证据仍只使用 `stage`、`exit_code`、`sha256`
  三字段格式。若任一检查失败，不分发该构建，并在重建后从头执行本清单。
