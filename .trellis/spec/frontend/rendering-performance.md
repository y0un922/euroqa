# Rendering Performance

## Scope

This spec applies to React components that render chat history, document lists,
history sessions, Markdown answers, citations, and other large repeated UI
surfaces.

## Contracts

- Keep high-frequency input state isolated from expensive display surfaces.
  Typing into a question composer must not re-render full chat history,
  Markdown answers, citation lists, document lists, or session history.
- Wrap large repeated surfaces in `React.memo` when their props can remain
  referentially stable during unrelated input updates.
- Parent components that pass callbacks into memoized surfaces should use stable
  callback wrappers so unchanged data props are not invalidated by function
  identity churn.
- Optional actions must keep their original enabled/disabled semantics when
  wrapped in stable callbacks.
- Prefer splitting components by update frequency before adding virtualization.
  Virtualization is appropriate only when memo boundaries are insufficient.
- Completed chat turns may display response telemetry such as token usage and
  elapsed time, but that metadata must stay inside the turn card and not leak
  into the composer or other high-frequency inputs.
- Render token usage and elapsed time only when the turn has finished and the
  data is available; do not synthesize placeholder metrics for in-flight turns.

## Tests Required

- Run frontend type-check and relevant component tests after changing render
  boundaries.
- Run a production build when memoization touches top-level layout components.
