import React from 'react';
import { 
  Zap, 
  ShieldCheck, 
  Layers, 
  Cpu, 
  Activity, 
  Server, 
  MessageSquare, 
  Coins, 
  Users, 
  Calendar,
  Lock,
  ArrowRightLeft
} from 'lucide-react';

interface HeaderProps {
  activeTab: string;
  setActiveTab: (tab: string) => void;
  stats: {
    totalWebhooks: number;
    tokensSaved: number;
    nairaSaved: number;
    activeHolds: number;
  };
}

export const Header: React.FC<HeaderProps> = ({ activeTab, setActiveTab, stats }) => {
  const tabs = [
    { id: 'simulator', label: 'WhatsApp Simulator', icon: MessageSquare, badge: 'Live Phone' },
    { id: 'webhooks', label: 'Meta Webhooks', icon: Server, badge: '200 OK' },
    { id: 'nlu', label: 'Pidgin NLU Matrix', icon: Cpu, badge: 'Fast-Path' },
    { id: 'anti-ghosting', label: 'Anti-Ghosting Ledger', icon: ArrowRightLeft, badge: '10m Hold' },
    { id: 'reservations', label: 'Atomic Slots', icon: Calendar, badge: 'GiST Lock' },
    { id: 'handoff', label: 'Agent Handoff', icon: Users, badge: 'No-Repeat' },
    { id: 'pii-ndpa', label: 'PII & NDPA Vault', icon: Lock, badge: 'BVN Redacted' },
  ];

  return (
    <header className="border-b border-white/5 bg-[#0e0e10] sticky top-0 z-40 backdrop-blur-md">
      {/* Top Banner / Executive Indicators */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 py-2 flex flex-wrap items-center justify-between gap-3 border-b border-white/5 text-xs">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></div>
            <span className="text-[10px] text-gray-400 uppercase tracking-widest">Meta Webhook Queue</span>
            <span className="text-emerald-400 font-mono text-[11px]">18ms (Decoupled 200 OK)</span>
          </div>
          <div className="h-4 w-px bg-white/10 hidden sm:block"></div>
          <div className="hidden sm:flex items-center gap-1.5 text-gray-400 text-xs">
            <Zap className="w-3.5 h-3.5 text-amber-400" />
            <span className="text-[10px] text-gray-500 uppercase tracking-widest">Worker Pool:</span>
            <strong className="text-gray-200 font-mono text-[11px]">Redis Async NG-01</strong>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5 bg-white/5 border border-white/10 px-2.5 py-0.5 rounded-full text-emerald-400 text-xs">
            <Coins className="w-3.5 h-3.5 text-emerald-500" />
            <span className="text-[10px] text-gray-400 uppercase tracking-widest">Token Cap Saved:</span>
            <span className="font-semibold text-emerald-400">₦{stats.nairaSaved.toLocaleString()}</span>
          </div>
          <div className="hidden md:flex items-center gap-1.5 bg-blue-500/10 border border-blue-500/20 px-2.5 py-0.5 rounded-full text-blue-400 text-[11px]">
            <ShieldCheck className="w-3.5 h-3.5 text-blue-400" />
            <span className="text-[10px] uppercase tracking-widest font-mono">NDPA 2023 Shield OK</span>
          </div>
        </div>
      </div>

      {/* Main Title & Nav Tabs */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 py-3.5">
        <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
          <div className="flex items-center gap-3.5">
            <div className="w-10 h-10 bg-emerald-500 rounded-xl flex items-center justify-center text-black font-extrabold text-base shadow-sm shadow-emerald-500/30">
              KF
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-base font-semibold text-white tracking-tight">
                  KudiFlow Enterprise
                </h1>
                <span className="px-2 py-0.5 rounded border border-emerald-500/30 text-[10px] text-emerald-400 uppercase tracking-widest font-mono bg-emerald-500/10">
                  Tier 1 Nigerian SME
                </span>
              </div>
              <p className="text-[11px] text-gray-500 mt-0.5 font-normal">
                Conversational Workflow Manager &bull; Regional Node: Lagos-M1 &bull; Pidgin NLU &bull; Anti-Ghosting Webhooks
              </p>
            </div>
          </div>

          {/* Tab Navigation */}
          <nav className="flex items-center gap-1.5 overflow-x-auto pb-1 lg:pb-0 scrollbar-none">
            {tabs.map((tab) => {
              const Icon = tab.icon;
              const isActive = activeTab === tab.id;
              return (
                <button
                  key={tab.id}
                  id={`tab-nav-${tab.id}`}
                  onClick={() => setActiveTab(tab.id)}
                  className={`flex items-center gap-2 px-3 py-2 rounded-xl text-xs whitespace-nowrap transition-all duration-150 ${
                    isActive
                      ? 'bg-emerald-500 text-black font-bold shadow-sm shadow-emerald-500/20'
                      : 'text-gray-400 hover:text-gray-200 hover:bg-white/5 border border-transparent hover:border-white/5'
                  }`}
                >
                  <Icon className={`w-3.5 h-3.5 ${isActive ? 'text-black' : 'text-gray-400'}`} />
                  <span>{tab.label}</span>
                  {tab.badge && (
                    <span
                      className={`text-[9px] px-1.5 py-0.2 rounded font-mono ${
                        isActive
                          ? 'bg-black/20 text-black font-bold'
                          : 'bg-white/5 text-gray-400 border border-white/10'
                      }`}
                    >
                      {tab.badge}
                    </span>
                  )}
                </button>
              );
            })}
          </nav>
        </div>
      </div>
    </header>
  );
};
