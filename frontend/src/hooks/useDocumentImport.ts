import { useCallback, useEffect, useRef, useState } from "react";

import {
  deleteDocument,
  listDocuments,
  processDocument,
  subscribeToPipelineStatus,
  uploadDocument,
} from "../lib/api";
import type { DocumentStatus, PipelineProgressEvent } from "../lib/types";

type UseDocumentImportOptions = {
  onComplete?: () => void;
};

export type DocumentImportState = {
  isUploading: boolean;
  processingDocId: string | null;
  pipelineStage: DocumentStatus | null;
  pipelineProgress: number;
  error: string | null;
  handleUpload: (file: File) => Promise<void>;
  handleDelete: (docId: string) => Promise<void>;
};

export function useDocumentImport(
  options: UseDocumentImportOptions = {}
): DocumentImportState {
  const { onComplete } = options;
  const [isUploading, setIsUploading] = useState(false);
  const [processingDocId, setProcessingDocId] = useState<string | null>(null);
  const [pipelineStage, setPipelineStage] = useState<DocumentStatus | null>(null);
  const [pipelineProgress, setPipelineProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const unsubscribeRef = useRef<(() => void) | null>(null);

  // 页面刷新恢复：检测后端是否有正在处理的文档，自动重连 SSE
  useEffect(() => {
    if (processingDocId) return;
    const TERMINAL: Set<string> = new Set(["ready", "uploaded", "error"]);
    listDocuments()
      .then((docs) => {
        const active = docs.find((d) => d.status && !TERMINAL.has(d.status));
        if (active) {
          setProcessingDocId(active.id);
          setPipelineStage(active.status as DocumentStatus);
          setPipelineProgress(0);
        }
      })
      .catch(() => {/* 静默失败 */});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // SSE 订阅管理
  useEffect(() => {
    if (!processingDocId) return;

    const unsub = subscribeToPipelineStatus(
      processingDocId,
      (event: PipelineProgressEvent) => {
        setPipelineStage(event.stage as DocumentStatus);
        setPipelineProgress(event.progress);
        if (event.error) setError(event.error);
      },
      (_event: PipelineProgressEvent) => {
        setProcessingDocId(null);
        setPipelineStage(null);
        setPipelineProgress(0);
        onComplete?.();
      },
      (errMsg: string) => {
        setError(errMsg);
        setProcessingDocId(null);
        setPipelineStage(null);
      }
    );
    unsubscribeRef.current = unsub;

    return () => {
      unsub();
      unsubscribeRef.current = null;
    };
  }, [processingDocId, onComplete]);

  const handleUpload = useCallback(async (file: File) => {
    setError(null);
    setIsUploading(true);
    let docId: string | null = null;
    try {
      const result = await uploadDocument(file);
      docId = result.doc_id;
      setIsUploading(false);

      setProcessingDocId(docId);
      setPipelineStage("pending");
      setPipelineProgress(0);
      await processDocument(docId);
    } catch (err) {
      setIsUploading(false);
      setProcessingDocId(null);
      setPipelineStage(null);
      setPipelineProgress(0);
      setError(err instanceof Error ? err.message : String(err));
      if (docId) onComplete?.();
    }
  }, [onComplete]);

  const handleDelete = useCallback(async (docId: string) => {
    setError(null);
    try {
      await deleteDocument(docId);
      onComplete?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [onComplete]);

  return {
    isUploading,
    processingDocId,
    pipelineStage,
    pipelineProgress,
    error,
    handleUpload,
    handleDelete,
  };
}
