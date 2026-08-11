# 跨平台审计深蓝自定义窗口顶栏设计

## 目标与批准依据

本设计删除 Electron 默认生成的窗口标题栏和 `File`、`Edit`、`View`、`Window` 菜单，把
现有蓝色业务顶栏升级为应用唯一的窗口顶栏。用户在三套可视化稿中选择了
“A：审计深蓝一体栏”，并进一步确认 Windows、macOS、Linux 三个平台都使用完全统一的
自绘窗口框架；macOS 不保留红、黄、绿原生窗口按钮。

页面的单一目标是：在不改变目录选择、核验、报告和安全退出流程的前提下，让用户打开应用后
直接进入一体化的“文档元数据核验”工作台，不再看到与产品视觉割裂的系统黑色栏。

## 现状与问题

`desktop/src/main/main.ts` 当前使用带原生框架的 `BrowserWindow`，且没有显式设置应用菜单。
Electron 因而自动创建窗口标题栏以及包含 `File`、`Edit`、`View`、`Window` 的默认菜单。
渲染层又在 `desktop/src/renderer/main.ts` 中绘制了一条 52px 高的业务顶栏，最终形成三层顶部
结构：系统标题栏、系统菜单、应用蓝色顶栏。

这三层结构有四个问题：

1. 系统黑色区域与审计蓝业务界面割裂。
2. 标题和产品身份重复出现，占用垂直空间。
3. 默认菜单没有承载项目实际功能，却形成可见噪声。
4. 原生标题栏随操作系统变化，无法保持用户批准的跨平台统一外观。

Electron 43.3.0 官方接口支持用 `frame: false` 创建无边框窗口；无原生标题栏的窗口需要用
CSS `app-region: drag` 标记拖动区域，并用 `app-region: no-drag` 恢复按钮等交互元素的指针
事件。`Menu.setApplicationMenu(null)` 可禁止默认菜单，且在 Windows/Linux 上移除窗口菜单栏。

## 方案比较

### 方案 A：完全无边框窗口与自绘控制按钮（采用）

- 所有平台设置 `frame: false`。
- 渲染层绘制产品顶栏和最小化、最大化/还原、关闭按钮。
- 通过受限 preload 接口把明确的窗口动作发送到主进程。
- 优点是三平台外观完全一致，能够精确落实批准稿。
- 代价是必须自行覆盖拖动、窗口状态同步、无障碍标签和跨平台冒烟测试。

### 方案 B：隐藏标题栏但保留系统窗口按钮（不采用）

使用 `titleBarStyle: "hidden"` 和 `titleBarOverlay`。实现成本较低，但 Windows/Linux 的系统
按钮与 macOS 交通灯仍不一致，而且窗口按钮不是项目自绘，无法满足批准稿。

### 方案 C：按平台混合原生和自绘框架（不采用）

Windows/Linux 使用自绘按钮，macOS 保留交通灯。它更符合各平台惯例，但与用户明确选择的
三平台统一方案冲突。

## 变更边界

本次只调整 Electron 桌面壳层、受限 IPC、渲染层顶栏、相关类型和自动化测试：

- 修改 `BrowserWindow` 外观配置并禁止默认应用菜单。
- 增加最小化、最大化/还原、关闭和最大化状态同步能力。
- 把当前业务顶栏重构为唯一的自定义窗口顶栏。
- 增加窗口控制图标、样式、键盘焦点和响应式收缩规则。
- 增加主进程、preload 合同和渲染层的定向测试。

本次不改变：

- Python 元数据解析、格式检测、证据归一化和比较算法。
- Java Worker、ExifTool、扫描进程生命周期和资源限制。
- 目录发现、核验结果模型、报告证据结构或导出格式。
- 现有目录选择、开始核验、停止、重试、重新核验和报告导航语义。
- CSP、`contextIsolation`、`sandbox`、`nodeIntegration`、导航限制和新窗口限制。
- 打包工具、运行时下载策略、发行档案结构或依赖版本。

不引入第三方标题栏组件、图标库、字体或任何远程资源。现有技术栈已经提供完成该功能所需的
Electron 主进程 API、preload 隔离边界和原生 TypeScript DOM 渲染能力，自定义实现的范围足够
小，不需要额外供应链依赖。

## 架构设计

