import { useEffect, useState } from "react";
import {
  Bot,
  BrainCircuit,
  KeyRound,
  RotateCcw,
  Save,
  Server
} from "lucide-react";

import type { LlmSettings } from "../lib/types";

type LlmSettingsPanelProps = {
  apiKeyConfigured: boolean;
  defaults: LlmSettings;
  localSettings: LlmSettings | null;
  onReset: () => void;
  onSave: (settings: LlmSettings) => void;
};

function buildDraft(
  defaults: LlmSettings,
  localSettings: LlmSettings | null
): LlmSettings {
  return localSettings ?? defaults;
}

export default function LlmSettingsPanel({
  apiKeyConfigured,
  defaults,
  localSettings,
  onReset,
  onSave
}: LlmSettingsPanelProps) {
  const [draft, setDraft] = useState<LlmSettings>(() => buildDraft(defaults, localSettings));

  useEffect(() => {
    setDraft(buildDraft(defaults, localSettings));
  }, [defaults, localSettings]);

  const isUsingLocalOverride = localSettings !== null;

  return (
    <div className="absolute right-0 top-12 z-30 w-[360px] rounded-2xl border border-stone-200 bg-white p-4 shadow-[0_24px_80px_rgba(28,25,23,0.12)]">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-sm font-semibold text-stone-900">LLM 设置</p>
          <p className="mt-1 text-xs leading-5 text-stone-500">
            {isUsingLocalOverride ? "当前使用本地覆盖配置" : "当前使用服务端默认配置"}
          </p>
        </div>
        <span
          className={`rounded-full px-2 py-1 text-[11px] font-medium ${
            isUsingLocalOverride
              ? "bg-cyan-50 text-cyan-700"
              : "bg-stone-100 text-stone-600"
          }`}
        >
          {isUsingLocalOverride ? "本地覆盖" : "默认"}
        </span>
      </div>

      <div className="mt-4 space-y-3">
        <label className="block">
          <span className="mb-1.5 flex items-center gap-1.5 text-xs font-medium text-stone-600">
            <KeyRound className="h-3.5 w-3.5" />
            API Key
          </span>
          <input
            type="password"
            value={draft.apiKey}
            onChange={(event) =>
              setDraft((current) => ({ ...current, apiKey: event.target.value }))
            }
            placeholder="留空则沿用服务端默认 Key"
            className="w-full rounded-xl border border-stone-200 bg-stone-50 px-3 py-2 text-sm text-stone-900 outline-none transition focus:border-cyan-300 focus:bg-white"
          />
          <span className="mt-1 block text-[11px] text-stone-500">
            服务端默认 Key：{apiKeyConfigured ? "已配置" : "未配置"}
          </span>
        </label>

        <label className="block">
          <span className="mb-1.5 flex items-center gap-1.5 text-xs font-medium text-stone-600">
            <Server className="h-3.5 w-3.5" />
            Base URL
          </span>
          <input
            type="text"
            value={draft.baseUrl}
            onChange={(event) =>
              setDraft((current) => ({ ...current, baseUrl: event.target.value }))
            }
            className="w-full rounded-xl border border-stone-200 bg-stone-50 px-3 py-2 text-sm text-stone-900 outline-none transition focus:border-cyan-300 focus:bg-white"
          />
          <span className="mt-1 block text-[11px] text-stone-500">
            默认值：{defaults.baseUrl}
          </span>
        </label>

        <label className="block">
          <span className="mb-1.5 flex items-center gap-1.5 text-xs font-medium text-stone-600">
            <Bot className="h-3.5 w-3.5" />
            Model
          </span>
          <input
            type="text"
            value={draft.model}
            onChange={(event) =>
              setDraft((current) => ({ ...current, model: event.target.value }))
            }
            className="w-full rounded-xl border border-stone-200 bg-stone-50 px-3 py-2 text-sm text-stone-900 outline-none transition focus:border-cyan-300 focus:bg-white"
          />
          <span className="mt-1 block text-[11px] text-stone-500">
            默认值：{defaults.model}
          </span>
        </label>

        <label className="flex items-center justify-between rounded-xl border border-stone-200 bg-stone-50 px-3 py-2.5">
          <span>
            <span className="flex items-center gap-1.5 text-xs font-medium text-stone-600">
              <BrainCircuit className="h-3.5 w-3.5" />
              Enable Thinking
            </span>
            <span className="mt-1 block text-[11px] text-stone-500">
              默认值：{defaults.enableThinking ? "开启" : "关闭"}
            </span>
          </span>
          <button
            type="button"
            onClick={() =>
              setDraft((current) => ({
                ...current,
                enableThinking: !current.enableThinking
              }))
            }
            className={`relative h-7 w-12 rounded-full transition ${
              draft.enableThinking ? "bg-cyan-600" : "bg-stone-300"
            }`}
          >
            <span
              className={`absolute top-1 h-5 w-5 rounded-full bg-white transition ${
                draft.enableThinking ? "left-6" : "left-1"
              }`}
            />
          </button>
        </label>
      </div>

      <div className="mt-4 flex items-center justify-between gap-3">
        <button
          type="button"
          onClick={onReset}
          className="inline-flex items-center gap-1.5 rounded-xl border border-stone-200 px-3 py-2 text-sm font-medium text-stone-600 transition hover:border-stone-300 hover:bg-stone-50"
        >
          <RotateCcw className="h-3.5 w-3.5" />
          恢复默认
        </button>
        <button
          type="button"
          onClick={() => {
            onSave(draft);
          }}
          className="inline-flex items-center gap-1.5 rounded-xl bg-cyan-700 px-3 py-2 text-sm font-medium text-white transition hover:bg-cyan-800"
        >
          <Save className="h-3.5 w-3.5" />
          保存设置
        </button>
      </div>
    </div>
  );
}
