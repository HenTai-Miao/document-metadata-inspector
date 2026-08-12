import { resolve } from "node:path";

import { app, BrowserWindow, dialog, type IpcMainInvokeEvent, ipcMain, Menu } from "electron";
import squirrelStartup from "electron-squirrel-startup";
import type { SelectedFolderManifest } from "../shared/contracts";
import { WINDOW_CONTROL_CHANNELS } from "../shared/window-controls";
import { discoverFolder, publicFolderSelection } from "./folder-discovery";
import { resolveDocmetaCommand } from "./runtime-resolver";
import { ScanService } from "./scan-service";
import { registerWindowControlHandlers } from "./window-controls";

if (squirrelStartup) {
  app.quit();
}

const projectRoot = resolve(__dirname, "../../..");
let mainWindow: BrowserWindow | null = null;
let scanService: ScanService | null = null;
let selectedFolder: SelectedFolderManifest | null = null;
let allowImmediateQuit = false;
let quitStopPromise: Promise<void> | null = null;

function showStopFailure(title: string, message: string): void {
  dialog.showErrorBox(title, message);
  if (app.isReady() && mainWindow === null) {
    createWindow();
  }
}

function assertTrustedSender(event: IpcMainInvokeEvent): void {
  if (
    mainWindow === null ||
    event.sender !== mainWindow.webContents ||
    event.senderFrame !== mainWindow.webContents.mainFrame
  ) {
    throw new Error("拒绝来自未知窗口的请求");
  }
}

function registerIpcHandlers(): void {
  registerWindowControlHandlers({
    ipc: ipcMain,
    getWindow: () => mainWindow,
    assertTrustedSender,
  });

  ipcMain.handle("dialog:select-folder", async (event) => {
    assertTrustedSender(event);
    if (mainWindow === null) {
      return null;
    }
    const selected = await dialog.showOpenDialog(mainWindow, {
      title: "选择投标文件目录",
      buttonLabel: "选择这个目录",
      properties: ["openDirectory", "createDirectory", "dontAddToRecent"],
    });
    if (selected.canceled || selected.filePaths[0] === undefined) {
      return null;
    }
    try {
      await scanService?.discardResult();
    } catch {
      throw new Error("上一批核验结果未能安全清理，请关闭程序后重试");
    }
    selectedFolder = null;
    try {
      selectedFolder = await discoverFolder(selected.filePaths[0]);
    } catch {
      throw new Error("无法读取所选目录，请确认权限后重新选择");
    }
    return publicFolderSelection(selectedFolder);
  });

  ipcMain.handle("scan:start", async (event) => {
    assertTrustedSender(event);
    if (scanService === null) {
      throw new Error("离线核验服务尚未初始化");
    }
    if (selectedFolder === null) {
      throw new Error("请先通过文件夹选择窗口选择投标文件目录");
    }
    const sender = event.sender;
    return scanService.start(selectedFolder, (progress) => {
      if (!sender.isDestroyed()) {
        sender.send("scan:progress", progress);
      }
    });
  });

  ipcMain.handle("scan:stop", (event) => {
    assertTrustedSender(event);
    return scanService?.stop() ?? false;
  });

  ipcMain.handle("scan:document-detail", (event, documentId: unknown) => {
    assertTrustedSender(event);
    if (scanService === null || typeof documentId !== "string") {
      throw new Error("文档详情请求无效");
    }
    return scanService.documentDetail(documentId);
  });
}

function createWindow(): void {
  const window = new BrowserWindow({
    width: 1360,
    height: 900,
    minWidth: 980,
    minHeight: 700,
    frame: false,
    show: false,
    title: "围标串标投标人名称一致检测工具",
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
      void scanService?.dispose().catch(() => {
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

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});

app.on("before-quit", (event) => {
  if (allowImmediateQuit || scanService === null) {
    return;
  }
  event.preventDefault();
  if (quitStopPromise !== null) {
    return;
  }
  const service = scanService;
  quitStopPromise = service
    .dispose()
    .then(() => {
      allowImmediateQuit = true;
      app.quit();
    })
    .catch(() => {
      quitStopPromise = null;
      showStopFailure("无法安全退出", "核验进程尚未完全停止，请再次关闭程序重试。");
    });
});
