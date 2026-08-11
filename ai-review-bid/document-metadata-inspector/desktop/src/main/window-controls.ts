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
