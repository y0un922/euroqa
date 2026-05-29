import { useEffect, useState } from "react";

import EvidencePanel from "./components/EvidencePanel";
import LoginPage from "./components/LoginPage";
import MainWorkspace from "./components/MainWorkspace";
import Sidebar from "./components/Sidebar";
import TopBar from "./components/TopBar";
import { useDocumentImport } from "./hooks/useDocumentImport";
import { useEuroQaDemo } from "./hooks/useEuroQaDemo";
import { checkAuthRequired } from "./lib/api";
import { isAuthenticated, onAuthExpired } from "./lib/auth";

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
  const demo = useEuroQaDemo();
  const docImport = useDocumentImport({
    onComplete: demo.refreshDocuments,
  });

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-stone-50 font-sans text-stone-900 selection:bg-cyan-100 selection:text-cyan-900">
      <TopBar
        apiState={demo.apiState}
        conversationId={demo.conversationId}
        documentCount={demo.documents.length}
        glossaryCount={demo.glossary.length}
        llmApiKeyConfigured={demo.llmApiKeyConfigured}
        llmDefaultSettings={demo.llmDefaultSettings}
        llmSettings={demo.llmSettings}
        messages={demo.messages}
        onResetLlmSettings={demo.resetLlmSettings}
        onSaveLlmSettings={demo.saveLlmSettings}
      />
      <div className="flex flex-1 overflow-hidden">
        <Sidebar
          activeSessionId={demo.activeSessionId}
          documents={demo.documents}
          glossary={demo.glossary}
          historySessions={demo.historySessions}
          hotQuestions={demo.hotQuestions}
          onNewSession={demo.newSession}
          onSelectHistorySession={demo.selectHistorySession}
          onSelectHotQuestion={demo.askQuestion}
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
          messages={demo.messages}
          onDraftQuestionChange={demo.setDraftQuestion}
          onReferenceClick={demo.setActiveReferenceId}
          onRegenerateAnswer={demo.regenerateAnswer}
          onSelectHotQuestion={demo.askQuestion}
          onStop={demo.stopStreaming}
          onSubmit={demo.submitDraftQuestion}
        />
        <EvidencePanel
          activeReference={demo.activeReference}
          onPdfLocationResolved={demo.setPdfLocationStatus}
          onSourceTranslationEnabledChange={demo.setSourceTranslationEnabled}
          pdfFileUrl={demo.activeReferencePdfUrl}
          pdfLocationStatus={demo.pdfLocationStatus}
          sourceTranslation={demo.activeSourceTranslation}
          sourceTranslationEnabled={demo.sourceTranslationEnabled}
          sourceTranslationError={demo.sourceTranslationError}
          sourceTranslationLoading={demo.sourceTranslationLoading}
        />
      </div>
    </div>
  );
}
