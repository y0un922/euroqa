# PDF 证据面板优化 — 依赖关系图

## 整体依赖图

```mermaid
graph TD
    subgraph P1["Phase 1: Foundation"]
        P1T1["P1-T1\n删除 conflict 文件\nS · 1-A"]
        P1T2["P1-T2\nlayout test 语义断言\nS · 1-A"]
        P1T3["P1-T3\npdfLocator 锚点测试\nM · 1-B"]
        P1T4["P1-T4\ncitations 锚点测试\nM · 1-B"]
    end

    subgraph P2["Phase 2: Matching Logic"]
        P2T1["P2-T1\n清理 highlight_text\nM · 2-A"]
        P2T2["P2-T2\n降低 isStrong 阈值\nM · 2-B"]
        P2T3["P2-T3\n反向包含检查\nM · 2-B"]
        P2T4["P2-T4\npage 软 boost\nM · 2-C"]
        P2T5["P2-T5\npart 号匹配\nS · 2-C"]
        P2T6["P2-T6\nscroll-to-highlight\nL · 2-D ★"]
    end

    subgraph P3["Phase 3: Visual Redesign"]
        P3T1["P3-T1\n移除标题栏+chips\nM · 3-A"]
        P3T2["P3-T2\nPDF背景+骨架屏\nS · 3-A"]
        P3T3["P3-T3\n翻译区稳定\nS · 3-A"]
        P3T4["P3-T4\nmark青色样式\nS · 3-C"]
        P3T5["P3-T5\nbbox淡入\nS · 3-D"]
        P3T6["P3-T6\n空状态重设计\nS · 3-A"]
        P3T7["P3-T7\ntoggle状态\nS · 3-A"]
    end

    subgraph P4["Phase 4: Polish"]
        P4T1["P4-T1\n响应式抽屉\nL · 4-A"]
        P4T2["P4-T2\nE2E验证\nM · 4-B"]
        P4T3["P4-T3\n更新文档\nS · 4-C"]
    end

    P1T1 --> P2T1
    P1T1 --> P2T6
    P1T3 --> P2T2
    P1T4 --> P2T4

    P2T2 --> P2T3
    P2T4 --> P2T5

    P2T6 --> P3T1
    P2T6 --> P3T5
    P2T2 --> P3T4

    P3T1 --> P3T2
    P3T2 --> P3T3
    P3T3 --> P3T6
    P3T6 --> P3T7

    P3T7 --> P4T1
    P3T4 --> P4T1
    P3T5 --> P4T1
    P3T7 --> P4T2
    P3T4 --> P4T2
    P3T5 --> P4T2

    P4T2 --> P4T3

    classDef laneA fill:#dbeafe,stroke:#3b82f6
    classDef laneB fill:#dcfce7,stroke:#22c55e
    classDef laneC fill:#fef9c3,stroke:#eab308
    classDef laneD fill:#fce7f3,stroke:#ec4899
    classDef critical fill:#fee2e2,stroke:#ef4444,stroke-width:2px

    class P1T1,P1T2 laneA
    class P1T3,P1T4 laneB
    class P2T1 laneA
    class P2T2,P2T3 laneB
    class P2T4,P2T5 laneC
    class P2T6 critical
    class P3T1,P3T2,P3T3,P3T6,P3T7 laneA
    class P3T4 laneC
    class P3T5 laneD
    class P4T1 critical
    class P4T2 laneB
    class P4T3 laneC
```

## 关键路径

```
P1-T3(3h) → P2-T6(6h) → P3-T1(3h) → P3-T2(1h) → P3-T3(1h) → P3-T6(1h) → P3-T7(1h) → P4-T2(2h)
```

**最小挂钟时间**: ~16h（Phase 1: 3h + Phase 2: 6h + Phase 3: 5h + Phase 4: 2h）

## 并行通道时间轴

```
Phase 1 (3h)
  1-A │ T1(S) │ T2(S) │
  1-B │ T3(M)         │ T4(M) │

Phase 2 (6h)
  2-A │ T1(M ~2h)              │
  2-B │ T2(M) │ T3(M)          │
  2-C │ T4(M ~2h) │ T5(S)      │
  2-D │ T6(L ~6h) ← 关键路径   │

Phase 3 (5h)
  3-A │ T1(M) │ T2(S) │ T3(S) │ T6(S) │ T7(S) │ ← 关键路径
  3-C │ T4(S)                                    │
  3-D │ T5(S)                                    │

Phase 4 (5h)
  4-A │ T1(L ~5h) ← 可选       │
  4-B │ T2(M ~2h)               │
  4-C │     T3(S)               │
```