### 主进程窗口边界

`desktop/src/main/main.ts` 创建窗口时在三个平台统一设置 `frame: false`，保留当前
`width`、`height`、`minWidth`、`minHeight`、图标、背景色和全部安全型
`webPreferences`。不设置 `titleBarOverlay`，避免系统按钮覆盖自绘按钮。

应用启动时显式调用 `Menu.setApplicationMenu(null)`，从源头禁止 Electron 自动创建默认菜单。
窗口继续使用当前 `ready-to-show`、导航拦截、关闭处理和平台激活流程。

新增的窗口控制模块只承担以下职责：

- 根据受信任的 IPC 请求调用当前 `BrowserWindow.minimize()`。
- 在 `isMaximized()` 为 `true` 时调用 `unmaximize()`，否则调用 `maximize()`。
- 调用当前 `BrowserWindow.close()`，而不是直接调用 `destroy()` 或强制终止进程。
- 返回当前 `{ isMaximized: boolean }` 状态。
- 监听 `maximize` 和 `unmaximize`，只向当前主窗口主 frame 推送状态变化。

窗口控制模块不拥有扫描状态，不实现退出策略，也不直接修改渲染层。关闭仍进入现有窗口关闭和
应用退出链路，因此 Windows/Linux 上最后一个窗口关闭后仍触发 `app.quit()` 和既有
`before-quit` 扫描停止保护；macOS 保持现有“关闭窗口但应用仍可从 Dock 再次激活”的语义。

### 共享合同与 preload 边界

共享合同增加不可扩散 Electron 对象的纯数据接口：

```ts
export interface WindowState {
  isMaximized: boolean;
}

export interface WindowControlsBridge {
  minimize(): Promise<void>;
  toggleMaximize(): Promise<WindowState>;
  close(): Promise<void>;
  getState(): Promise<WindowState>;
  onStateChanged(listener: (state: WindowState) => void): () => void;
}
```

`DocmetaBridge` 增加只读的 `windowControls: WindowControlsBridge`。preload 只允许访问以下固定
通道：

- `window:minimize`
- `window:toggle-maximize`
- `window:close`
- `window:get-state`
- `window:state-changed`

每个 invoke 请求都复用当前主进程的可信发送者检查：发送者必须是当前主窗口的
`webContents`，且发送 frame 必须是该窗口的 `mainFrame`。preload 不暴露 `ipcRenderer`、
`BrowserWindow`、通道名称参数、任意发送函数或平台文件系统能力。

`onStateChanged` 为每个调用者创建单独监听器并返回清理函数；清理函数必须移除同一个包装后的
监听器，防止页面重载或重复初始化造成监听泄漏。

### 渲染层组件

当前 `topbar()` 保留业务状态驱动逻辑，但窗口控制按钮拆成一个边界清晰的小组件。该组件：

- 接收 `WindowControlsBridge` 和当前 `WindowState`。
- 创建最小化、最大化/还原和关闭三个 `button`。
- 根据 `isMaximized` 在单矩形和双矩形 SVG 之间切换。
- 只调用桥接层方法，不读取 Electron 全局对象。
- 给每个按钮设置中文 `aria-label`、`title` 和稳定测试标识。

渲染器在首次挂载时订阅 `onStateChanged`，并读取一次 `getState()`。点击最大化按钮时，
`toggleMaximize()` 的返回值立即更新图标；主进程的 `maximize`/`unmaximize` 事件负责同步通过
拖动区域双击、系统快捷操作或窗口管理器触发的状态变化。

业务状态仍由现有 `AppState` 管理。窗口最大化状态是桌面壳层状态，不进入扫描状态归约器，也不
改变目录选择或结果页面的状态机。

### 数据与事件流

```text
用户点击窗口按钮
  → renderer WindowControls 组件
  → window.docmeta.windowControls 固定方法
  → preload 固定 IPC 通道
  → main assertTrustedSender
  → 当前 BrowserWindow 动作
  → maximize / unmaximize 事件
  → window:state-changed
  → preload 监听包装
  → renderer 更新最大化/还原图标
```

关闭流程不经过扫描服务的新通道：

```text
关闭按钮 → BrowserWindow.close()
  → 现有 closed / window-all-closed / before-quit 流程
  → 如核验正在运行，复用现有 ScanService.stop()
  → 停止成功后退出；停止失败时复用既有错误框和恢复窗口逻辑
```

