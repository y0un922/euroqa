# Phase 1: API 层 AbortSignal

- [ ] T1: queryStream / readSseStream 添加 AbortSignal 支持

## Acceptance Criteria
- queryStream 接受 signal?: AbortSignal
- readSseStream 接受 signal?: AbortSignal
- fetch 传入 signal
- abort 时抛出可区分的错误
