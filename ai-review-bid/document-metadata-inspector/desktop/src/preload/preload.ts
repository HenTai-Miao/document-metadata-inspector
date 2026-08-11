import { contextBridge, ipcRenderer } from "electron";

import type { DocmetaBridge, FolderSelection, ScanProgress, ScanResult } from "../shared/contracts";
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

contextBridge.exposeInMainWorld("docmeta", bridge);
