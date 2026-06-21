import { useCallback, useEffect, useRef, useState } from "react";

import EvidencePanel from "./components/EvidencePanel";
import IndexAdminPage from "./components/IndexAdminPage";
import KnowledgeBasesPage from "./components/KnowledgeBasesPage";
import LoginPage from "./components/LoginPage";
import MainWorkspace from "./components/MainWorkspace";
import Sidebar from "./components/Sidebar";
import TopBar from "./components/TopBar";
import { useDocumentImport } from "./hooks/useDocumentImport";
import { useEuroQaDemo } from "./hooks/useEuroQaDemo";
import { checkAuthRequired, listKnowledgeBases } from "./lib/api";
import { isAuthenticated, onAuthExpired } from "./lib/auth";
import type { KnowledgeBaseInfo } from "./lib/types";

function useStableCallback<T extends (...args: any[]) => unknown>(
  callback: T
): T {
  const callbackRef = useRef(callback);
  callbackRef.current = callback;

  return useCallback(
    ((...args: Parameters<T>) => callbackRef.current(...args)) as T,
    []
  );
}

export default function App() {
  const [authRequired, setAuthRequired] = useState<boolean | null>(null);
  const [authCheckFailed, setAuthCheckFailed] = useState(false);
  const [loggedIn, setLoggedIn] = useState(() => isAuthenticated());

  useEffect(() => {
    checkAuthRequired()
      .then(setAuthRequired)
      .catch(() => setAuthCheckFailed(true));
  }, []);

  useEffect(() => onAuthExpired(() => setLoggedIn(false)), []);

  if (authCheckFailed) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-stone-50 text-stone-700">
        <div className="text-center">
          <p className="text-lg">无法连接到服务器</p>
          <button
            className="mt-4 rounded-md bg-cyan-800 px-4 py-2 text-sm text-white hover:bg-cyan-900"
            onClick={() => window.location.reload()}
          >
            重试
          </button>
        </div>
      </main>
    );
  }

  if (authRequired === null) {
    return null;
  }

  if (authRequired && !loggedIn) {
    return <LoginPage onLogin={() => setLoggedIn(true)} />;
  }

  return <AuthenticatedApp />;
}

function AuthenticatedApp() {
  const [currentView, setCurrentView] = useState<
    "chat" | "knowledge-bases" | "index-admin"
  >("chat");
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBaseInfo[]>([]);
  const demo = useEuroQaDemo();
  const handleRefreshDocuments = useStableCallback(demo.refreshDocuments);
  const refreshKnowledgeBases = useStableCallback(async () => {
    try {
      const nextKnowledgeBases = await listKnowledgeBases();
      setKnowledgeBases(nextKnowledgeBases);
    } catch {
      setKnowledgeBases([]);
    }
  });
  const docImport = useDocumentImport({
    onComplete: handleRefreshDocuments,
  });
  const handleResetLlmSettings = useStableCallback(demo.resetLlmSettings);
  const handleSaveLlmSettings = useStableCallback(demo.saveLlmSettings);
  const handleNewSession = useStableCallback(demo.newSession);
  const handleSelectHistorySession = useStableCallback(
    demo.selectHistorySession
  );
  const handleDeleteHistorySession = useStableCallback(
    demo.deleteHistorySession
  );
  const handleAskQuestion = useStableCallback(demo.askQuestion);
  const handleDraftQuestionChange = useStableCallback(demo.setDraftQuestion);
  const handleReferenceClick = useStableCallback(demo.setActiveReferenceId);
  const handleRegenerateAnswer = useStableCallback(demo.regenerateAnswer);
  const handleStopStreaming = useStableCallback(demo.stopStreaming);
  const handleSubmitDraftQuestion = useStableCallback(demo.submitDraftQuestion);
  const handlePdfLocationResolved = useStableCallback(demo.setPdfLocationStatus);
  const handleSourceTranslationEnabledChange = useStableCallback(
    demo.setSourceTranslationEnabled
  );
  const handleSelectedKbIdsChange = useStableCallback(demo.setSelectedKbIds);

  useEffect(() => {
    void refreshKnowledgeBases();
  }, [refreshKnowledgeBases]);

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-stone-50 font-sans text-stone-900 selection:bg-cyan-100 selection:text-cyan-900">
      <TopBar
        apiState={demo.apiState}
        conversationId={demo.conversationId}
        currentView={currentView}
        documentCount={demo.documents.length}
        glossaryCount={demo.glossary.length}
        llmApiKeyConfigured={demo.llmApiKeyConfigured}
        llmDefaultSettings={demo.llmDefaultSettings}
        llmSettings={demo.llmSettings}
        messages={demo.messages}
        onViewChange={setCurrentView}
        onResetLlmSettings={handleResetLlmSettings}
        onSaveLlmSettings={handleSaveLlmSettings}
      />
      {currentView === "knowledge-bases" ? (
        <KnowledgeBasesPage
          documents={demo.documents}
          knowledgeBases={knowledgeBases}
          onDocumentsChanged={handleRefreshDocuments}
          onRefreshKnowledgeBases={refreshKnowledgeBases}
        />
      ) : currentView === "index-admin" ? (
        <IndexAdminPage documents={demo.documents} />
      ) : (
        <div className="flex flex-1 overflow-hidden">
          <Sidebar
            activeSessionId={demo.activeSessionId}
            documents={demo.documents}
            glossary={demo.glossary}
            historySessions={demo.historySessions}
            hotQuestions={demo.hotQuestions}
            onNewSession={handleNewSession}
            onSelectHistorySession={handleSelectHistorySession}
            onDeleteHistorySession={handleDeleteHistorySession}
            onSelectHotQuestion={handleAskQuestion}
            onUploadFile={docImport.handleUpload}
            onDeleteDocument={docImport.handleDelete}
            processingDocId={docImport.processingDocId}
            pipelineStage={docImport.pipelineStage}
            pipelineProgress={docImport.pipelineProgress}
          />
          <MainWorkspace
            activeReferenceId={demo.activeReferenceId}
            apiState={demo.apiState}
            bootError={demo.bootError}
            documents={demo.documents}
            draftQuestion={demo.draftQuestion}
            hotQuestions={demo.hotQuestions}
            isSubmitting={demo.isSubmitting}
            knowledgeBases={knowledgeBases}
            messages={demo.messages}
            onDraftQuestionChange={handleDraftQuestionChange}
            onReferenceClick={handleReferenceClick}
            onRegenerateAnswer={handleRegenerateAnswer}
            onSelectHotQuestion={handleAskQuestion}
            onSelectedKbIdsChange={handleSelectedKbIdsChange}
            onStop={handleStopStreaming}
            onSubmit={handleSubmitDraftQuestion}
            selectedKbIds={demo.selectedKbIds}
          />
          <EvidencePanel
            activeReference={demo.activeReference}
            onPdfLocationResolved={handlePdfLocationResolved}
            onSourceTranslationEnabledChange={
              handleSourceTranslationEnabledChange
            }
            pdfFileUrl={demo.activeReferencePdfUrl}
            pdfLocationStatus={demo.pdfLocationStatus}
            sourceTranslation={demo.activeSourceTranslation}
            sourceTranslationEnabled={demo.sourceTranslationEnabled}
            sourceTranslationError={demo.sourceTranslationError}
            sourceTranslationLoading={demo.sourceTranslationLoading}
          />
        </div>
      )}
    </div>
  );
}
