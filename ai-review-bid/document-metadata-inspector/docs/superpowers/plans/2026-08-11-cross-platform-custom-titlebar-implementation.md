# Cross-Platform Audit-Blue Custom Titlebar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Electron's native frame and default menu with the approved 58px audit-blue titlebar and secure custom window controls on Windows, macOS, and Linux.

**Architecture:** A narrow main-process adapter owns the four allowed window actions and validates every IPC sender through the existing trust boundary. A preload factory exposes a closed `WindowControlsBridge`; the renderer adds a state-driven, accessible control cluster to the existing business topbar while the browser preview supplies deterministic no-op/toggle behavior for visual tests.

**Tech Stack:** Electron 43.3.0, TypeScript 7.0.2, native DOM rendering, Vite 8.2.0, Vitest 4.1.10, Python 3.12/pytest, Playwright.

## Global Constraints

- Windows, macOS, and Linux must all use `frame: false`; macOS traffic-light controls must not remain.
- Remove Electron's default `File`, `Edit`, `View`, and `Window` menu with `Menu.setApplicationMenu(null)`.
- Keep the approved titlebar height `58px`, background `#0b315a`, 30px logo tile, and approximately `44px × 58px` window-control hit areas.
- Keep minimize/maximize hover subtle and make close hover `#c42b35`; maximize must switch to a restore icon and label.
- Keep `contextIsolation: true`, `nodeIntegration: false`, `sandbox: true`, `webSecurity: true`, navigation denial, and new-window denial unchanged.
- Never expose `ipcRenderer`, `BrowserWindow`, arbitrary channel names, or a generic send/invoke method to the renderer.
- Reuse the existing `assertTrustedSender` check for every window-control request and call `BrowserWindow.close()`, never `destroy()`.
- Do not change Python extraction, Java Worker, ExifTool, folder discovery, scan state, result contracts, report layouts, exports, packaging, or dependency versions.
- Do not add a titlebar package, icon package, font, native module, remote asset, or runtime download.
- Preserve browser-preview responsiveness down to its existing 390px regression viewport even though the Electron minimum window is 980px.
- Follow red-green-refactor: each production change below starts only after its named test fails for the expected missing behavior.

## File Structure

- Create `desktop/src/shared/window-controls.ts`: channel constants plus serializable window state and bridge contracts.
- Create `desktop/src/main/window-controls.ts`: dependency-injected IPC registration and `BrowserWindow` action mapping.
- Create `desktop/src/preload/window-controls.ts`: closed preload adapter and listener cleanup.
- Create `desktop/src/renderer/window-controls.ts`: pure maximize presentation plus accessible DOM control cluster.
- Create `desktop/tests/window-controls-main.test.ts`: action, state, close, and trust-boundary tests without loading Electron runtime.
- Create `desktop/tests/window-controls-preload.test.ts`: fixed-channel invocation and exact listener-removal tests.
- Create `desktop/tests/window-controls-renderer.test.ts`: maximize/restore presentation tests in the existing Node test environment.
- Modify `desktop/src/shared/contracts.ts`: compose `WindowControlsBridge` into `DocmetaBridge` and re-export its public types.
- Modify `desktop/src/main/main.ts`: frameless window, no default menu, handler registration, and maximize-state publication.
- Modify `desktop/src/preload/preload.ts`: expose the window-control adapter under the existing `docmeta` bridge.
- Modify `desktop/src/renderer/bridge.ts`: deterministic browser-preview window-control implementation.
- Modify `desktop/src/renderer/main.ts`: shell-state subscription and approved topbar content order.
- Modify `desktop/src/renderer/styles.css`: drag/no-drag regions, approved visual tokens, control states, and responsive contraction.
- Modify `desktop/tests/e2e/problem_label_renderer.py`: titlebar DOM, visual, maximize-label, hover, and 980px checks.
- Modify `tests/unit/test_desktop_release_workflow.py`: source-level regression for frameless configuration, menu removal, and drag/no-drag CSS.

---

### Task 1: Secure Main/Preload Window-Control Boundary

**Files:**
- Create: `desktop/tests/window-controls-main.test.ts`
- Create: `desktop/tests/window-controls-preload.test.ts`
- Create: `desktop/src/shared/window-controls.ts`
- Create: `desktop/src/main/window-controls.ts`
- Create: `desktop/src/preload/window-controls.ts`
- Modify: `desktop/src/shared/contracts.ts`
- Modify: `desktop/src/main/main.ts`
- Modify: `desktop/src/preload/preload.ts`
- Modify: `desktop/src/renderer/bridge.ts`
- Modify: `tests/unit/test_desktop_release_workflow.py`

**Interfaces:**
- Produces: `WINDOW_CONTROL_CHANNELS`, `WindowState`, and `WindowControlsBridge` from `desktop/src/shared/window-controls.ts`.
- Produces: `registerWindowControlHandlers(options: WindowControlHandlerOptions): void` from `desktop/src/main/window-controls.ts`.
- Produces: `createWindowControlsBridge(ipc: WindowControlIpc): WindowControlsBridge` from `desktop/src/preload/window-controls.ts`.
- Produces: `DocmetaBridge.windowControls: WindowControlsBridge` for the renderer task.
- Consumes: existing `assertTrustedSender(event: IpcMainInvokeEvent): void`, `ipcMain`, and the current `mainWindow` provider.

