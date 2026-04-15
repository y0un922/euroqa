import React, { useState } from 'react';
import Sidebar from './components/Sidebar';
import MainWorkspace from './components/MainWorkspace';
import EvidencePanel from './components/EvidencePanel';
import TopBar from './components/TopBar';

export default function App() {
  const [activeReference, setActiveReference] = useState<string | null>('ref-1');

  return (
    <div className="flex flex-col h-screen bg-stone-50 text-stone-900 font-sans overflow-hidden selection:bg-cyan-100 selection:text-cyan-900">
      <TopBar />
      <div className="flex flex-1 overflow-hidden">
        <Sidebar />
        <MainWorkspace activeReference={activeReference} onReferenceClick={setActiveReference} />
        <EvidencePanel activeReference={activeReference} />
      </div>
    </div>
  );
}
