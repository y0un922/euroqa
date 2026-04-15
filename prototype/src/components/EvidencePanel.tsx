import { FileText, ExternalLink, ShieldCheck, Target, Layers, BookOpen } from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';

interface EvidencePanelProps {
  activeReference: string | null;
}

export default function EvidencePanel({ activeReference }: EvidencePanelProps) {
  
  const refData: Record<string, any> = {
    'ref-1': {
      doc: 'EN 1990:2002',
      title: 'Eurocode - Basis of structural design',
      section: 'Section 2 Requirements',
      clause: 'Table 2.1',
      page: '23',
      confidence: 0.98,
      english: 'Table 2.1 — Indicative design working life\n\nDesign working life category: 5\nIndicative design working life (years): 100\nExamples: Monumental building structures, bridges, and other civil engineering structures.',
      chinese: '表 2.1 — 指示性设计使用年限\n\n设计使用年限类别：5\n指示性设计使用年限（年）：100\n示例：纪念性建筑结构、桥梁及其他土木工程结构。',
      related: ['EN 1991-2: Traffic loads on bridges', 'ISO 2394: General principles on reliability for structures']
    },
    'ref-2': {
      doc: 'EN 1990:2002',
      title: 'Eurocode - Basis of structural design',
      section: 'Section 2 Requirements',
      clause: 'Clause 2.3(1)',
      page: '22',
      confidence: 0.95,
      english: '(1) The design working life is the assumed period for which a structure or part of it is to be used for its intended purpose with anticipated maintenance but without major repair being necessary.',
      chinese: '(1) 设计使用年限是指结构或其部分在预期维护下，能够按预期目的使用而无需进行重大修复的假定时间段。',
      related: ['Clause 2.4 Durability']
    }
  };

  const data = activeReference ? refData[activeReference] : null;

  return (
    <aside className="w-[380px] border-l border-stone-200 bg-stone-50 flex flex-col h-full shrink-0 shadow-[-4px_0_24px_-12px_rgba(0,0,0,0.05)] z-20">
      <div className="h-14 border-b border-stone-200 flex items-center px-5 bg-white shrink-0">
        <h2 className="text-sm font-semibold text-stone-800 flex items-center gap-2">
          <ShieldCheck className="w-4 h-4 text-cyan-700" />
          证据与溯源 (Evidence)
        </h2>
      </div>

      <div className="flex-1 overflow-y-auto">
        <AnimatePresence mode="wait">
          {data ? (
            <motion.div 
              key={activeReference}
              initial={{ opacity: 0, x: 10 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -10 }}
              transition={{ duration: 0.2 }}
              className="p-5 space-y-6"
            >
              {/* Meta Info */}
              <div className="space-y-3">
                <div className="flex items-start justify-between">
                  <div>
                    <div className="inline-flex items-center gap-1.5 px-2 py-1 rounded bg-stone-200/50 text-stone-700 text-xs font-mono font-medium mb-2">
                      <FileText className="w-3 h-3" />
                      {data.doc}
                    </div>
                    <h3 className="text-sm font-medium text-stone-900 leading-snug">{data.title}</h3>
                  </div>
                  <div className="flex flex-col items-end">
                    <div className="flex items-center gap-1 text-emerald-600 bg-emerald-50 px-2 py-1 rounded text-xs font-medium border border-emerald-100">
                      <Target className="w-3 h-3" />
                      {(data.confidence * 100).toFixed(0)}% 匹配
                    </div>
                  </div>
                </div>

                <div className="bg-white border border-stone-200 rounded-lg p-3 text-xs space-y-2 shadow-sm">
                  <div className="flex items-center justify-between">
                    <span className="text-stone-500">Section Path</span>
                    <span className="text-stone-800 font-medium text-right">{data.section}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-stone-500">Clause / Table</span>
                    <span className="text-stone-800 font-mono font-medium">{data.clause}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-stone-500">Page</span>
                    <span className="text-stone-800 font-mono font-medium">p. {data.page}</span>
                  </div>
                </div>
              </div>

              {/* Content Comparison */}
              <div className="space-y-4">
                <div>
                  <h4 className="text-xs font-semibold text-stone-400 uppercase tracking-wider mb-2 flex items-center gap-1.5">
                    <span className="w-1.5 h-1.5 rounded-full bg-stone-300"></span>
                    原文 (Original Text)
                  </h4>
                  <div className="bg-stone-900 text-stone-300 p-4 rounded-lg text-[13px] font-mono leading-relaxed whitespace-pre-wrap shadow-inner">
                    {data.english}
                  </div>
                </div>

                <div>
                  <h4 className="text-xs font-semibold text-stone-400 uppercase tracking-wider mb-2 flex items-center gap-1.5">
                    <span className="w-1.5 h-1.5 rounded-full bg-cyan-600"></span>
                    中文解析 (Interpretation)
                  </h4>
                  <div className="bg-white border border-stone-200 p-4 rounded-lg text-[13px] text-stone-800 leading-relaxed whitespace-pre-wrap shadow-sm">
                    {data.chinese}
                  </div>
                </div>
              </div>

              {/* Related Refs */}
              <div>
                <h4 className="text-xs font-semibold text-stone-400 uppercase tracking-wider mb-2 flex items-center gap-1.5">
                  <Layers className="w-3.5 h-3.5" />
                  关联条款 (Related Refs)
                </h4>
                <ul className="space-y-1.5">
                  {data.related.map((ref: string, idx: number) => (
                    <li key={idx}>
                      <button className="w-full text-left flex items-center justify-between px-3 py-2 bg-white border border-stone-200 hover:border-cyan-300 hover:bg-cyan-50 rounded-md text-xs text-stone-600 transition-colors group">
                        <span className="truncate pr-2">{ref}</span>
                        <ExternalLink className="w-3 h-3 text-stone-400 group-hover:text-cyan-600 shrink-0" />
                      </button>
                    </li>
                  ))}
                </ul>
              </div>

              {/* Document Preview Thumbnail */}
              <div className="pt-4 border-t border-stone-200">
                <button className="w-full group relative overflow-hidden rounded-lg border border-stone-200 bg-white p-2 flex items-center gap-3 hover:border-cyan-300 transition-colors shadow-sm">
                  <div className="w-12 h-16 bg-stone-100 border border-stone-200 rounded flex items-center justify-center shrink-0 relative overflow-hidden">
                    {/* Fake PDF lines */}
                    <div className="absolute inset-2 flex flex-col gap-1 opacity-30">
                      <div className="h-0.5 w-full bg-stone-400"></div>
                      <div className="h-0.5 w-3/4 bg-stone-400"></div>
                      <div className="h-0.5 w-full bg-stone-400 mt-1"></div>
                      <div className="h-0.5 w-5/6 bg-stone-400"></div>
                      <div className="h-2 w-full bg-cyan-400/50 mt-1"></div> {/* Highlight */}
                      <div className="h-0.5 w-full bg-stone-400 mt-1"></div>
                    </div>
                  </div>
                  <div className="flex-1 text-left">
                    <div className="text-xs font-medium text-stone-800 mb-0.5">查看原文档</div>
                    <div className="text-[10px] text-stone-500 font-mono">EN1990_2002.pdf</div>
                  </div>
                  <div className="w-6 h-6 rounded-full bg-stone-100 flex items-center justify-center group-hover:bg-cyan-100 transition-colors">
                    <BookOpen className="w-3 h-3 text-stone-600 group-hover:text-cyan-700" />
                  </div>
                </button>
              </div>

            </motion.div>
          ) : (
            <div className="h-full flex flex-col items-center justify-center text-stone-400 p-8 text-center">
              <ShieldCheck className="w-12 h-12 mb-4 opacity-20" />
              <p className="text-sm">点击左侧回答中的引用标签<br/>查看详细证据与溯源</p>
            </div>
          )}
        </AnimatePresence>
      </div>
    </aside>
  );
}
