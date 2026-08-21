# 产品名称与 Squirrel 首次启动修复设计

## 背景

当前 Windows 安装版能够把 x64 Electron 应用和离线分析运行时写入用户目录，但安装完成后
没有正常显示应用，也没有创建指向安装版的快捷方式。Parallels Windows 11 中对桌面交付
EXE `b9575189c28ab709d48e842ec1947a2d59e0d0c2927edf8cfcec547b55861a72`
的单次干净复现证明：

- Squirrel Setup 外壳为 `0x014c`，内置 Electron 应用与分析核心为 `0x8664`；
- 安装目录和卸载项正常创建，Setup 返回 `0`；
- 安装版入口未创建快捷方式；
- 使用真实 `--squirrel-firstrun` 参数启动时，进程立即退出且从未显示窗口；
- 不带 Squirrel 参数直接启动同一个已安装 x64 应用时，主窗口可正常出现并关闭。

根因是 `desktop/src/main/main.ts` 使用
`process.argv[1]?.startsWith("--squirrel-")` 处理 Squirrel 生命周期。这个条件错误地把
`--squirrel-firstrun` 当作必须退出的生命周期事件，并且没有在安装、升级和卸载事件中调用
Squirrel 的快捷方式管理命令。该内联逻辑来自一次为规避 pnpm 打包缺少运行时依赖而做的历史
修复；本次不能简单恢复外部依赖，否则会重新引入打包后 `MODULE_NOT_FOUND` 风险。

用户同时要求把产品名称逐字改为：

> 围标串标投标人名称一致检测工具

不得替换同义词、缩写、增加“报告”“软件”“系统”“平台”等后缀，也不得保留旧产品名作为
当前界面名称。

## 目标

1. 所有当前用户可见产品名称统一为“围标串标投标人名称一致检测工具”。
2. Windows Squirrel 安装完成后，`--squirrel-firstrun` 必须进入普通应用启动流程并显示窗口。
3. Squirrel 安装/升级必须创建快捷方式，卸载必须移除快捷方式，obsolete 事件必须安全退出。
4. Squirrel 事件处理代码必须打进 Vite 主进程 bundle，不依赖 packaged app 中额外存在的
   `node_modules/electron-squirrel-startup`。
5. 重新生成绿色免安装版和安装版，并在 Parallels Windows 中真实验证安装、首次启动、
   快捷方式、无 CMD 窗口和卸载。

## 非目标

- 不更改 Python 包名、CLI 命令 `docmeta`、Electron npm 包名
  `docmeta-review-desktop` 或可执行文件名 `docmeta-review.exe`。
- 不更改 Squirrel/NuGet 身份 `DocumentMetadataInspector`、安装目录、注册表键、升级身份或
  现有发布目录内部的英文契约文件名。
- 不批量改写历史设计稿、历史研究原型、已经归档的规格或实现报告。
- 不把代码签名证书纳入本次修改。安装包仍可能在新的 Windows 机器上显示未知发布者或
  SmartScreen 声誉提示；该提示与本次首次启动缺陷分开记录。
- 不改变扫描、解析、报告数据模型、问题标签、导出结构或离线运行时内容。

## 产品名称边界

当前用户入口中的旧名称全部替换为精确名称：

- `desktop/package.json` 的 `productName`；
- HTML 页面标题、Electron `BrowserWindow` 标题和顶部栏标题；
- 当前 HTML 报告的 `<title>` 与可见 `<h1>`；
- NSIS 备用安装器中的显示名、版本资源、安装/卸载区段和快捷方式目录；
- README 中的当前产品标题与产品说明；
- 当前打包与验收文档中用于说明产品显示名的位置。

内部兼容标识继续使用英文稳定值。Windows 正式发布目录仍保留：

```text
DocumentMetadataInspector-<version>-win-x64-Setup.exe
DocumentMetadataInspector-<version>-win-x64-Portable.zip
DocumentMetadataInspector-<version>-win-x64-CLI.zip
```

最终复制到用户桌面的两个普通用户入口使用精确中文产品名：

```text
围标串标投标人名称一致检测工具-安装版-x64-<commit>.exe
围标串标投标人名称一致检测工具-绿色免安装-x64-<commit>.zip
```

“安装版”“绿色免安装”“x64”和提交号是交付物类型/平台/版本信息，不属于产品名称本身。

## Squirrel 生命周期设计

恢复固定版本 `electron-squirrel-startup@1.0.1` 作为桌面生产依赖。主进程在创建任何窗口、
注册 IPC 或解析离线运行时之前导入该模块：

```ts
import squirrelStartup from "electron-squirrel-startup";

if (squirrelStartup) {
  app.quit();
}
```

模块的固定行为为：

- `--squirrel-install`、`--squirrel-updated`：通过相邻 `Update.exe` 创建当前可执行文件快捷方式，
  完成后退出生命周期进程；
