import type { AppAction } from "./state";

export function scanFailureAction(token: number, message: string): AppAction {
  if (message === "核验已停止") {
    return { type: "scanStopped", token };
  }
  if (message.includes("未能安全停止") || message.includes("临时文件未能安全清理")) {
    return { type: "scanStopFailed", token, error: message };
  }
  return { type: "scanFailed", token, error: message };
}
