import { MessageSquarePlus, BookMarked, Library, ChevronRight, Hash } from 'lucide-react';

export default function Sidebar() {
  const eurocodes = [
    { id: 'en1990', name: 'EN 1990', desc: '基础 Basis of Design' },
    { id: 'en1991', name: 'EN 1991', desc: '荷载 Actions on Structures' },
    { id: 'en1992', name: 'EN 1992', desc: '混凝土 Concrete Structures' },
    { id: 'en1993', name: 'EN 1993', desc: '钢结构 Steel Structures' },
    { id: 'en1997', name: 'EN 1997', desc: '岩土 Geotechnical Design' },
    { id: 'en1998', name: 'EN 1998', desc: '抗震 Earthquake Resistance' },
  ];

  return (
    <aside className="w-64 border-r border-stone-200 bg-stone-50/50 flex flex-col h-full shrink-0">
      <div className="p-4">
        <button className="w-full bg-stone-900 hover:bg-stone-800 text-white text-sm font-medium py-2 px-4 rounded-md flex items-center justify-center gap-2 transition-colors shadow-sm">
          <MessageSquarePlus className="w-4 h-4" />
          新建检索会话
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-3 py-2 space-y-6">
        {/* History */}
        <div>
          <h3 className="text-xs font-semibold text-stone-400 uppercase tracking-wider mb-2 px-2">最近检索</h3>
          <ul className="space-y-0.5">
            <li>
              <button className="w-full text-left px-2 py-1.5 text-sm text-stone-700 hover:bg-stone-200/50 rounded-md truncate bg-stone-200/50 font-medium">
                桥梁设计使用年限
              </button>
            </li>
            <li>
              <button className="w-full text-left px-2 py-1.5 text-sm text-stone-600 hover:bg-stone-200/50 rounded-md truncate">
                风荷载基本风速计算
              </button>
            </li>
            <li>
              <button className="w-full text-left px-2 py-1.5 text-sm text-stone-600 hover:bg-stone-200/50 rounded-md truncate">
                混凝土保护层厚度要求
              </button>
            </li>
          </ul>
        </div>

        {/* Eurocodes */}
        <div>
          <h3 className="text-xs font-semibold text-stone-400 uppercase tracking-wider mb-2 px-2">规范库结构</h3>
          <ul className="space-y-0.5">
            {eurocodes.map((code) => (
              <li key={code.id}>
                <button className="w-full flex items-center justify-between px-2 py-1.5 text-sm text-stone-600 hover:bg-stone-200/50 rounded-md group">
                  <div className="flex items-center gap-2 truncate">
                    <BookMarked className="w-3.5 h-3.5 text-stone-400 group-hover:text-cyan-600 transition-colors" />
                    <span className="truncate">{code.name} <span className="text-stone-400 text-xs ml-1">{code.desc}</span></span>
                  </div>
                  <ChevronRight className="w-3 h-3 text-stone-300 opacity-0 group-hover:opacity-100 transition-opacity" />
                </button>
              </li>
            ))}
          </ul>
        </div>

        {/* Tools */}
        <div>
          <h3 className="text-xs font-semibold text-stone-400 uppercase tracking-wider mb-2 px-2">知识工具</h3>
          <ul className="space-y-0.5">
            <li>
              <button className="w-full flex items-center gap-2 px-2 py-1.5 text-sm text-stone-600 hover:bg-stone-200/50 rounded-md">
                <Library className="w-3.5 h-3.5 text-stone-400" />
                中英术语表 (Glossary)
              </button>
            </li>
            <li>
              <button className="w-full flex items-center gap-2 px-2 py-1.5 text-sm text-stone-600 hover:bg-stone-200/50 rounded-md">
                <Hash className="w-3.5 h-3.5 text-stone-400" />
                国家附件 (National Annexes)
              </button>
            </li>
          </ul>
        </div>
      </div>
    </aside>
  );
}
