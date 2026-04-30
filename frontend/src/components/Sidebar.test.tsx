import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import Sidebar from "./Sidebar";

test("Sidebar renders history sessions and omits glossary preview", () => {
  Object.assign(globalThis, { React });
  const html = renderToStaticMarkup(
    React.createElement(Sidebar, {
      documents: [
        {
          id: "doc-1",
          name: "EN 1992-1-1.pdf",
          title: "EN 1992-1-1",
          total_pages: 580,
          chunk_count: 200,
          status: "ready"
        }
      ],
      glossary: [
        {
          zh: ["徐变"],
          en: "creep",
          verified: true
        }
      ],
      historySessions: [
        {
          id: "history-1",
          title: "保护层都与什么因素相关，该怎么计算?",
          messageCount: 3,
          lastUpdatedLabel: "刚刚"
        }
      ],
      hotQuestions: [
        "请给出混凝土结构设计中相关作用荷载和材料的分项系数。",
        "请给出混凝土材料的强度与变形的相关定义、相互关系及如何计算。",
        "有哪些因素会对混凝土的徐变与收缩产生影响?",
        "钢筋的主要特性有哪些?并给出相应总结。",
        "请问都有那些环境暴露等级?",
        "保护层都与什么因素相关，该怎么计算?",
        "欧标的截面计算的基本假设前提是什么？",
        "混凝土受压区应变-应力分布假设是什么？",
        "混凝土压碎应变限值是多少？",
        "极限受力状态下混凝土受压区高度限值为多少？",
        "受弯构件正截面承载力计算的一般步骤是什么？"
      ],
      activeSessionId: "current",
      onNewSession: () => {},
      onSelectHistorySession: () => {},
      onSelectHotQuestion: () => {}
    })
  );

  assert.match(html, /历史会话/);
  assert.match(html, /保护层都与什么因素相关，该怎么计算\?/);
  assert.match(html, /请给出混凝土结构设计中相关作用荷载和材料的分项系数。/);
  assert.match(html, /极限受力状态下混凝土受压区高度限值为多少？/);
  assert.doesNotMatch(html, /受弯构件正截面承载力计算的一般步骤是什么？/);
  assert.doesNotMatch(html, /术语预览/);
  assert.doesNotMatch(html, /creep/);
});
