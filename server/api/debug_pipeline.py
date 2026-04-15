"""Debug-only pipeline run viewer and APIs."""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse
from sse_starlette.sse import EventSourceResponse

from server.deps import get_config
from shared.pipeline_debug import PipelineDebugStore

router = APIRouter()


def _get_store(config) -> PipelineDebugStore:
    return PipelineDebugStore(config.debug_pipeline_dir)


@router.get("/debug/pipeline", response_class=HTMLResponse)
async def debug_pipeline_page() -> str:
    """Serve the pipeline debug page."""
    return """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>Pipeline Debug</title>
  <style>
    body { margin: 0; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; background: #0b1020; color: #e5e7eb; }
    .layout { display: grid; grid-template-columns: 280px 1fr; min-height: 100vh; }
    .sidebar { border-right: 1px solid #1f2937; padding: 16px; background: #111827; }
    .content { padding: 16px; display: grid; gap: 16px; }
    .panel { border: 1px solid #1f2937; border-radius: 12px; background: #111827; padding: 16px; }
    .run-btn, .artifact-btn { width: 100%; text-align: left; background: #0f172a; color: #e5e7eb; border: 1px solid #334155; padding: 10px 12px; border-radius: 10px; cursor: pointer; margin-bottom: 8px; }
    .run-btn.active, .artifact-btn.active { border-color: #22c55e; background: #052e16; }
    .grid { display: grid; gap: 12px; }
    .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; }
    .card { background: #0f172a; border: 1px solid #334155; border-radius: 10px; padding: 12px; }
    .table { width: 100%; border-collapse: collapse; }
    .table th, .table td { border-bottom: 1px solid #1f2937; padding: 8px; text-align: left; vertical-align: top; }
    pre { white-space: pre-wrap; word-break: break-word; background: #020617; border: 1px solid #1f2937; border-radius: 10px; padding: 12px; min-height: 180px; overflow: auto; }
    .muted { color: #94a3b8; }
    .row { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
    .status-running { color: #f59e0b; }
    .status-completed { color: #22c55e; }
    .status-failed { color: #ef4444; }
  </style>
</head>
<body>
  <div class="layout">
    <aside class="sidebar">
      <h2>Pipeline Debug</h2>
      <p class="muted">历史运行记录与实时阶段快照</p>
      <div id="runs"></div>
    </aside>
    <main class="content">
      <section class="panel">
        <div id="summary" class="cards"></div>
      </section>
      <section class="panel">
        <h3>Stages</h3>
        <table class="table" id="stages"></table>
      </section>
      <section class="row">
        <section class="panel">
          <h3>Documents</h3>
          <div id="documents"></div>
        </section>
        <section class="panel">
          <h3>Artifacts</h3>
          <div id="artifacts"></div>
        </section>
      </section>
      <section class="panel">
        <h3>Artifact Content</h3>
        <pre id="artifact-content">选择一个 artifact 查看内容</pre>
      </section>
    </main>
  </div>
  <script>
    const state = { runs: [], currentRun: null, currentDoc: null, currentArtifact: null, stream: null };

    async function fetchJson(url) {
      const resp = await fetch(url);
      if (!resp.ok) throw new Error(await resp.text());
      return await resp.json();
    }

    function statusClass(status) {
      return `status-${status || 'unknown'}`;
    }

    async function loadRuns() {
      state.runs = await fetchJson('/api/debug/pipeline/runs');
      renderRuns();
      if (!state.currentRun && state.runs.length) {
        await selectRun(state.runs[0].run_id);
      }
    }

    function renderRuns() {
      const container = document.getElementById('runs');
      if (!state.runs.length) {
        container.innerHTML = '<p class="muted">暂无运行记录</p>';
        return;
      }
      container.innerHTML = state.runs.map(run => `
        <button class="run-btn ${state.currentRun && state.currentRun.run_id === run.run_id ? 'active' : ''}" onclick="selectRun('${run.run_id}')">
          <div><strong>${run.run_id}</strong></div>
          <div class="${statusClass(run.status)}">${run.status}</div>
          <div class="muted">${run.started_at || ''}</div>
        </button>
      `).join('');
    }

    async function selectRun(runId) {
      if (state.stream) {
        state.stream.close();
        state.stream = null;
      }
      state.currentRun = await fetchJson(`/api/debug/pipeline/runs/${runId}`);
      const docIds = Object.keys(state.currentRun.documents || {});
      state.currentDoc = docIds.includes(state.currentDoc) ? state.currentDoc : docIds[0] || null;
      state.currentArtifact = null;
      renderRuns();
      renderRun();
      attachStreamIfNeeded();
    }

    function renderRun() {
      const run = state.currentRun;
      if (!run) return;
      document.getElementById('summary').innerHTML = [
        ['Run ID', run.run_id],
        ['Status', run.status],
        ['Current Stage', run.current_stage || '-'],
        ['Updated', run.updated_at || '-'],
      ].map(([label, value]) => `<div class="card"><div class="muted">${label}</div><div>${value}</div></div>`).join('');

      const stageRows = Object.entries(run.stages || {}).map(([stage, info]) => `
        <tr>
          <td>${stage}</td>
          <td class="${statusClass(info.status)}">${info.status || '-'}</td>
          <td><pre>${JSON.stringify(info.summary || {}, null, 2)}</pre></td>
        </tr>
      `).join('');
      document.getElementById('stages').innerHTML = `
        <tr><th>Stage</th><th>Status</th><th>Summary</th></tr>
        ${stageRows || '<tr><td colspan="3" class="muted">暂无阶段信息</td></tr>'}
      `;

      const documents = run.documents || {};
      const docIds = Object.keys(documents);
      document.getElementById('documents').innerHTML = docIds.map(docId => `
        <button class="run-btn ${state.currentDoc === docId ? 'active' : ''}" onclick="selectDocument('${docId}')">
          <div><strong>${docId}</strong></div>
          <div class="muted">${documents[docId].title || ''}</div>
        </button>
      `).join('') || '<p class="muted">暂无文档</p>';

      renderArtifacts();
    }

    function selectDocument(docId) {
      state.currentDoc = docId;
      state.currentArtifact = null;
      renderRun();
    }

    function renderArtifacts() {
      const container = document.getElementById('artifacts');
      const run = state.currentRun;
      if (!run || !state.currentDoc || !run.documents[state.currentDoc]) {
        container.innerHTML = '<p class="muted">暂无 artifact</p>';
        return;
      }
      const stageEntries = Object.entries(run.documents[state.currentDoc].stages || {});
      const buttons = [];
      for (const [stage, info] of stageEntries) {
        for (const artifact of (info.artifacts || [])) {
          buttons.push(`
            <button class="artifact-btn ${state.currentArtifact === artifact.path ? 'active' : ''}" onclick="loadArtifact('${artifact.path}', '${artifact.content_type || 'text/plain'}')">
              <div><strong>${stage}</strong> · ${artifact.label}</div>
              <div class="muted">${artifact.path}</div>
            </button>
          `);
        }
      }
      container.innerHTML = buttons.join('') || '<p class="muted">该文档暂无 artifact</p>';
    }

    async function loadArtifact(path, contentType) {
      state.currentArtifact = path;
      renderArtifacts();
      const resp = await fetch(`/api/debug/pipeline/runs/${state.currentRun.run_id}/artifacts/${path}`);
      if (!resp.ok) {
        document.getElementById('artifact-content').textContent = await resp.text();
        return;
      }
      if (contentType === 'application/json') {
        const data = await resp.json();
        document.getElementById('artifact-content').textContent = JSON.stringify(data, null, 2);
      } else {
        document.getElementById('artifact-content').textContent = await resp.text();
      }
    }

    function attachStreamIfNeeded() {
      if (!state.currentRun || state.currentRun.status !== 'running') return;
      state.stream = new EventSource(`/api/debug/pipeline/runs/${state.currentRun.run_id}/stream`);
      state.stream.addEventListener('state', (event) => {
        state.currentRun = JSON.parse(event.data);
        renderRuns();
        renderRun();
      });
      state.stream.addEventListener('done', async () => {
        if (state.stream) state.stream.close();
        state.stream = null;
        await selectRun(state.currentRun.run_id);
      });
    }

    loadRuns().catch(err => {
      document.getElementById('artifact-content').textContent = String(err);
    });
  </script>
</body>
</html>"""


