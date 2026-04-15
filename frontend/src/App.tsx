import EvidencePanel from "./components/EvidencePanel";
import MainWorkspace from "./components/MainWorkspace";
import Sidebar from "./components/Sidebar";
import TopBar from "./components/TopBar";
import { useDocumentImport } from "./hooks/useDocumentImport";
import { useEuroQaDemo } from "./hooks/useEuroQaDemo";

export default function App() {
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
          documents={demo.documents}
          glossary={demo.glossary}
          hotQuestions={demo.hotQuestions}
          onNewSession={demo.newSession}
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