## 视觉设计

### 色彩与尺寸

- 顶栏高度：`58px`。
- 顶栏背景：审计深蓝 `#0b315a`。
- 顶栏底部分隔：低对比度白色透明线，不使用阴影或渐变。
- 产品图标容器：`30px × 30px`，半透明白色背景，圆角 `7px`。
- 产品名：13–14px、700 字重、白色。
- 辅助说明“本地证据工作台”：10–11px、低对比度白色。
- 离线状态点：安全绿；文字为低对比度白色。
- 每个窗口按钮：约 `44px × 58px` 的点击区域，图标保持 10–12px 细线。
- 普通窗口按钮悬停：半透明白色背景。
- 关闭按钮悬停：风险红 `#c42b35`；按下态使用更深红色。

字体继续使用现有 `PingFang SC`、`Microsoft YaHei` 和系统无衬线字体栈。按钮和项目图标使用
内联 SVG，不使用 emoji、外部图片或装饰性动画。

### 顶栏信息顺序

从左到右固定为：

1. 项目图标。
2. “文档元数据核验”。
3. “本地证据工作台”。
4. 已选目录信息；未选择时不占据额外可见文本。
5. 可拖动的弹性空白区。
6. 当前业务操作：选择目录、停止、重试、返回报告、元数据明细或重新核验。
7. “离线运行”状态。
8. 一条低对比度竖分隔线。
9. 最小化、最大化/还原、关闭。

顶栏不重新加入 `File`、`Edit`、`View`、`Window`，也不新增汉化菜单替代物，因为这些默认
菜单没有项目功能价值。

### 拖动与指针区域

顶栏容器使用 `app-region: drag` 并禁用文本选择。所有按钮及其完整悬停范围使用
`app-region: no-drag`，保证点击、悬停和键盘焦点正常。拖动区域不挂载自定义右键菜单；某些
平台会把它当作非客户区并显示系统菜单，设计不与该系统行为冲突。

Electron/操作系统接管拖动区域的鼠标事件，并按系统标题栏语义处理拖动和双击最大化/还原。
因此渲染层不实现基于鼠标坐标的手工拖窗逻辑，也不增加原生模块。三个目标平台必须在本机构建
中验证双击行为；窗口控制按钮始终提供可操作的最大化/还原回退路径。

### 响应式收缩

当前最小窗口宽度为 980px。顶栏仍按以下优先级收缩：

1. 先隐藏“本地证据工作台”。
2. 当前目录名称使用省略号，并逐步降低最大宽度。
3. 缩短业务按钮之间的间距，但不改变按钮文字。
4. 始终保留离线状态语义和三个窗口控制按钮。

顶栏不得出现水平滚动条，窗口控制按钮不得被目录名称或业务按钮覆盖。

## 无障碍与键盘行为

- 三个窗口控制按钮均为真实 `button type="button"`。
- 中文标签分别为“最小化窗口”、“最大化窗口”或“还原窗口”、“关闭窗口”。
- `title` 与 `aria-label` 使用相同动作词，最大化状态改变时同步更新。
- 键盘 `Tab` 可以依次到达业务按钮和窗口控制按钮。
- `:focus-visible` 使用白色或高对比度浅蓝轮廓，不能只依赖背景色表达焦点。
- SVG 设置为装饰性内容，避免屏幕阅读器重复朗读图标路径。
- `prefers-reduced-motion` 下不增加位移、缩放或闪烁；本设计只使用短时颜色变化。

## 错误处理与状态一致性

- 主窗口不存在或请求来源不可信时，窗口控制请求失败关闭，不尝试查找或控制其他窗口。
- 最大化切换以主进程 `BrowserWindow.isMaximized()` 为准，渲染层状态仅用于显示图标。
- 渲染层对窗口动作的已知失败做收敛处理，不显示原始 Electron 异常，也不产生未处理的 Promise
  rejection。
- 关闭请求不绕过现有扫描停止预算、错误框和恢复窗口逻辑。
- 窗口重建后重新绑定一次窗口状态事件；旧窗口关闭后不再发送事件。

## 测试设计

### 自动化测试

