import { Settings, BookOpen, Activity, LayoutGrid } from 'lucide-react';

export default function TopBar() {
  return (
    <header className="h-14 border-b border-stone-200 bg-white flex items-center justify-between px-6 shrink-0 z-10">
      <div className="flex items-center gap-4">
        <div className="font-serif font-semibold text-xl tracking-tight text-stone-800 flex items-center gap-2">
          <div className="w-5 h-5 bg-cyan-800 rounded-sm"></div>
          Euro_QA
        </div>
        <div className="h-4 w-px bg-stone-300 mx-2"></div>
        <div className="flex items-center gap-2 text-xs font-medium text-stone-500 bg-stone-100 px-2 py-1 rounded-md">
          <Activity className="w-3 h-3 text-cyan-600" />
          <span>索引状态: 已同步 (24,051 条款)</span>
        </div>
      </div>
      <div className="flex items-center gap-5 text-sm text-stone-600">
        <button className="flex items-center gap-1.5 hover:text-stone-900 transition-colors">
          <LayoutGrid className="w-4 h-4" />
          <span>演示模式</span>
        </button>
        <button className="flex items-center gap-1.5 hover:text-stone-900 transition-colors">
          <BookOpen className="w-4 h-4" />
          <span>规范库</span>
        </button>
        <button className="flex items-center gap-1.5 hover:text-stone-900 transition-colors">
          <Settings className="w-4 h-4" />
          <span>设置</span>
        </button>
      </div>
    </header>
  );
}
