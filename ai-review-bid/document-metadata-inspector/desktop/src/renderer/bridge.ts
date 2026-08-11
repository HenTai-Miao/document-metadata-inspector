import type {
  DocmetaBridge,
  FolderSelection,
  ScanProgress,
  ScanResult,
  WindowControlsBridge,
  WindowState,
} from "../shared/contracts";

const previewListeners = new Set<(progress: ScanProgress) => void>();
let previewController: AbortController | null = null;
let previewTimers: number[] = [];

function emitPreview(progress: ScanProgress): void {
  for (const listener of previewListeners) {
    listener(progress);
  }
}

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { Accept: "application/json", ...init?.headers },
  });
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `预览服务返回 ${response.status}`);
  }
  return (await response.json()) as T;
}

function clearPreviewTimers(): void {
  for (const timer of previewTimers) {
    window.clearTimeout(timer);
  }
  previewTimers = [];
}

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

const browserPreviewBridge: DocmetaBridge = {
  windowControls: previewWindowControls,
  selectFolder: () => fetchJson<FolderSelection>("/__docmeta/selection"),
  async startScan(): Promise<ScanResult> {
    if (previewController !== null) {
      throw new Error("已有核验任务正在运行");
    }
    previewController = new AbortController();
    emitPreview({ stage: "preparing", message: "正在确认投标人目录和文件边界", percent: 8 });
    previewTimers = [
      window.setTimeout(
        () =>
          emitPreview({
            stage: "extracting",
            message: "三个离线解析引擎正在提取元数据",
            percent: 42,
          }),
        120,
      ),
      window.setTimeout(
        () =>
          emitPreview({
            stage: "comparing",
            message: "正在核对不同投标人之间的身份痕迹",
            percent: 84,
          }),
        620,
      ),
    ];
    try {
      return await fetchJson<ScanResult>("/__docmeta/start", {
        method: "POST",
        signal: previewController.signal,
      });
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        throw new Error("核验已停止");
      }
      throw error;
    } finally {
      clearPreviewTimers();
      previewController = null;
    }
  },
  async stopScan(): Promise<boolean> {
    const running = previewController !== null;
    previewController?.abort();
    clearPreviewTimers();
    emitPreview({ stage: "stopped", message: "核验已停止，可以重新开始", percent: 0 });
    await fetchJson<{ stopped: boolean }>("/__docmeta/stop", { method: "POST" }).catch(() => ({
      stopped: running,
    }));
    return running;
  },
  onScanProgress(listener): () => void {
    previewListeners.add(listener);
    return () => previewListeners.delete(listener);
  },
};

function isLocalPreview(): boolean {
  return (
    import.meta.env.DEV &&
    (window.location.hostname === "127.0.0.1" || window.location.hostname === "localhost")
  );
}

export function getDocmetaBridge(): DocmetaBridge {
  if (window.docmeta !== undefined) {
    return window.docmeta;
  }
  if (isLocalPreview()) {
    return browserPreviewBridge;
  }
  throw new Error("桌面安全桥未加载，请从 Electron 程序启动此页面");
}
