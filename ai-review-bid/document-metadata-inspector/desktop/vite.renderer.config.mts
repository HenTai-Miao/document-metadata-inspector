import { lstat, readFile } from "node:fs/promises";
import type { ServerResponse } from "node:http";

import { defineConfig, type Plugin } from "vite";

import { discoverFolder, publicFolderSelection } from "./src/main/folder-discovery";
import { adaptComparisonReport, adaptReportDocumentDetail } from "./src/main/report-adapter";
import type { ComparisonReportJson } from "./src/shared/contracts";

function contentSecurityPolicyPlugin(): Plugin {
  let developmentServer = false;
  return {
    name: "docmeta-content-security-policy",
    configResolved(config) {
      developmentServer = config.command === "serve";
    },
    transformIndexHtml(html) {
      return html.replace(
        "__DOCMETA_STYLE_SOURCE__",
        developmentServer ? "'self' 'unsafe-inline'" : "'self'",
      );
    },
  };
}

function sendJson(response: ServerResponse, status: number, value: unknown): void {
  response.statusCode = status;
  response.setHeader("Content-Type", "application/json; charset=utf-8");
  response.setHeader("Cache-Control", "no-store");
  response.end(JSON.stringify(value));
}

function previewPlugin(): Plugin | null {
  const folder = process.env.DOCMETA_PREVIEW_FOLDER;
  const reportPath = process.env.DOCMETA_PREVIEW_REPORT;
  if (folder === undefined || reportPath === undefined) {
    return null;
  }
  return {
    name: "docmeta-real-preview",
    configureServer(server) {
      let activeReport: ComparisonReportJson | null = null;
      server.middlewares.use(async (request, response, next) => {
        const pathname = new URL(request.url ?? "/", "http://127.0.0.1").pathname;
        if (!pathname.startsWith("/__docmeta/")) {
          next();
          return;
        }
        try {
          if (pathname === "/__docmeta/selection" && request.method === "GET") {
            sendJson(response, 200, publicFolderSelection(await discoverFolder(folder)));
            return;
          }
          if (pathname === "/__docmeta/start" && request.method === "POST") {
            const metadata = await lstat(reportPath);
            if (!metadata.isFile() || metadata.isSymbolicLink()) {
              throw new Error("真实预览报告缺失或不是普通文件");
            }
            const report = JSON.parse(await readFile(reportPath, "utf8")) as ComparisonReportJson;
            activeReport = report;
            const selection = await discoverFolder(folder);
            await new Promise((resolveDelay) => setTimeout(resolveDelay, 1_000));
            sendJson(response, 200, adaptComparisonReport(report, selection));
            return;
          }
          if (pathname.startsWith("/__docmeta/details/") && request.method === "GET") {
            const documentId = decodeURIComponent(pathname.slice("/__docmeta/details/".length));
            const detail =
              activeReport === null ? null : adaptReportDocumentDetail(activeReport, documentId);
            if (detail === null) {
              sendJson(response, 404, { error: "preview detail not found" });
              return;
            }
            sendJson(response, 200, detail);
            return;
          }
          if (pathname === "/__docmeta/stop" && request.method === "POST") {
            sendJson(response, 200, { stopped: true });
            return;
          }
          sendJson(response, 404, { error: "preview route not found" });
        } catch (error) {
          sendJson(response, 500, {
            error: error instanceof Error ? error.message : "真实预览失败",
          });
        }
      });
    },
  };
}

export default defineConfig({
  base: "./",
  server: {
    host: "127.0.0.1",
    strictPort: true,
  },
  plugins: [contentSecurityPolicyPlugin(), previewPlugin()].filter(
    (plugin): plugin is Plugin => plugin !== null,
  ),
});
