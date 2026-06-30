import assert from "node:assert/strict";
import test from "node:test";

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ReactMarkdown from "react-markdown";

import MainWorkspace from "./MainWorkspace.tsx";
import type { ChatTurn } from "../lib/types.ts";

Object.assign(globalThis, { React });

test("MainWorkspace does not render follow-up suggestion chips in composer area", () => {
  const html = renderToStaticMarkup(
    React.createElement(MainWorkspace, {
      activeReferenceId: null,
      apiState: "ready",
      bootError: null,
      documents: [],
      draftQuestion: "",
      hotQuestions: [
        "请给出混凝土结构设计中相关作用荷载和材料的分项系数。",
        "请给出混凝土材料的强度与变形的相关定义、相互关系及如何计算。",
        "有哪些因素会对混凝土的徐变与收缩产生影响?",
        "钢筋的主要特性有哪些?并给出相应总结。",
        "请问都有那些环境暴露等级?",
        "保护层都与什么因素相关，该怎么计算?",
        "什么情况下需要考虑二阶效应？"
      ],
      isSubmitting: false,
      messages: [],
      onDraftQuestionChange: () => {},
      onReferenceClick: () => {},
      onSelectHotQuestion: () => {},
      onSubmit: () => {},
    })
  );

  assert.match(html, /已载入文档/);
  assert.match(html, /保护层都与什么因素相关，该怎么计算\?/);
  assert.doesNotMatch(html, /什么情况下需要考虑二阶效应？/);
  assert.doesNotMatch(html, /当前规范/);
  assert.doesNotMatch(html, /当前文档/);
  assert.doesNotMatch(html, /推荐追问/);
  assert.doesNotMatch(html, /自动意图识别/);
});

test("MainWorkspace hides display-layer controls and question type badges", () => {
  const messages: ChatTurn[] = [
    {
      id: "turn-1",
      question: "欧标的截面计算基本假设前提是什么？",
      answer: "### 直接答案\n完整回答第一段。\n\n### 关键依据\n完整回答第二段。",
      reasoning: "",
      status: "done",
      confidence: "high",
      sources: [],
      relatedRefs: [],
      degraded: false,
      usage: { input_tokens: 12, output_tokens: 34, total_tokens: 46 },
      elapsed_ms: 1234,
      questionType: "rule",
    }
  ];

  const html = renderToStaticMarkup(
    React.createElement(MainWorkspace, {
      activeReferenceId: null,
      apiState: "ready",
      bootError: null,
      documents: [],
      draftQuestion: "",
      hotQuestions: [],
      isSubmitting: false,
      messages,
      onDraftQuestionChange: () => {},
      onReferenceClick: () => {},
      onSelectHotQuestion: () => {},
      onSubmit: () => {},
    })
  );

  assert.match(html, /完整回答第一段/);
  assert.match(html, /完整回答第二段/);
  assert.doesNotMatch(html, /详略：/);
  assert.doesNotMatch(html, />现场</);
  assert.doesNotMatch(html, />设计</);
  assert.doesNotMatch(html, />审图</);
  assert.doesNotMatch(html, />rule</);
  assert.match(html, /Token 总 46 · 输入 12 · 输出 34/);
  assert.match(html, /耗时 1\.2s/);
  assert.doesNotMatch(html, /Table 2\.6/);
  assert.doesNotMatch(html, /EN 1998/);
});

test("MainWorkspace shows usage and elapsed time for finished turns", () => {
  const messages: ChatTurn[] = [
    {
      id: "turn-stream-done",
      question: "设计使用年限怎么确定？",
      answer: "回答内容。",
      reasoning: "",
      status: "done",
      confidence: "high",
      sources: [],
      relatedRefs: [],
      degraded: false,
      usage: { total_tokens: 88 },
      elapsed_ms: 245,
    },
  ];

  const html = renderToStaticMarkup(
    React.createElement(MainWorkspace, {
      activeReferenceId: null,
      apiState: "ready",
      bootError: null,
      documents: [],
      draftQuestion: "",
      hotQuestions: [],
      isSubmitting: false,
      messages,
      onDraftQuestionChange: () => {},
      onReferenceClick: () => {},
      onSelectHotQuestion: () => {},
      onSubmit: () => {},
    })
  );

  assert.match(html, /Token 总 88/);
  assert.match(html, /耗时 245ms/);
});

