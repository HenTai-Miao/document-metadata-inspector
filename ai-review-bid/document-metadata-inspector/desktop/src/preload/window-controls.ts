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
