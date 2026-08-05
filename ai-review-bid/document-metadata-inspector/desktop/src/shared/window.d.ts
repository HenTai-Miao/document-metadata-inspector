import type { DocmetaBridge } from "./contracts";

declare global {
  interface Window {
    docmeta?: DocmetaBridge;
  }
}
