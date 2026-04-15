import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

type PackageJson = {
  dependencies?: Record<string, string>;
  version?: string;
};

function readPackageJson(path: string): PackageJson {
  return JSON.parse(readFileSync(path, "utf8")) as PackageJson;
}

test("installed pdfjs-dist matches the version required by react-pdf", () => {
  const currentDir = dirname(fileURLToPath(import.meta.url));
  const installedPdfjs = readPackageJson(
    resolve(currentDir, "../../node_modules/pdfjs-dist/package.json")
  );
  const reactPdf = readPackageJson(
    resolve(currentDir, "../../node_modules/react-pdf/package.json")
  );

  assert.equal(
    installedPdfjs.version,
    reactPdf.dependencies?.["pdfjs-dist"],
    "PdfEvidenceViewer worker must use the same pdfjs-dist version as react-pdf"
  );
});