@router.get("/api/debug/pipeline/runs")
async def list_pipeline_runs(config=Depends(get_config)) -> list[dict]:
    """List all persisted pipeline debug runs."""
    return _get_store(config).list_runs()


@router.get("/api/debug/pipeline/runs/{run_id}")
async def get_pipeline_run(run_id: str, config=Depends(get_config)) -> dict:
    """Return a specific run manifest."""
    try:
        return _get_store(config).get_run(run_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found") from exc


@router.get("/api/debug/pipeline/runs/{run_id}/artifacts/{artifact_path:path}")
async def get_pipeline_artifact(run_id: str, artifact_path: str, config=Depends(get_config)):
    """Return a persisted artifact from a pipeline run."""
    store = _get_store(config)
    try:
        if artifact_path.endswith(".json"):
            return store.read_json_artifact(run_id, artifact_path)
        return PlainTextResponse(store.read_text_artifact(run_id, artifact_path))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Artifact {artifact_path} not found") from exc


@router.get("/api/debug/pipeline/runs/{run_id}/stream")
async def stream_pipeline_run(run_id: str, config=Depends(get_config)) -> EventSourceResponse:
    """Stream manifest changes for a running pipeline via SSE."""
    store = _get_store(config)

    async def event_generator():
        last_updated = None
        while True:
            try:
                run = store.get_run(run_id)
            except FileNotFoundError:
                yield {"event": "error", "data": json.dumps({"detail": f"Run {run_id} not found"}, ensure_ascii=False)}
                return

            if run.get("updated_at") != last_updated:
                last_updated = run.get("updated_at")
                yield {"event": "state", "data": json.dumps(run, ensure_ascii=False)}

            if run.get("status") in {"completed", "failed"}:
                yield {"event": "done", "data": json.dumps({"status": run["status"]}, ensure_ascii=False)}
                return

            await asyncio.sleep(1.0)

    return EventSourceResponse(event_generator())
