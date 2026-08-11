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
  minimize:
    '<svg viewBox="0 0 12 12" aria-hidden="true" focusable="false"><path d="M2 8.5h8"/></svg>',
  maximize:
    '<svg viewBox="0 0 12 12" aria-hidden="true" focusable="false"><rect x="2.25" y="2.25" width="7.5" height="7.5"/></svg>',
  restore:
    '<svg viewBox="0 0 12 12" aria-hidden="true" focusable="false"><path d="M4 2.5h5.5V8M2.5 4H8v5.5H2.5z"/></svg>',
  close:
    '<svg viewBox="0 0 12 12" aria-hidden="true" focusable="false"><path d="m2.5 2.5 7 7m0-7-7 7"/></svg>',
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
  controls.setAttribute("role", "group");
  controls.setAttribute("aria-label", "窗口控制");
  controls.append(
    controlButton("最小化窗口", "window-minimize", "window-control--minimize", ICONS.minimize, () =>
      options.controls.minimize(),
    ),
    controlButton(
      presentation.maximizeLabel,
      "window-maximize",
      "window-control--maximize",
      ICONS[presentation.maximizeIcon],
      async () => options.onStateChanged(await options.controls.toggleMaximize()),
    ),
    controlButton("关闭窗口", "window-close", "window-control--close", ICONS.close, () =>
      options.controls.close(),
    ),
  );
  return controls;
}