test("MainWorkspace does not fabricate tool calls from reasoning text", () => {
  const messages: ChatTurn[] = [
    {
      id: "turn-streaming",
      question: "设计使用年限怎么确定？",
      answer: "",
      reasoning: "先定位条文，再核对表格。",
      status: "streaming",
      confidence: "none",
      sources: [],
      relatedRefs: [],
      degraded: false,
    }
  ];

  const html = renderToStaticMarkup(
    React.createElement(MainWorkspace, {
      activeReferenceId: null,
      apiState: "ready",
      bootError: null,
      documents: [],
      draftQuestion: "",
      hotQuestions: [],
      isSubmitting: true,
      messages,
      onDraftQuestionChange: () => {},
      onReferenceClick: () => {},
      onSelectHotQuestion: () => {},
      onSubmit: () => {},
      onStop: () => {},
      onRegenerateAnswer: () => {},
    })
  );

  assert.doesNotMatch(html, /reasoning_trace/);
  assert.doesNotMatch(html, /先定位条文，再核对表格。/);
  assert.doesNotMatch(html, /深度思考/);
  assert.doesNotMatch(html, /模型正在深度思考/);
});

test("MainWorkspace does not fabricate tool calls from generic progress", () => {
  const messages: ChatTurn[] = [
    {
      id: "turn-progress",
      question: "设计使用年限怎么确定？",
      answer: "",
      reasoning: "",
      status: "done",
      confidence: "none",
      sources: [],
      relatedRefs: [],
      degraded: false,
      usage: { total_tokens: 88 },
      elapsed_ms: 245,
      commentaries: ["正在搜索规范知识库：「设计使用年限」..."],
      progressEvents: [
        {
          stage: "agent_thinking",
          status: "completed",
          title: "Agent 分析问题",
          summary: "Agent 正在理解问题并决定策略。"
        },
        {
          stage: "understanding",
          status: "completed",
          title: "理解问题",
          summary: "识别为参数/限值类问题，优先查找 EN 1990 相关条款。"
        },
        {
          stage: "retrieving",
          status: "running",
          title: "检索规范条文",
          summary: "正在检索规范条文..."
        }
      ]
    }
  ];

  const html = renderToStaticMarkup(
    React.createElement(MainWorkspace, {
      activeReferenceId: null,
      apiState: "ready",
      bootError: null,
      documents: [],
      draftQuestion: "",
      hotQuestions: [],
      isSubmitting: true,
      messages,
      onDraftQuestionChange: () => {},
      onReferenceClick: () => {},
      onSelectHotQuestion: () => {},
      onSubmit: () => {},
      onStop: () => {},
      onRegenerateAnswer: () => {},
    })
  );

  assert.doesNotMatch(html, /query_rewrite/);
  assert.doesNotMatch(html, /tool_calling/);
  assert.doesNotMatch(html, /改写查询并规划检索策略/);
  assert.doesNotMatch(html, /调用欧标检索工具/);
  assert.doesNotMatch(html, /Agent 分析问题/);
  assert.match(html, /Token 总 88/);
  assert.match(html, /耗时 245ms/);
  assert.doesNotMatch(html, /Table 2\.6/);
});

test("MainWorkspace ignores legacy tool progress cards without sub-step events", () => {
  const messages: ChatTurn[] = [
    {
      id: "turn-legacy-tool",
      question: "长细比是如何定义的？",
      answer: "",
      reasoning: "",
      status: "streaming",
      confidence: "none",
      sources: [],
      relatedRefs: [],
      degraded: false,
      progressEvents: [
        {
          stage: "tool:retrieve",
          status: "completed",
          title: "检索规范知识库",
          summary: "检索到 3 个片段。",
          facts: {
            tool_name: "retrieve",
            tool_args: { query: "slenderness ratio definition", top_k: 6 },
            tool_trace: { expanded_queries: ["slenderness ratio", "长细比"] }
          }
        }
      ]
    }
  ];

  const html = renderToStaticMarkup(
    React.createElement(MainWorkspace, {
      activeReferenceId: null,
      apiState: "ready",
      bootError: null,
      documents: [],
      draftQuestion: "",
      hotQuestions: [],
      isSubmitting: false,
      messages,
      onDraftQuestionChange: () => {},
      onReferenceClick: () => {},
      onSelectHotQuestion: () => {},
      onSubmit: () => {},
      onStop: () => {},
      onRegenerateAnswer: () => {},
    })
  );

  assert.doesNotMatch(html, /slenderness ratio definition/);
  assert.doesNotMatch(html, /expanded_queries/);
  assert.doesNotMatch(html, /检索规范知识库/);
});

