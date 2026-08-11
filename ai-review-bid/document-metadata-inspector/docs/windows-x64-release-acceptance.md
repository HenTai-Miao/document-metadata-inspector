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
- [ ] `SHA256SUMS` 全部记录的 SHA-256 核验结果：
- [ ] 验收结论：PASS / FAIL

记录中不得写入用户名、主机名、绝对文档路径、报告内容或凭据。需要保留扫描报告时，只能保存
在仓库外的受控位置。

## 准备干净环境和核验交付文件

- [ ] 确认 `PATH` 中没有可用的 Python、Java 或 ExifTool。记录下面命令的输出摘要，不记录
  用户目录：

  ```powershell
  Get-Command python, py, java, exiftool -ErrorAction SilentlyContinue
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
  pwsh -File scripts/verify_windows_release.ps1 `
    -ReleaseDirectory release/windows-x64 `
    -Mode All
  ```

  失败时不分发该目录：保留不含文档/凭据的失败摘要，回到构建机重新构建并重新验收。

## 验收安装版

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
- [ ] 最终只记录 PASS/FAIL、版本、commit、平台、Defender 状态和哈希结果。若任一检查失败，
  不分发该构建，并在重建后从头执行本清单。
