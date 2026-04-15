# Frontend Chat UX Analysis

## Task

Add 3 features: (1) action bar below answers, (2) regenerate, (3) stop streaming.

## Architecture Summary

```
App.tsx
  └── useEuroQaDemo() hook (all state)
      ├── MainWorkspace.tsx (chat UI, submit, messages)
      ├── EvidencePanel.tsx (PDF viewer)
      └── Sidebar.tsx / TopBar.tsx
```

All state lives in `useEuroQaDemo.ts`; components communicate via props drilling through `App.tsx`.

## Key State

| Variable | Type | Location |
|----------|------|----------|
| `isSubmitting` | `boolean` | useEuroQaDemo.ts |
| `messages` | `ChatTurn[]` | useEuroQaDemo.ts |
| `draftQuestion` | `string` | useEuroQaDemo.ts |
| `copyFeedback` | `{messageId, tone}` | MainWorkspace.tsx local |

## Streaming Flow

```
submitDraftQuestion() → askQuestion(q)
  → queryStream(payload, {onReasoning, onChunk, onDone})
    → fetch POST /api/v1/query/stream (NO AbortController)
      → readSseStream(stream, handler) (NO signal)
        → onChunk: setMessages(m => m.answer += text)
        → onDone: setMessages(m => status="done", sources=...)
  → finally: setIsSubmitting(false)
```

## Gap Analysis

| Feature | Current State | Gap |
|---------|--------------|-----|
| Copy icon | Exists as text button in header (MainWorkspace.tsx:366-404) | Move to bottom action bar as icon |
| Regenerate | Not implemented | Need new `regenerateAnswer()` in hook |
| Stop streaming | No AbortController anywhere | Need signal in api.ts + hook ref |

## Files to Modify

| File | Changes |
|------|---------|
| `api.ts` | Add `signal?: AbortSignal` to `queryStream` and `readSseStream` |
| `useEuroQaDemo.ts` | Add `AbortController` ref, `regenerateAnswer()`, `stopStreaming()` |
| `App.tsx` | Pass new callbacks to MainWorkspace |
| `MainWorkspace.tsx` | Remove header copy button, add bottom action bar, swap submit/stop button |
