import assert from "node:assert/strict";
import test from "node:test";

import { buildPdfViewerPayload } from "./evidencePanelPdf.ts";

test("buildPdfViewerPayload keeps page navigation but drops highlight inputs", () => {
  const payload = buildPdfViewerPayload(
    {
      id: "ref-1",
      documentId: "EN1992-1-1_2004",
      confidence: "high",
      relatedRefs: [],
      source: {
        file: "EN1992-1-1_2004.pdf",
        document_id: "EN1992-1-1_2004",
        title: "EN1992-1-1_2004.pdf",
        section: "6.1",
        page: "83",
        clause: "6.1",
        original_text: "Concrete ultimate compressive strain",
        locator_text: "Concrete ultimate compressive strain",
        highlight_text: "Concrete ultimate compressive strain",
        translation: ""
      }
    },
    null
  );

  assert.deepEqual(payload, {
    fileUrl: "http://localhost:8080/api/v1/documents/EN1992-1-1_2004/file",
    page: 83
  });
});