test("MainWorkspace renders tool sub-steps as a nested agent chain timeline", () => {
  const messages: ChatTurn[] = [
    {
      id: "turn-tool",
      question: "长细比是如何定义的？",
      answer: "",
      reasoning: "",
      status: "streaming",
      confidence: "none",
      sources: [],
      relatedRefs: [],
      degraded: false,
      toolSubSteps: [
        {
          tool_name: "retrieve",
          step_id: "query_understanding",
          status: "completed",
          title: "理解问题",
          summary: "改写为：长细比定义；识别为 rule 问题。",
          metadata: {
            rewritten_question: "长细比定义",
            expanded_queries: ["slenderness ratio", "长细比"]
          },
          elapsed_ms: 18,
          parent_step_id: null
        },
        {
          tool_name: "retrieve",
          step_id: "hybrid_search",
          status: "completed",
          title: "混合检索",
          summary: "找到 3 个候选片段。",
          metadata: {
            chunk_count: 3,
            groundedness: "grounded"
          },
          elapsed_ms: 52,
          parent_step_id: null
        },
        {
          tool_name: "retrieve",
          step_id: "vector_search",
          status: "completed",
          title: "向量检索",
          summary: "得到 12 个候选",
          metadata: {
            candidate_count: 12
          },
          elapsed_ms: 30,
          parent_step_id: "hybrid_search"
        },
        {
          tool_name: "retrieve",
          step_id: "bm25_search",
          status: "completed",
          title: "BM25 检索",
          summary: "得到 8 个候选",
          metadata: {
            candidate_count: 8
          },
          elapsed_ms: 25,
          parent_step_id: "hybrid_search"
        }
      ]
    }
  ];

  const html = renderToStaticMarkup(
    React.createElement(MainWorkspace, {
      activeReferenceId: null,
      apiState: "ready",
      bootError: null,
      documents: [],
      draftQuestion: "",
      hotQuestions: [],
      isSubmitting: false,
      messages,
      onDraftQuestionChange: () => {},
      onReferenceClick: () => {},
      onSelectHotQuestion: () => {},
      onSubmit: () => {},
      onStop: () => {},
      onRegenerateAnswer: () => {},
    })
  );

  assert.match(html, /retrieve/);
  assert.match(html, /理解问题/);
  assert.match(html, /混合检索/);
  assert.match(html, /向量检索/);
  assert.match(html, /BM25 检索/);
  assert.match(html, /expanded_queries/);
  assert.match(html, /长细比/);
  assert.match(html, /找到 3 个候选片段/);
  assert.match(html, /并行/);
  assert.doesNotMatch(html, /query_rewrite/);
});

test.skip("MainWorkspace falls back to plain text when markdown rendering fails", () => {
  const originalCreateElement = React.createElement;
  const messages: ChatTurn[] = [
    {
      id: "turn-markdown-error",
      question: "公式生成中断怎么办？",
      answer: "不完整公式 $\\frac{",
      reasoning: "",
      status: "streaming",
      confidence: "none",
      sources: [],
      relatedRefs: [],
      degraded: false
    }
  ];

  React.createElement = ((type: unknown, ...args: unknown[]) => {
    if (type === ReactMarkdown) {
      throw new Error("markdown render failed");
    }
    return originalCreateElement(type as never, ...(args as never[]));
  }) as typeof React.createElement;

  try {
    const html = renderToStaticMarkup(
      React.createElement(MainWorkspace, {
        activeReferenceId: null,
        apiState: "ready",
        bootError: null,
        documents: [],
        draftQuestion: "",
        hotQuestions: [],
        isSubmitting: true,
        messages,
        onDraftQuestionChange: () => {},
        onReferenceClick: () => {},
        onSelectHotQuestion: () => {},
        onSubmit: () => {},
        onStop: () => {},
        onRegenerateAnswer: () => {},
      })
    );

    assert.match(html, /不完整公式/);
  } finally {
    React.createElement = originalCreateElement;
  }
});

test("MainWorkspace uses details elements for default-collapsed agent chain timeline", () => {
  const messages: ChatTurn[] = [
    {
      id: "turn-details",
      question: "长细比是如何定义的？",
      answer: "",
      reasoning: "",
      status: "streaming",
      confidence: "none",
      sources: [],
      relatedRefs: [],
      degraded: false,
      toolSubSteps: [
        {
          tool_name: "retrieve",
          step_id: "query_understanding",
          status: "running",
          title: "理解问题",
          summary: "识别检索意图。",
          metadata: {},
          elapsed_ms: 0,
          parent_step_id: null
        }
      ]
    }
  ];

  const html = renderToStaticMarkup(
    React.createElement(MainWorkspace, {
      activeReferenceId: null,
      apiState: "ready",
      bootError: null,
      documents: [],
      draftQuestion: "",
      hotQuestions: [],
      isSubmitting: true,
      messages,
      onDraftQuestionChange: () => {},
      onReferenceClick: () => {},
      onSelectHotQuestion: () => {},
      onSubmit: () => {},
      onStop: () => {},
      onRegenerateAnswer: () => {},
    })
  );

  assert.match(html, /<details class="/);
  assert.doesNotMatch(html, /<details open/);
});
