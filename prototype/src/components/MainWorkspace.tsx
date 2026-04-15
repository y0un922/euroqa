import { Search, Sparkles, CornerDownLeft, FileText, CheckCircle2, BookMarked } from 'lucide-react';
import { motion } from 'motion/react';

interface MainWorkspaceProps {
  activeReference: string | null;
  onReferenceClick: (id: string) => void;
}

export default function MainWorkspace({ activeReference, onReferenceClick }: MainWorkspaceProps) {
  return (
    <main className="flex-1 flex flex-col bg-white h-full relative">
      {/* Background texture - subtle grid */}
      <div className="absolute inset-0 pointer-events-none opacity-[0.02]" style={{ backgroundImage: 'linear-gradient(#000 1px, transparent 1px), linear-gradient(90deg, #000 1px, transparent 1px)', backgroundSize: '20px 20px' }}></div>

      {/* Chat Area */}
      <div className="flex-1 overflow-y-auto px-8 py-10 scroll-smooth">
        <div className="max-w-3xl mx-auto space-y-10">
          
          {/* User Question */}
          <motion.div 
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="flex flex-col items-end"
          >
            <div className="bg-stone-100 text-stone-900 px-5 py-4 rounded-2xl rounded-tr-sm max-w-[85%] shadow-sm border border-stone-200/50">
              <p className="text-[15px] leading-relaxed">EN 1990 中桥梁的设计使用年限通常如何理解？</p>
            </div>
          </motion.div>

          {/* AI Response */}
          <motion.div 
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
            className="flex flex-col items-start"
          >
            <div className="flex items-center gap-2 mb-3 text-sm font-medium text-cyan-800">
              <Sparkles className="w-4 h-4" />
              <span>Euro_QA 智能综合解答</span>
              <span className="text-stone-400 font-normal text-xs ml-2">基于 3 份文档综合生成</span>
            </div>
            
            <div className="text-stone-800 text-[15px] leading-relaxed space-y-6 w-full max-w-[95%]">
              
              {/* Conclusion */}
              <div className="bg-cyan-50/50 border border-cyan-100 p-4 rounded-lg">
                <div className="flex items-start gap-2">
                  <CheckCircle2 className="w-5 h-5 text-cyan-600 mt-0.5 shrink-0" />
                  <div>
                    <h4 className="font-semibold text-cyan-900 mb-1">核心结论</h4>
                    <p className="text-cyan-800/90">在 EN 1990 中，桥梁及其他土木工程结构的设计使用年限（Design Working Life）通常被归类为 <strong>Category 5</strong>，其指示性设计使用年限为 <strong>100年</strong>。</p>
                  </div>
                </div>
              </div>

              {/* Explanation */}
              <div className="space-y-4">
                <p>
                  根据 <button onClick={() => onReferenceClick('ref-1')} className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs font-mono transition-colors ${activeReference === 'ref-1' ? 'bg-cyan-100 text-cyan-800 border border-cyan-200' : 'bg-stone-100 text-stone-600 border border-stone-200 hover:bg-stone-200'}`}>[1] EN 1990:2002 Clause 2.3</button> 的规定，设计使用年限是指结构在预期维护下，能够按预期目的使用而无需进行重大修复的假定时间段。
                </p>
                <p>
                  规范将结构的设计使用年限分为 1 至 5 类（Table 2.1）：
                </p>
                <ul className="list-disc pl-5 space-y-2 text-stone-700">
                  <li><strong>Category 1-3:</strong> 适用于临时结构、可更换结构部件以及农业建筑等（1至25年）。</li>
                  <li><strong>Category 4:</strong> 适用于普通建筑结构和其他常见结构（50年）。</li>
                  <li><strong>Category 5:</strong> 明确适用于<strong>纪念性建筑、桥梁及其他土木工程结构</strong>（Monumental building structures, bridges, and other civil engineering structures），规定为 <strong>100年</strong>。</li>
                </ul>
                <p>
                  <strong>工程应用说明：</strong><br/>
                  在实际工程中，100年是一个指示性数值（indicative value）。具体项目的设计使用年限可能会根据国家附件（National Annex）或客户的具体要求（Client's requirements）进行调整。例如，某些跨海大桥或特大桥梁，其设计使用年限可能会被要求提高至 120 年。
                </p>
              </div>

              {/* Citations */}
              <div className="pt-4 border-t border-stone-100">
                <h4 className="text-xs font-semibold text-stone-400 uppercase tracking-wider mb-3">引用来源</h4>
                <div className="flex flex-wrap gap-2">
                  <button 
                    onClick={() => onReferenceClick('ref-1')}
                    className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-sm transition-all ${activeReference === 'ref-1' ? 'bg-stone-900 text-white shadow-md' : 'bg-stone-50 text-stone-600 border border-stone-200 hover:border-stone-300 hover:bg-stone-100'}`}
                  >
                    <FileText className="w-3.5 h-3.5" />
                    <span className="font-mono text-xs">EN 1990 Table 2.1</span>
                  </button>
                  <button 
                    onClick={() => onReferenceClick('ref-2')}
                    className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-sm transition-all ${activeReference === 'ref-2' ? 'bg-stone-900 text-white shadow-md' : 'bg-stone-50 text-stone-600 border border-stone-200 hover:border-stone-300 hover:bg-stone-100'}`}
                  >
                    <FileText className="w-3.5 h-3.5" />
                    <span className="font-mono text-xs">EN 1990 Clause 2.3(1)</span>
                  </button>
                </div>
              </div>

            </div>
          </motion.div>

        </div>
      </div>

      {/* Input Area */}
      <div className="p-6 bg-white border-t border-stone-100 z-10">
        <div className="max-w-3xl mx-auto">
          {/* Suggestions */}
          <div className="flex items-center gap-2 mb-3 overflow-x-auto pb-1 scrollbar-hide">
            <span className="text-xs font-medium text-stone-400 uppercase tracking-wider shrink-0 mr-2">推荐追问:</span>
            <button className="shrink-0 px-3 py-1.5 bg-stone-50 border border-stone-200 rounded-full text-xs text-stone-600 hover:bg-stone-100 transition-colors">
              设计使用年限如何影响可靠度指标 (β)？
            </button>
            <button className="shrink-0 px-3 py-1.5 bg-stone-50 border border-stone-200 rounded-full text-xs text-stone-600 hover:bg-stone-100 transition-colors">
              EN 1991 中桥梁交通荷载的基准期是多少？
            </button>
          </div>

          {/* Input Box */}
          <div className="relative group">
            <div className="absolute inset-0 bg-gradient-to-r from-cyan-500/20 to-blue-500/20 rounded-xl blur-md opacity-0 group-focus-within:opacity-100 transition-opacity duration-500"></div>
            <div className="relative bg-white border border-stone-300 rounded-xl shadow-sm focus-within:border-cyan-500 focus-within:ring-1 focus-within:ring-cyan-500 transition-all flex flex-col">
              <textarea 
                placeholder="输入规范相关问题，例如：EN 1992 中关于裂缝控制的原则是什么？"
                className="w-full bg-transparent px-4 py-3 text-[15px] text-stone-800 placeholder:text-stone-400 resize-none focus:outline-none min-h-[80px]"
                defaultValue=""
              />
              <div className="flex items-center justify-between px-3 py-2 border-t border-stone-100 bg-stone-50/50 rounded-b-xl">
                <div className="flex items-center gap-3">
                  <button className="text-xs flex items-center gap-1 text-stone-500 hover:text-stone-800 transition-colors">
                    <Search className="w-3.5 h-3.5" />
                    <span>混合检索 (Hybrid)</span>
                  </button>
                  <div className="w-px h-3 bg-stone-300"></div>
                  <button className="text-xs flex items-center gap-1 text-stone-500 hover:text-stone-800 transition-colors">
                    <BookMarked className="w-3.5 h-3.5" />
                    <span>全部规范</span>
                  </button>
                </div>
                <button className="bg-stone-900 hover:bg-stone-800 text-white p-1.5 rounded-lg transition-colors flex items-center justify-center">
                  <CornerDownLeft className="w-4 h-4" />
                </button>
              </div>
            </div>
          </div>
          <div className="text-center mt-3">
            <span className="text-[10px] text-stone-400">AI 生成内容可能存在误差，请结合原规范进行工程判断。</span>
          </div>
        </div>
      </div>
    </main>
  );
}