- [ ] **Step 1: Write failing main-process action tests**

Create `desktop/tests/window-controls-main.test.ts` with separate tests for each behavior. The fake registry captures handlers, and the fake target contains only the narrow methods the module is allowed to call:

```ts
import type { IpcMain, IpcMainInvokeEvent } from "electron";
import { describe, expect, test, vi } from "vitest";

import { registerWindowControlHandlers } from "../src/main/window-controls";
import { WINDOW_CONTROL_CHANNELS } from "../src/shared/window-controls";

type InvokeHandler = (event: IpcMainInvokeEvent) => unknown;

function fixture(initiallyMaximized = false) {
  const handlers = new Map<string, InvokeHandler>();
  let maximized = initiallyMaximized;
  const target = {
    minimize: vi.fn(),
    maximize: vi.fn(() => {
      maximized = true;
    }),
    unmaximize: vi.fn(() => {
      maximized = false;
    }),
    isMaximized: vi.fn(() => maximized),
    close: vi.fn(),
    destroy: vi.fn(),
  };
  const assertTrustedSender = vi.fn();
  const ipc = {
    handle: vi.fn((channel: string, handler: InvokeHandler) => {
      handlers.set(channel, handler);
    }),
  } as unknown as Pick<IpcMain, "handle">;
  registerWindowControlHandlers({ ipc, getWindow: () => target, assertTrustedSender });
  const event = {} as IpcMainInvokeEvent;
  const invoke = (channel: string) => {
    const handler = handlers.get(channel);
    if (handler === undefined) {
      throw new Error(`missing handler: ${channel}`);
    }
    return handler(event);
  };
  return { assertTrustedSender, event, invoke, target };
}

describe("registerWindowControlHandlers", () => {
  test("minimizes only after validating the sender", () => {
    const { assertTrustedSender, event, invoke, target } = fixture();
    invoke(WINDOW_CONTROL_CHANNELS.minimize);
    expect(assertTrustedSender).toHaveBeenCalledWith(event);
    expect(target.minimize).toHaveBeenCalledOnce();
  });

  test("maximizes a normal window and returns authoritative state", () => {
    const { invoke, target } = fixture();
    expect(invoke(WINDOW_CONTROL_CHANNELS.toggleMaximize)).toEqual({ isMaximized: true });
    expect(target.maximize).toHaveBeenCalledOnce();
    expect(target.unmaximize).not.toHaveBeenCalled();
  });

  test("restores a maximized window", () => {
    const { invoke, target } = fixture(true);
    expect(invoke(WINDOW_CONTROL_CHANNELS.toggleMaximize)).toEqual({ isMaximized: false });
    expect(target.unmaximize).toHaveBeenCalledOnce();
    expect(target.maximize).not.toHaveBeenCalled();
  });

  test("closes through close rather than destructive APIs", () => {
    const { invoke, target } = fixture();
    invoke(WINDOW_CONTROL_CHANNELS.close);
    expect(target.close).toHaveBeenCalledOnce();
    expect(target.destroy).not.toHaveBeenCalled();
  });

  test("reads the authoritative maximize state", () => {
    const { invoke } = fixture(true);
    expect(invoke(WINDOW_CONTROL_CHANNELS.getState)).toEqual({ isMaximized: true });
  });

  test("fails closed when the current window no longer exists", () => {
    const handlers = new Map<string, InvokeHandler>();
    const ipc = {
      handle: (channel: string, handler: InvokeHandler) => handlers.set(channel, handler),
    } as unknown as Pick<IpcMain, "handle">;
    registerWindowControlHandlers({
      ipc,
      getWindow: () => null,
      assertTrustedSender: vi.fn(),
    });
    expect(() => handlers.get(WINDOW_CONTROL_CHANNELS.getState)?.({} as IpcMainInvokeEvent)).toThrow(
      "主窗口不可用",
    );
  });

  test("rejects an untrusted sender before resolving a window action", () => {
    const handlers = new Map<string, InvokeHandler>();
    const target = { minimize: vi.fn() };
    const ipc = {
      handle: (channel: string, handler: InvokeHandler) => handlers.set(channel, handler),
    } as unknown as Pick<IpcMain, "handle">;
    registerWindowControlHandlers({
      ipc,
      getWindow: () => target as never,
      assertTrustedSender: () => {
        throw new Error("拒绝来自未知窗口的请求");
      },
    });
    expect(() => handlers.get(WINDOW_CONTROL_CHANNELS.minimize)?.({} as IpcMainInvokeEvent)).toThrow(
      "拒绝来自未知窗口的请求",
    );
    expect(target.minimize).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run the main-process test and verify RED**

Run:

```bash
cd desktop
pnpm test -- tests/window-controls-main.test.ts
```

Expected: FAIL because `src/main/window-controls.ts` and `src/shared/window-controls.ts` do not exist.

- [ ] **Step 3: Write failing preload adapter tests**

Create `desktop/tests/window-controls-preload.test.ts`:

```ts
import type { IpcRenderer } from "electron";
import { describe, expect, test, vi } from "vitest";

