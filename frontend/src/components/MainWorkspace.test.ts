import assert from "node:assert/strict";
import test from "node:test";

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import MainWorkspace from "./MainWorkspace.tsx";
import type { ChatTurn } from "../lib/types.ts";

test("MainWorkspace does not render follow-up suggestion chips in composer area", () => {
  const html = renderToStaticMarkup(
    React.createElement(MainWorkspace, {
      activeReferenceId: null,
      apiState: "ready",
      bootError: null,
      documents: [],
      draftQuestion: "",
      hotQuestions: [
        "结构分析的目的是什么?",
        "什么是单向板?",
        "长细比是如何定义的?"
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