- `--squirrel-uninstall`：移除当前可执行文件快捷方式，完成后退出；
- `--squirrel-obsolete`：立即退出；
- `--squirrel-firstrun` 和普通启动：返回 `false`，继续应用初始化并显示主窗口。

`desktop/vite.main.config.mts` 只把 Electron 本身标记为 external。不得把
`electron-squirrel-startup` 保留为 external；Vite 必须把模块及其小型 JavaScript 依赖直接
写入 `.vite/build/main.js`。这样 packaged app 不依赖 pnpm 的 `node_modules` 链接布局，也不会
重现历史 `Cannot find module 'electron-squirrel-startup'`。

## 安装与运行体验

- 双击安装版后允许出现 Squirrel 自带 `Installing...` 进度窗口；不得产生 CMD、PowerShell、
  Java 或 ExifTool 可见控制台。
- 首次安装完成后必须出现产品主窗口，窗口标题必须是精确产品名。
- 开始菜单或桌面中必须至少存在一个由 Squirrel 创建、目标指向当前安装身份的快捷方式；
  验收不能把旧绿色版快捷方式误认为安装版快捷方式。
- 通过安装入口再次启动时，必须显示同一个 x64 Electron 应用。
- 卸载必须调用真实 `Update.exe --uninstall`，并继续遵守现有严格残留所有权和清理契约。

## 测试设计

### RED 契约

先增加窄范围测试并观察当前代码失败：

1. 产品显示名测试要求当前 UI、窗口、HTML 报告和 package metadata 使用精确名称；
2. Squirrel 启动测试要求恢复固定生产依赖、主进程导入官方模块，并禁止通配
   `startsWith("--squirrel-")`；
3. Vite 打包契约测试要求 `electron-squirrel-startup` 不在 external 列表中；
4. Windows 发布工作流测试要求安装版验收检查首次运行窗口和安装版快捷方式目标。

### GREEN 门禁

实现后至少运行：

```bash
uv run pytest tests/unit/test_html_export.py \
  tests/unit/test_desktop_release_workflow.py
uv run ruff check .
uv run ruff format --check .
uv run basedpyright
uv lock --check
uv build
(cd java-worker && ./mvnw --batch-mode --no-transfer-progress verify)
(cd desktop && corepack pnpm install --frozen-lockfile)
(cd desktop && corepack pnpm test)
(cd desktop && corepack pnpm typecheck)
(cd desktop && corepack pnpm lint)
(cd desktop && corepack pnpm format:check)
(cd desktop && corepack pnpm build)
```

完整 Python 测试 `uv run pytest` 也必须通过后才可打包。

## Windows 构建与验收

从精确提交创建新的 Windows x64 构建，不复用旧 `0bb2ce5` 安装包。构建产物必须经过现有
核心哈希、PE `0x8664`、离线运行时和发布目录校验。Parallels 验收使用普通用户交互会话，
并在每轮前可恢复地保存旧安装状态：

1. 证明安装根、Squirrel 临时目录和目标进程基线干净；
2. 从本地 NTFS 路径双击/启动安装版一次；
3. 记录 Setup、Update、Squirrel 和 Electron 的进程身份与窗口句柄；
4. 要求 Setup 返回 `0`，首次运行主窗口在有界时间内出现；
5. 要求窗口标题是精确产品名，且没有新的可见 CMD/PowerShell/Java/ExifTool 控制台；
6. 枚举 `.lnk` 的真实 `TargetPath`，要求它指向当前安装根，不能只按快捷方式文件名判断；
7. 从该快捷方式再次启动并确认窗口；
8. 使用真实卸载入口卸载，检查安装根、受控临时目录和产品进程；
9. 重算安装版、绿色版及发布清单哈希；
10. 把新安装版和绿色版复制到 Mac 桌面，文件名使用精确中文产品名。

如果 Parallels ARM64 宿主需要既有的 x64 架构诊断替代，只允许沿用已经审计的、绑定核心
SHA-256 的冻结自检替代；安装、首次启动、快捷方式、主窗口和卸载必须真实执行，不得替代。

## 验收标准

- 当前用户可见产品名称没有旧名称，也没有未经允许的名称变体。
- `--squirrel-firstrun` 不再被退出分支捕获。
- packaged `.vite/build/main.js` 不包含运行时
  `require("electron-squirrel-startup")`，但包含官方模块的快捷方式处理逻辑。
- 安装版在 Parallels 普通用户会话中完成真实安装、首次显示、快捷方式再启动和真实卸载。
- 安装版和绿色版均为 x64 应用载荷，无可见 CMD 窗口，离线运行时哈希与发布记录一致。
- 新交付物放到用户桌面，旧 `0bb2ce5` 文件保留，避免未经确认覆盖用户已有测试证据。
