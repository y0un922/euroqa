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
      status: "streaming",
      confidence: "none",
      sources: [],
      relatedRefs: [],
      degraded: false,
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
});

test("MainWorkspace renders real tool payloads as collapsed tool calls", () => {
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
      progressEvents: [
        {
          stage: "tool:retrieve",
          status: "completed",
          title: "检索规范知识库",
          summary: "检索到 3 个片段。",
          facts: {
            tool_name: "retrieve",
            tool_args: {
              query: "slenderness ratio definition",
              top_k: 6
            },
            tool_result: "检索到 3 个片段，groundedness=grounded。",
            tool_trace: {
              tool: "retrieve",
              query: "slenderness ratio definition",
              expanded_queries: ["slenderness ratio", "长细比"],
              chunk_count: 3,
              groundedness: "grounded"
            }
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

  assert.match(html, /retrieve/);
  assert.match(html, /slenderness ratio definition/);
  assert.match(html, /expanded_queries/);
  assert.match(html, /长细比/);
  assert.match(html, /检索到 3 个片段/);
  assert.doesNotMatch(html, /query_rewrite/);
});

test("MainWorkspace falls back to plain text when markdown rendering fails", () => {
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

test("MainWorkspace uses details elements for default-collapsed real tool calls", () => {
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
      progressEvents: [
        {
          stage: "understanding",
          status: "running",
          title: "理解问题",
          summary: "识别检索意图。"
        },
        {
          stage: "tool:retrieve",
          status: "running",
          title: "检索规范知识库",
          summary: "正在搜索规范知识库...",
          facts: {
            tool_name: "retrieve",
            tool_args: { query: "长细比", top_k: 4 }
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
