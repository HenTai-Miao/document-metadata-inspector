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

    expect(() =>
      handlers.get(WINDOW_CONTROL_CHANNELS.getState)?.({} as IpcMainInvokeEvent),
    ).toThrow("主窗口不可用");
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

    expect(() =>
      handlers.get(WINDOW_CONTROL_CHANNELS.minimize)?.({} as IpcMainInvokeEvent),
    ).toThrow("拒绝来自未知窗口的请求");
    expect(target.minimize).not.toHaveBeenCalled();
  });
});
