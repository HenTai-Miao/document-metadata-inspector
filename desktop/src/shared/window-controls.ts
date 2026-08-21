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