1. 主进程窗口配置测试证明 `frame` 为 `false`，且启动流程显式禁止默认菜单。
2. 窗口控制模块测试证明：
   - 最小化只调用当前受信任窗口的 `minimize()`；
   - 普通窗口调用 `maximize()`；
   - 最大化窗口调用 `unmaximize()`；
   - 关闭调用 `close()`，不调用 `destroy()` 或直接终止进程；
   - 非主窗口或非主 frame 请求被拒绝。
3. preload 合同测试证明只暴露规定的五类窗口能力，并且事件清理移除正确监听器。
4. 渲染组件测试证明三个按钮存在，中文标签正确，最大化状态切换时图标和标签同步变化。
5. 样式/结构回归测试证明顶栏包含拖动区、交互控件为非拖动区、关闭悬停色为风险红，且不再渲染
   原生菜单的替代 DOM。
6. 现有目录选择、扫描、停止、结果页和元数据明细测试必须保持通过。

### 视口检查

至少检查：

- `1360 × 900` 默认窗口。
- `980 × 700` 最小窗口。

两种尺寸都必须满足：无顶部黑色原生栏、无菜单栏、无水平溢出、产品信息不遮挡业务按钮、三个
窗口控制按钮完整可见、当前目录长名称安全省略。

### 原生平台冒烟测试

Windows、macOS、Linux 的本机构建分别验证：

- 拖动顶栏空白区移动窗口。
- 双击拖动区最大化并再次双击还原。
- 最小化、最大化/还原和关闭按钮。
- 最大化图标与真实窗口状态一致。
- 普通悬停、关闭红色悬停和键盘焦点。
- 调整窗口边缘仍可改变窗口尺寸。
- 空闲状态关闭。
- 核验进行中关闭，并确认现有安全停止流程仍生效。
- 关闭后重新激活应用的现有平台语义不变。

Linux 结果需记录使用的显示协议和桌面环境，因为 Wayland 窗口管理器对最小化、窗口尺寸和客户端
装饰存在平台差异；功能验收以项目支持的实际发行环境为准，不通过静默降级到带原生标题栏的
另一套外观。

### 仓库验证

实现完成后运行桌面端定向测试、完整测试、类型检查、Biome 检查和构建，并执行仓库规定的完整
Python 验证：

```bash
cd desktop
pnpm test
pnpm typecheck
pnpm lint
pnpm format:check
pnpm build

cd ..
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run basedpyright
uv lock --check
uv build
```

Java Worker 没有代码变更，但交付前仍按仓库规则在 Java 21 环境中运行
`./mvnw --batch-mode --no-transfer-progress verify`。冻结应用构建前后继续运行
`uv run docmeta verify`。

## 验收条件

1. Windows、macOS、Linux 均使用同一套审计深蓝自定义顶栏。
2. 应用窗口中不再出现原生标题栏或 `File / Edit / View / Window` 默认菜单。
3. 顶栏严格使用批准的 A 方案结构、深蓝色彩和右侧自绘窗口按钮。
4. 顶栏空白区可拖动，双击可最大化/还原；所有业务按钮正常点击且不会拖动窗口。
5. 最小化、最大化/还原和关闭功能正确，最大化图标与真实窗口状态一致。
6. 关闭按钮悬停为红色，所有窗口按钮具备中文无障碍标签和可见键盘焦点。
7. 点击关闭不绕过现有核验进程安全停止逻辑。
8. 预加载层不暴露通用 Electron 或 IPC 能力，未知窗口和子 frame 请求被拒绝。
9. `1360 × 900` 和 `980 × 700` 下无顶栏重叠或水平溢出。
10. 现有目录选择、扫描状态、报告和元数据明细行为不变。
11. 桌面端测试、类型检查、格式检查、构建及仓库级验证全部通过。

## 官方依据

- Electron Window Customization：<https://www.electronjs.org/docs/latest/tutorial/window-customization>
- Electron Custom Window Interactions：<https://www.electronjs.org/docs/latest/tutorial/custom-window-interactions>
- Electron BrowserWindow API：<https://www.electronjs.org/docs/latest/api/browser-window>
- Electron BaseWindow `frame` 配置：<https://www.electronjs.org/docs/latest/api/base-window>
- Electron Menu API：<https://www.electronjs.org/docs/latest/api/menu/>
