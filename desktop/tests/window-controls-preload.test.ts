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
