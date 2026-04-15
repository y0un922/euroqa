# LLM 回复复制与会话导出 Dependency Graph

## 说明

- 图中按阶段展示任务依赖关系
- 带 `Lane` 的 subgraph 表示可并行执行的任务组
- 无 lane 的阶段表示建议顺序执行

```mermaid
flowchart TB
  subgraph Phase1["Phase 1: 后端导出契约与检索快照标准化"]
    P1T1["P1-T1 定义 retrieval context DTO"]
    P1T2["P1-T2 构建共享 snapshot builder"]
    P1T3["P1-T3 扩展 /query 与 /query/stream 完成态"]
    P1T1 --> P1T2 --> P1T3
  end

  subgraph Phase2["Phase 2: 前端数据接入与会话持久化"]
    P2T1["P2-T1 扩展前端 types/api"]
    P2T2["P2-T2 hook 接入 stream + fallback"]
    P2T3["P2-T3 localStorage 持久化与迁移"]
    P2T1 --> P2T2 --> P2T3
  end

  subgraph Phase3["Phase 3: Markdown 导出器与复制/下载动作封装"]
    P3T1["P3-T1 冻结 Markdown 模板"]
    P3T2["P3-T2 实现共享格式化基础"]

    subgraph Phase3LaneA["Lane A"]
      P3T3["P3-T3 单条消息 Markdown builder"]
    end

    subgraph Phase3LaneB["Lane B"]
      P3T4["P3-T4 整会话 Markdown builder"]
    end

    P3T5["P3-T5 复制/下载动作与测试"]

    P3T1 --> P3T2
    P3T2 --> P3T3
    P3T2 --> P3T4
    P3T3 --> P3T5
    P3T4 --> P3T5
  end

  subgraph Phase4["Phase 4: UI 集成与交互反馈"]
    P4T1["P4-T1 暴露 hook/action 与反馈状态"]

    subgraph Phase4LaneA["Lane A"]
      P4T2["P4-T2 MainWorkspace 单条复制按钮"]
    end

    subgraph Phase4LaneB["Lane B"]
      P4T3["P4-T3 TopBar 整会话导出入口"]
    end

    P4T4["P4-T4 统一禁用态、文案与可访问性"]

    P4T1 --> P4T2
    P4T1 --> P4T3
    P4T2 --> P4T4
    P4T3 --> P4T4
  end

  subgraph Phase5["Phase 5: 回归验证与交付收口"]
    subgraph Phase5LaneA["Lane A"]
      P5T1["P5-T1 后端回归测试"]
    end

    subgraph Phase5LaneB["Lane B"]
      P5T2["P5-T2 前端回归测试"]
    end

    P5T3["P5-T3 人工验证清单"]

    P5T1 --> P5T3
    P5T2 --> P5T3
  end

  P1T3 --> P2T1
  P2T3 --> P3T1
  P3T5 --> P4T1
  P4T4 --> P5T1
  P4T4 --> P5T2
```

## 关键依赖解读

- `P1-T3 -> P2-T1`
  前端只有在后端完成新协议后，才能稳定接入 retrieval context。

- `P2-T3 -> P3-T1`
  Markdown 模板需要基于最终落库后的 `ChatTurn` 结构来定稿，否则后续 builder 会反复返工。

- `P3-T5 -> P4-T1`
  UI 集成应依赖稳定的导出器和动作层，而不是在组件里直接拼 Markdown。

- `P4-T4 -> P5-T1/P5-T2`
  自动化测试应在最终交互规则固定后补齐，避免测试围绕临时文案和禁用态频繁失效。

## 并行窗口

- Window 1:
  `P3-T3` 与 `P3-T4` 可并行
- Window 2:
  `P4-T2` 与 `P4-T3` 可并行
- Window 3:
  `P5-T1` 与 `P5-T2` 可并行

## 不建议并行的热点

- `frontend/src/hooks/useEuroQaDemo.ts`
  会同时承接 retrieval context 写入、动作暴露、UI 状态反馈，是实现期热点文件。

- `server/core/generation.py`
  会同时承接 snapshot builder 和完成态元数据，建议单人顺序修改。