import { createWindowControlsBridge } from "../src/preload/window-controls";
import { WINDOW_CONTROL_CHANNELS, type WindowState } from "../src/shared/window-controls";

type RendererListener = (event: Electron.IpcRendererEvent, state: WindowState) => void;

describe("createWindowControlsBridge", () => {
  test("invokes only the fixed window-control channels", async () => {
    const invoke = vi.fn(async (channel: string) =>
      channel === WINDOW_CONTROL_CHANNELS.getState ? { isMaximized: false } : undefined,
    );
    const ipc = {
      invoke,
      on: vi.fn(),
      removeListener: vi.fn(),
    } as unknown as Pick<IpcRenderer, "invoke" | "on" | "removeListener">;
    const bridge = createWindowControlsBridge(ipc);
    await bridge.minimize();
    await bridge.toggleMaximize();
    await bridge.close();
    await bridge.getState();
    expect(invoke.mock.calls.map(([channel]) => channel)).toEqual([
      WINDOW_CONTROL_CHANNELS.minimize,
      WINDOW_CONTROL_CHANNELS.toggleMaximize,
      WINDOW_CONTROL_CHANNELS.close,
      WINDOW_CONTROL_CHANNELS.getState,
    ]);
  });

  test("forwards state and removes the exact wrapper listener", () => {
    let registered: RendererListener | undefined;
    const removeListener = vi.fn();
    const ipc = {
      invoke: vi.fn(),
      on: vi.fn((_channel: string, listener: RendererListener) => {
        registered = listener;
      }),
      removeListener,
    } as unknown as Pick<IpcRenderer, "invoke" | "on" | "removeListener">;
    const bridge = createWindowControlsBridge(ipc);
    const listener = vi.fn();
    const dispose = bridge.onStateChanged(listener);
    registered?.({} as Electron.IpcRendererEvent, { isMaximized: true });
    expect(listener).toHaveBeenCalledWith({ isMaximized: true });
    dispose();
    expect(removeListener).toHaveBeenCalledWith(WINDOW_CONTROL_CHANNELS.stateChanged, registered);
  });
});
```

- [ ] **Step 4: Run the preload test and verify RED**

Run:

```bash
cd desktop
pnpm test -- tests/window-controls-preload.test.ts
```

Expected: FAIL because `src/preload/window-controls.ts` does not exist.

- [ ] **Step 5: Add a failing frameless/menu regression test**

Append to `tests/unit/test_desktop_release_workflow.py`:

```python
def test_electron_uses_the_approved_custom_window_frame() -> None:
    """The app must not fall back to Electron's native title or default menu."""
    main_source = (_PROJECT_ROOT / "desktop/src/main/main.ts").read_text(
        encoding="utf-8"
    )

    assert "frame: false" in main_source
    assert "Menu.setApplicationMenu(null)" in main_source
    assert "registerWindowControlHandlers" in main_source
    assert 'window.on("maximize"' in main_source
    assert 'window.on("unmaximize"' in main_source
    assert "WINDOW_CONTROL_CHANNELS.stateChanged" in main_source
```

- [ ] **Step 6: Run the Python regression and verify RED**

Run:

```bash
uv run pytest tests/unit/test_desktop_release_workflow.py::test_electron_uses_the_approved_custom_window_frame
```

Expected: FAIL at `assert "frame: false" in main_source`.

- [ ] **Step 7: Implement the shared closed contract**

Create `desktop/src/shared/window-controls.ts`:

```ts
export const WINDOW_CONTROL_CHANNELS = {
  minimize: "window:minimize",
  toggleMaximize: "window:toggle-maximize",
  close: "window:close",
  getState: "window:get-state",
  stateChanged: "window:state-changed",
} as const;

export interface WindowState {
  readonly isMaximized: boolean;
}

export interface WindowControlsBridge {
  minimize(): Promise<void>;
  toggleMaximize(): Promise<WindowState>;
  close(): Promise<void>;
  getState(): Promise<WindowState>;
  onStateChanged(listener: (state: WindowState) => void): () => void;
}
```

Modify `desktop/src/shared/contracts.ts` to import and re-export the types and add the nested capability:

```ts
import type { WindowControlsBridge } from "./window-controls";

export type { WindowControlsBridge, WindowState } from "./window-controls";

export interface DocmetaBridge {
  readonly windowControls: WindowControlsBridge;
  selectFolder(): Promise<FolderSelection | null>;
  startScan(): Promise<ScanResult>;
  stopScan(): Promise<boolean>;
  onScanProgress(listener: (progress: ScanProgress) => void): () => void;
}
```

- [ ] **Step 8: Implement dependency-injected main-process handlers**

Create `desktop/src/main/window-controls.ts` with a narrow structural target so tests never load Electron runtime:

```ts
import type { IpcMain, IpcMainInvokeEvent } from "electron";

import { WINDOW_CONTROL_CHANNELS, type WindowState } from "../shared/window-controls";

export interface WindowControlTarget {
  minimize(): void;
  maximize(): void;
  unmaximize(): void;
  isMaximized(): boolean;
  close(): void;
}

export interface WindowControlHandlerOptions {
  readonly ipc: Pick<IpcMain, "handle">;
  readonly getWindow: () => WindowControlTarget | null;
  readonly assertTrustedSender: (event: IpcMainInvokeEvent) => void;
}

function requiredWindow(options: WindowControlHandlerOptions): WindowControlTarget {
  const target = options.getWindow();
  if (target === null) {
    throw new Error("主窗口不可用");
  }
  return target;
}

function stateOf(target: WindowControlTarget): WindowState {
  return { isMaximized: target.isMaximized() };
}

export function registerWindowControlHandlers(options: WindowControlHandlerOptions): void {
  options.ipc.handle(WINDOW_CONTROL_CHANNELS.minimize, (event) => {
    options.assertTrustedSender(event);
    requiredWindow(options).minimize();
  });
  options.ipc.handle(WINDOW_CONTROL_CHANNELS.toggleMaximize, (event) => {
    options.assertTrustedSender(event);
    const target = requiredWindow(options);
    if (target.isMaximized()) {
      target.unmaximize();
    } else {
      target.maximize();
    }
    return stateOf(target);
  });
  options.ipc.handle(WINDOW_CONTROL_CHANNELS.close, (event) => {
    options.assertTrustedSender(event);
    requiredWindow(options).close();
  });
  options.ipc.handle(WINDOW_CONTROL_CHANNELS.getState, (event) => {
    options.assertTrustedSender(event);
    return stateOf(requiredWindow(options));
  });
}
```

- [ ] **Step 9: Implement the preload adapter**

Create `desktop/src/preload/window-controls.ts`:

```ts
import type { IpcRenderer } from "electron";

import {
  WINDOW_CONTROL_CHANNELS,
  type WindowControlsBridge,
  type WindowState,
} from "../shared/window-controls";

export type WindowControlIpc = Pick<IpcRenderer, "invoke" | "on" | "removeListener">;

export function createWindowControlsBridge(ipc: WindowControlIpc): WindowControlsBridge {
  return {
    minimize: () => ipc.invoke(WINDOW_CONTROL_CHANNELS.minimize) as Promise<void>,
    toggleMaximize: () =>
      ipc.invoke(WINDOW_CONTROL_CHANNELS.toggleMaximize) as Promise<WindowState>,
    close: () => ipc.invoke(WINDOW_CONTROL_CHANNELS.close) as Promise<void>,
    getState: () => ipc.invoke(WINDOW_CONTROL_CHANNELS.getState) as Promise<WindowState>,
    onStateChanged(listener): () => void {
      const handler = (_event: Electron.IpcRendererEvent, state: WindowState) => listener(state);
      ipc.on(WINDOW_CONTROL_CHANNELS.stateChanged, handler);
      return () => ipc.removeListener(WINDOW_CONTROL_CHANNELS.stateChanged, handler);
    },
  };
}
```

Modify `desktop/src/preload/preload.ts` so the existing closed bridge composes it:

```ts
import { createWindowControlsBridge } from "./window-controls";

const bridge: DocmetaBridge = {
  windowControls: createWindowControlsBridge(ipcRenderer),
  selectFolder: () => ipcRenderer.invoke("dialog:select-folder") as Promise<FolderSelection | null>,
  startScan: () => ipcRenderer.invoke("scan:start") as Promise<ScanResult>,
  stopScan: () => ipcRenderer.invoke("scan:stop") as Promise<boolean>,
  onScanProgress(listener): () => void {
    const handler = (_event: Electron.IpcRendererEvent, progress: ScanProgress) =>
      listener(progress);
    ipcRenderer.on("scan:progress", handler);
    return () => ipcRenderer.removeListener("scan:progress", handler);
  },
};
```

- [ ] **Step 10: Wire the frameless main window and state publication**

Modify the Electron import block and add the two internal imports exactly as follows:

```ts
import {
  app,
  BrowserWindow,
  dialog,
  type IpcMainInvokeEvent,
  ipcMain,
  Menu,
} from "electron";
import type { SelectedFolderManifest } from "../shared/contracts";
import { WINDOW_CONTROL_CHANNELS } from "../shared/window-controls";
import { registerWindowControlHandlers } from "./window-controls";
```

Insert the registration below as the first statement of the current `registerIpcHandlers()`;
leave the three existing dialog/scan registrations after it:

```ts
registerWindowControlHandlers({
  ipc: ipcMain,
  getWindow: () => mainWindow,
  assertTrustedSender,
});
```

Replace `createWindow()` with this complete version:

```ts
function createWindow(): void {
  const window = new BrowserWindow({
    width: 1360,
    height: 900,
    minWidth: 980,
    minHeight: 700,
    frame: false,
    show: false,
    title: "文档元数据核验",
    backgroundColor: "#f4f6fa",
    icon: resolve(projectRoot, "desktop", "build", "icons", "icon-512.png"),
    webPreferences: {
      preload: resolve(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      webSecurity: true,
    },
  });
  mainWindow = window;

  const publishWindowState = (): void => {
    if (!window.webContents.isDestroyed()) {
      window.webContents.send(WINDOW_CONTROL_CHANNELS.stateChanged, {
        isMaximized: window.isMaximized(),
      });
    }
  };
  window.on("maximize", publishWindowState);
  window.on("unmaximize", publishWindowState);

  window.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
  window.webContents.on("will-navigate", (event) => event.preventDefault());
  window.once("ready-to-show", () => window.show());
  window.on("closed", () => {
    if (process.platform === "darwin") {
      void scanService?.stop().catch(() => {
        showStopFailure("无法停止核验", "核验进程尚未完全停止，请再次关闭程序重试。");
      });
    }
    if (mainWindow === window) {
      mainWindow = null;
      selectedFolder = null;
    }
  });

  if (MAIN_WINDOW_VITE_DEV_SERVER_URL !== undefined) {
    void window.loadURL(MAIN_WINDOW_VITE_DEV_SERVER_URL);
  } else {
    void window.loadFile(resolve(__dirname, `../renderer/${MAIN_WINDOW_VITE_NAME}/index.html`));
  }
}
```

Replace the ready callback with this complete version, whose only behavioral addition is the first menu line:

```ts
void app.whenReady().then(() => {
  Menu.setApplicationMenu(null);
  scanService = new ScanService({
    resolveRuntime: () =>
      resolveDocmetaCommand({
        isPackaged: app.isPackaged,
        resourcesPath: process.resourcesPath,
        projectRoot,
        expectedPackagedSha256: DOCMETA_RUNTIME_SHA256,
      }),
  });
  registerIpcHandlers();
  createWindow();
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});
```

Do not modify any `before-quit`, `window-all-closed`, or scan-stop branch.

- [ ] **Step 11: Add deterministic browser-preview controls**

Modify `desktop/src/renderer/bridge.ts` before `browserPreviewBridge`:

```ts
const previewWindowStateListeners = new Set<(state: WindowState) => void>();
let previewWindowState: WindowState = { isMaximized: false };

const previewWindowControls: WindowControlsBridge = {
  minimize: async () => undefined,
  async toggleMaximize(): Promise<WindowState> {
    previewWindowState = { isMaximized: !previewWindowState.isMaximized };
    for (const listener of previewWindowStateListeners) {
      listener(previewWindowState);
    }
    return previewWindowState;
  },
  close: async () => undefined,
  getState: async () => previewWindowState,
  onStateChanged(listener): () => void {
    previewWindowStateListeners.add(listener);
    return () => previewWindowStateListeners.delete(listener);
  },
};

```

Import `WindowControlsBridge` and `WindowState` as types from `../shared/contracts`, then insert
`windowControls: previewWindowControls` as the first property of the existing
`browserPreviewBridge` object. Leave its current folder and scan methods unchanged. The preview must never
call browser `close()` or attempt OS minimization.

- [ ] **Step 12: Run focused tests and verify GREEN**

Run:

```bash
cd desktop
pnpm test -- tests/window-controls-main.test.ts tests/window-controls-preload.test.ts
pnpm typecheck

cd ..
uv run pytest tests/unit/test_desktop_release_workflow.py::test_electron_uses_the_approved_custom_window_frame
```

Expected: all commands PASS with no TypeScript diagnostics or unhandled Promise warnings.

- [ ] **Step 13: Commit the secure window boundary**

```bash
git add ai-review-bid/document-metadata-inspector/desktop/src/shared/window-controls.ts \
  ai-review-bid/document-metadata-inspector/desktop/src/shared/contracts.ts \
  ai-review-bid/document-metadata-inspector/desktop/src/main/window-controls.ts \
  ai-review-bid/document-metadata-inspector/desktop/src/main/main.ts \
  ai-review-bid/document-metadata-inspector/desktop/src/preload/window-controls.ts \
  ai-review-bid/document-metadata-inspector/desktop/src/preload/preload.ts \
  ai-review-bid/document-metadata-inspector/desktop/src/renderer/bridge.ts \
  ai-review-bid/document-metadata-inspector/desktop/tests/window-controls-main.test.ts \
  ai-review-bid/document-metadata-inspector/desktop/tests/window-controls-preload.test.ts \
  ai-review-bid/document-metadata-inspector/tests/unit/test_desktop_release_workflow.py
git commit -m "feat: add secure custom window controls"
```

Expected: one commit containing only Task 1 files.

---

### Task 2: Approved Audit-Blue Renderer Titlebar

**Files:**
- Create: `desktop/tests/window-controls-renderer.test.ts`
- Create: `desktop/src/renderer/window-controls.ts`
- Modify: `desktop/src/renderer/main.ts`
- Modify: `desktop/src/renderer/styles.css`
- Modify: `desktop/tests/e2e/problem_label_renderer.py`
- Modify: `tests/unit/test_desktop_release_workflow.py`

**Interfaces:**
- Consumes: `DocmetaBridge.windowControls`, `WindowState`, and the browser-preview adapter from Task 1.
- Produces: `windowControlPresentation(state: WindowState): WindowControlPresentation`.
- Produces: `renderWindowControls(options: RenderWindowControlsOptions): HTMLElement`.
- Preserves: existing `topbar()` business actions and renderer `AppState` transitions.

- [ ] **Step 1: Write the failing presentation test**

Create `desktop/tests/window-controls-renderer.test.ts`:

```ts
import { describe, expect, test } from "vitest";

import { windowControlPresentation } from "../src/renderer/window-controls";

describe("windowControlPresentation", () => {
  test("labels a normal window action as maximize", () => {
    expect(windowControlPresentation({ isMaximized: false })).toEqual({
      maximizeLabel: "最大化窗口",
      maximizeIcon: "maximize",
    });
  });

  test("labels a maximized window action as restore", () => {
    expect(windowControlPresentation({ isMaximized: true })).toEqual({
      maximizeLabel: "还原窗口",
      maximizeIcon: "restore",
    });
  });
});
```

- [ ] **Step 2: Extend source and browser acceptance tests before production CSS/DOM**

Append this source-level regression to `tests/unit/test_desktop_release_workflow.py`:

```python
def test_custom_titlebar_marks_drag_and_control_regions() -> None:
    """Window controls must remain clickable inside the draggable titlebar."""
    styles = (_PROJECT_ROOT / "desktop/src/renderer/styles.css").read_text(
        encoding="utf-8"
    )

    assert "-webkit-app-region: drag" in styles
    assert "\n  app-region: drag;" in styles
    assert "-webkit-app-region: no-drag" in styles
    assert "\n  app-region: no-drag;" in styles
    assert ".window-control--close:hover" in styles
    assert "#c42b35" in styles
```

In `desktop/tests/e2e/problem_label_renderer.py`, add constants and assertions immediately after the first page load, before `_scan(page)`:

```python
TITLEBAR_HEIGHT: Final = 58.0
TITLEBAR_CLOSE_BACKGROUND: Final = "rgb(196, 43, 53)"

expect(page.get_by_test_id("window-minimize")).to_have_count(1)
expect(page.get_by_test_id("window-maximize")).to_have_attribute(
    "aria-label", "最大化窗口"
)
expect(page.get_by_test_id("window-close")).to_have_attribute(
    "aria-label", "关闭窗口"
)
expect(page.get_by_test_id("window-close")).to_have_attribute("title", "关闭窗口")
titlebar_box = _visible_box(page.locator(".topbar"), "custom titlebar")
_require(
    condition=titlebar_box["height"] == TITLEBAR_HEIGHT,
    message={"unexpected_titlebar_height": titlebar_box["height"]},
)
page.get_by_test_id("window-maximize").click()
expect(page.get_by_test_id("window-maximize")).to_have_attribute(
    "aria-label", "还原窗口"
)
page.get_by_test_id("window-maximize").click()
expect(page.get_by_test_id("window-maximize")).to_have_attribute(
    "aria-label", "最大化窗口"
)
page.keyboard.press("Tab")
expect(page.get_by_test_id("window-close")).to_be_focused()
focus_outline = page.get_by_test_id("window-close").evaluate(
    "node => getComputedStyle(node).outlineStyle"
)
_require(
    condition=focus_outline != "none",
    message={"missing_window_control_focus": focus_outline},
)
page.get_by_test_id("window-close").hover()
close_background = page.get_by_test_id("window-close").evaluate(
    "node => getComputedStyle(node).backgroundColor"
)
_require(
    condition=close_background == TITLEBAR_CLOSE_BACKGROUND,
    message={"unexpected_close_background": close_background},
)
```

Add a `980 × 700` viewport pass to the existing screenshot sequence and call `_assert_no_page_overflow(page, "980")`. Keep the current 760px and 390px checks.

- [ ] **Step 3: Run focused tests and verify RED**

Run:

```bash
cd desktop
pnpm test -- tests/window-controls-renderer.test.ts

cd ..
uv run pytest tests/unit/test_desktop_release_workflow.py::test_custom_titlebar_marks_drag_and_control_regions
uv run python desktop/tests/e2e/problem_label_renderer.py
```

Expected:

- Vitest FAILS because `src/renderer/window-controls.ts` does not exist.
- pytest FAILS because current CSS has no drag/no-drag declarations.
- Playwright FAILS on the missing `window-minimize` test id before reaching pre-existing report assertions.

- [ ] **Step 4: Implement the state-driven window-control component**

Create `desktop/src/renderer/window-controls.ts`:

```ts
import type { WindowControlsBridge, WindowState } from "../shared/contracts";
import { element, testId } from "./dom";

export interface WindowControlPresentation {
  readonly maximizeLabel: "最大化窗口" | "还原窗口";
  readonly maximizeIcon: "maximize" | "restore";
}

export function windowControlPresentation(state: WindowState): WindowControlPresentation {
  return state.isMaximized
    ? { maximizeLabel: "还原窗口", maximizeIcon: "restore" }
    : { maximizeLabel: "最大化窗口", maximizeIcon: "maximize" };
}

export interface RenderWindowControlsOptions {
  readonly controls: WindowControlsBridge;
  readonly state: WindowState;
  readonly onStateChanged: (state: WindowState) => void;
}

const ICONS = {
  minimize: '<svg viewBox="0 0 12 12" aria-hidden="true"><path d="M2 8.5h8"/></svg>',
  maximize:
    '<svg viewBox="0 0 12 12" aria-hidden="true"><rect x="2.25" y="2.25" width="7.5" height="7.5"/></svg>',
  restore:
    '<svg viewBox="0 0 12 12" aria-hidden="true"><path d="M4 2.5h5.5V8M2.5 4H8v5.5H2.5z"/></svg>',
  close:
    '<svg viewBox="0 0 12 12" aria-hidden="true"><path d="m2.5 2.5 7 7m0-7-7 7"/></svg>',
} as const;

function controlButton(
  label: string,
  id: string,
  className: string,
  icon: string,
  action: () => Promise<unknown>,
): HTMLButtonElement {
  const button = element("button", `window-control ${className}`);
  button.type = "button";
  button.ariaLabel = label;
  button.title = label;
  button.innerHTML = icon;
  testId(button, id);
  button.addEventListener("click", () => void action().catch(() => undefined));
  return button;
}

export function renderWindowControls(options: RenderWindowControlsOptions): HTMLElement {
  const presentation = windowControlPresentation(options.state);
  const controls = element("div", "window-controls");
  controls.append(
    controlButton(
      "最小化窗口",
      "window-minimize",
      "window-control--minimize",
      ICONS.minimize,
      () => options.controls.minimize(),
    ),
    controlButton(
      presentation.maximizeLabel,
      "window-maximize",
      "window-control--maximize",
      ICONS[presentation.maximizeIcon],
      async () => options.onStateChanged(await options.controls.toggleMaximize()),
    ),
    controlButton(
      "关闭窗口",
      "window-close",
      "window-control--close",
      ICONS.close,
      () => options.controls.close(),
    ),
  );
  return controls;
}
```

- [ ] **Step 5: Integrate shell state and approved topbar copy**

Modify `desktop/src/renderer/main.ts`:

```ts
import type { WindowState } from "../shared/contracts";
import { renderWindowControls } from "./window-controls";

let windowState: WindowState = { isMaximized: false };

function updateWindowState(next: WindowState): void {
  if (next.isMaximized === windowState.isMaximized) {
    return;
  }
  windowState = next;
  render();
}

const disposeWindowState = bridge.windowControls.onStateChanged(updateWindowState);
window.addEventListener("beforeunload", disposeWindowState, { once: true });
void bridge.windowControls.getState().then(updateWindowState).catch(() => undefined);
```

Update `topbar()` to append this exact information order:

```ts
bar.append(
  logoEl,
  element("span", "topbar__title", "文档元数据核验"),
  element("span", "topbar__mode", "本地证据工作台"),
);
// retain optional folder, spacer, and existing state-driven business buttons
const status = element("div", "topbar__status");
status.append(element("span", "topbar__dot"), element("span", undefined, "离线运行"));
bar.append(
  btns,
  status,
  element("span", "topbar__window-sep"),
  renderWindowControls({
    controls: bridge.windowControls,
    state: windowState,
    onStateChanged: updateWindowState,
  }),
);
```

Do not move business actions out of the existing state conditions. Keep the selected-folder name and its safe ellipsis.

- [ ] **Step 6: Implement the approved visual and drag regions**

Replace the topbar-specific CSS block in `desktop/src/renderer/styles.css` with rules derived from these exact tokens:

```css
.topbar {
  display: flex;
  align-items: center;
  gap: 10px;
  height: 58px;
  padding: 0 0 0 18px;
  color: #fff;
  background: #0b315a;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  flex-shrink: 0;
  z-index: 40;
  user-select: none;
  -webkit-app-region: drag;
  app-region: drag;
}

.topbar__logo {
  display: grid;
  width: 30px;
  height: 30px;
  place-items: center;
  flex-shrink: 0;
  border-radius: 7px;
  background: rgba(255, 255, 255, 0.1);
}

.topbar__mode {
  color: rgba(255, 255, 255, 0.62);
  font-size: 10px;
  white-space: nowrap;
}

.topbar__actions,
.window-controls,
.topbar button {
  -webkit-app-region: no-drag;
  app-region: no-drag;
}

.window-controls {
  display: flex;
  align-self: stretch;
  flex-shrink: 0;
}

.window-control {
  display: grid;
  width: 44px;
  min-height: 58px;
  padding: 0;
  place-items: center;
  color: rgba(255, 255, 255, 0.9);
  border: 0;
  border-radius: 0;
  background: transparent;
}

.window-control svg {
  width: 12px;
  height: 12px;
  fill: none;
  stroke: currentColor;
  stroke-width: 1;
}

.window-control:hover {
  background: rgba(255, 255, 255, 0.1);
}

.window-control--close:hover {
  background: #c42b35;
}

.window-control:focus-visible {
  position: relative;
  outline: 2px solid #b9d9f1;
  outline-offset: -3px;
}
```

Add media rules without changing report layout rules:

```css
@media (max-width: 1150px) {
  .topbar__mode {
    display: none;
  }

  .topbar__folder-name {
    max-width: 130px;
  }
}

@media (max-width: 760px) {
  .topbar {
    gap: 7px;
    padding-left: 10px;
  }

  .topbar__folder,
  .topbar__status,
  .topbar__sep,
  .topbar__window-sep {
    display: none;
  }

  .window-control {
    width: 38px;
  }
}

@media (max-width: 520px) {
  .topbar__title {
    display: none;
  }

  .topbar__actions {
    gap: 4px;
  }

  .topbar .btn {
    padding-inline: 8px;
  }

  .window-control {
    width: 36px;
  }
}
```

- [ ] **Step 7: Run focused tests and the renderer acceptance scenario**

Run:

```bash
cd desktop
pnpm test -- tests/window-controls-renderer.test.ts
pnpm typecheck

cd ..
uv run pytest tests/unit/test_desktop_release_workflow.py::test_custom_titlebar_marks_drag_and_control_regions
uv run python desktop/tests/e2e/problem_label_renderer.py
```

Expected: all commands PASS; Playwright produces screenshots for 1440, 1280, 1024, 980, 760, and 390 widths without console, page, response, or overflow errors.

- [ ] **Step 8: Inspect the generated screenshots**

Open at least the 1440px, 980px, and 390px screenshots with the local image viewer. Confirm:

- 1440px: logo tile, title, “本地证据工作台”, business actions, “离线运行”, and all controls appear in one 58px band.
- 980px: no overlap among directory text, business actions, status, and controls.
- 390px browser regression: title/status/folder contract as specified, all business and window buttons remain clickable, and no horizontal clipping occurs.
- Close hover is the only large red titlebar surface.

If a visual defect is found, first add a bounding-box or computed-style assertion to `problem_label_renderer.py`, rerun it to observe failure, then make the smallest CSS fix and rerun.

- [ ] **Step 9: Commit the renderer titlebar**

```bash
git add ai-review-bid/document-metadata-inspector/desktop/src/renderer/window-controls.ts \
  ai-review-bid/document-metadata-inspector/desktop/src/renderer/main.ts \
  ai-review-bid/document-metadata-inspector/desktop/src/renderer/styles.css \
  ai-review-bid/document-metadata-inspector/desktop/tests/window-controls-renderer.test.ts \
  ai-review-bid/document-metadata-inspector/desktop/tests/e2e/problem_label_renderer.py \
  ai-review-bid/document-metadata-inspector/tests/unit/test_desktop_release_workflow.py
git commit -m "feat: add audit blue custom titlebar"
```

Expected: one commit containing only Task 2 files.

---

### Task 3: Full Verification and Handoff Evidence

**Files:**
- Verify only: all Task 1 and Task 2 files.
- Update only if a verification command exposes a defect: the exact failing test and its owning production file, using a new red-green cycle.

**Interfaces:**
- Consumes: complete custom-titlebar feature from Tasks 1 and 2.
- Produces: reproducible command output, screenshots, and a clean diff suitable for native Windows/macOS/Linux build follow-up.

- [ ] **Step 1: Run the complete desktop gate**

```bash
cd desktop
pnpm test
pnpm typecheck
pnpm lint
pnpm format:check
pnpm build
```

Expected: every command exits 0 with no lint, format, type, or build diagnostics.

- [ ] **Step 2: Run renderer integration/acceptance checks**

```bash
cd ..
uv run python desktop/tests/e2e/problem_label_renderer.py
```

Expected: exit 0, no browser console/page/HTTP errors, and screenshots show the approved titlebar.

- [ ] **Step 3: Run the repository Python gate**

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run basedpyright
uv lock --check
uv build
```

Expected: every command exits 0. Do not weaken unrelated tests or static-analysis configuration to obtain green output.

- [ ] **Step 4: Run runtime and Java verification required by AGENTS.md**

```bash
uv run docmeta verify

cd java-worker
./mvnw --batch-mode --no-transfer-progress verify
```

Expected: both commands exit 0 with Java 21 selected for Maven. If a required bundled runtime is unavailable, record the exact missing prerequisite without printing secrets or config values.

- [ ] **Step 5: Review the final diff and commit graph**

```bash
cd /Users/zhongerbing/Documents/xm/ai-review-bid/document-metadata-inspector
git diff --check HEAD~2..HEAD
git status --short
git log -4 --oneline --decorate
```

Expected:

- `git diff --check` prints nothing.
- Status contains no uncommitted custom-titlebar files; pre-existing unrelated untracked paths remain untouched.
- The graph contains the plan commit followed by the two implementation commits.

- [ ] **Step 6: Report native-platform verification limits accurately**

The current host can verify one native Electron platform plus browser-layout regressions. Do not claim Windows and Linux native drag/resize behavior unless their native CI/build jobs have run. Handoff must distinguish:

- automated cross-platform contract coverage;
- native behavior observed on the current macOS host;
- Windows/Linux native smoke checks still required by the design acceptance list.
