import React, { useState } from 'react';
import { 
  Cpu, 
  Sparkles, 
  Zap, 
  Flame, 
  ThermometerSun, 
  Snowflake, 
  BookOpen, 
  Search, 
  CheckCircle2, 
  ArrowRight,
  TrendingUp,
  Coins
} from 'lucide-react';
import { LeadScore } from '../types';
import { PIDGIN_SLANG_DICTIONARY } from '../data/mockData';

interface NluIntentMatrixProps {
  leads: LeadScore[];
  onTestNlu: (text: string) => Promise<any>;
}

export const NluIntentMatrix: React.FC<NluIntentMatrixProps> = ({ leads, onTestNlu }) => {
  const [testInput, setTestInput] = useState('How far boss, I wan buy 2 cartons of oil make you send account number.');
  const [testResult, setTestResult] = useState<any>(null);
  const [isEvaluating, setIsEvaluating] = useState(false);
  const [searchSlang, setSearchSlang] = useState('');

  const filteredSlang = PIDGIN_SLANG_DICTIONARY.filter(
    (item) =>
      item.phrase.toLowerCase().includes(searchSlang.toLowerCase()) ||
      item.english.toLowerCase().includes(searchSlang.toLowerCase()) ||
      item.intent.toLowerCase().includes(searchSlang.toLowerCase())
  );

  const handleRunNluTest = async () => {
    if (!testInput.trim()) return;
    setIsEvaluating(true);
    try {
      const res = await onTestNlu(testInput);
      setTestResult(res);
    } catch (e) {
      console.error('NLU evaluation error:', e);
    } finally {
      setIsEvaluating(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Banner: Localized NLU Overview */}
      <div className="bg-[#151518] border border-white/5 rounded-2xl p-5 shadow-sm">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="h-2 w-2 rounded-full bg-emerald-500"></span>
              <h2 className="text-sm font-semibold text-white tracking-tight">Hyper-Localized Nigerian NLU &amp; Intent Scoring Matrix</h2>
            </div>
            <p className="text-xs text-gray-400 max-w-3xl leading-relaxed">
              Global LLMs fail on Nigerian Pidgin and commercial market dialect. Our dual-tiered architecture uses a 
              <strong className="text-emerald-400 font-mono"> Deterministic Fast-Path Router (0 token OPEX)</strong> for standard slang/orders, and escalates nuanced commercial queries to <strong className="text-purple-400 font-mono">Gemini 3.7 Flash</strong> with Nigerian market system prompts.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <div className="bg-[#0e0e10] border border-white/5 px-3.5 py-2.5 rounded-xl text-center">
              <div className="text-[10px] text-gray-500 uppercase tracking-widest font-mono">Fast-Path Hit Rate</div>
              <div className="text-base font-bold text-emerald-400 font-mono mt-0.5">83.1%</div>
            </div>
            <div className="bg-[#0e0e10] border border-white/5 px-3.5 py-2.5 rounded-xl text-center">
              <div className="text-[10px] text-gray-500 uppercase tracking-widest font-mono">Avg Evaluation</div>
              <div className="text-base font-bold text-blue-400 font-mono mt-0.5">14ms</div>
            </div>
          </div>
        </div>
      </div>

      {/* Grid: Interactive Sandbox & Lead Scoring Pipeline */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left: Interactive NLU Sandbox */}
        <div className="lg:col-span-6 space-y-4">
          <div className="bg-[#151518] border border-white/5 rounded-2xl p-4 shadow-sm">
            <h3 className="text-xs font-semibold text-gray-300 uppercase tracking-widest flex items-center gap-2 mb-3">
              <Cpu className="w-4 h-4 text-emerald-400" />
              <span>Interactive Intent &amp; Entity Extractor Sandbox</span>
            </h3>

            <div className="space-y-3">
              <div>
                <label className="text-[10px] text-gray-400 uppercase tracking-widest block mb-1">
                  Enter WhatsApp Message (Pidgin, English, or Nigerian Commercial Slang):
                </label>
                <textarea
                  id="nlu-test-textarea"
                  value={testInput}
                  onChange={(e) => setTestInput(e.target.value)}
                  rows={3}
                  className="w-full bg-[#0e0e10] border border-white/5 text-xs p-3 rounded-xl text-gray-100 focus:outline-none focus:border-emerald-500 font-sans"
                  placeholder="e.g. How far, wetin be the wholesale price for 10 bags of rice to Ikeja?"
                />
              </div>

              {/* Preset quick test phrases */}
              <div className="flex flex-wrap gap-1.5 items-center">
                <span className="text-[10px] text-gray-500 uppercase tracking-widest py-1">Quick:</span>
                {[
                  'How far, I wan buy 2 cartons for Ikeja',
                  'My BVN is 22212345678, check my balance',
                  'Abeg reduce price small for 10 bags',
                  'I don pay ₦45,000, see debit alert',
                ].map((phrase, idx) => (
                  <button
                    key={idx}
                    onClick={() => setTestInput(phrase)}
                    className="text-[10px] bg-white/[0.02] hover:bg-white/5 text-gray-300 px-2 py-0.5 rounded-lg border border-white/5 transition-colors"
                  >
                    "{phrase.slice(0, 24)}..."
                  </button>
                ))}
              </div>

              <button
                id="evaluate-nlu-btn"
                onClick={handleRunNluTest}
                disabled={isEvaluating}
                className="w-full bg-emerald-500 hover:bg-emerald-400 disabled:opacity-40 text-black font-bold uppercase tracking-widest py-2.5 px-4 rounded-xl text-[11px] flex items-center justify-center gap-2 shadow-sm transition-colors"
              >
                {isEvaluating ? <Sparkles className="w-3.5 h-3.5 animate-spin" /> : <Zap className="w-3.5 h-3.5" />}
                <span>Evaluate Intent Matrix &amp; Route Lead</span>
              </button>
            </div>

            {/* Test Results Card */}
            {testResult && (
              <div className="mt-4 p-3.5 bg-[#0e0e10] rounded-xl border border-white/5 space-y-2.5 text-xs">
                <div className="flex items-center justify-between pb-2 border-b border-white/5">
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] uppercase tracking-widest text-gray-400 font-medium">Route:</span>
                    {testResult.source === 'FAST_PATH_DETERMINISTIC' ? (
                      <span className="bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 px-2 py-0.5 rounded font-mono text-[10px] font-bold">
                        ⚡ Fast-Path (0 Tokens / ₦0.00)
                      </span>
                    ) : (
                      <span className="bg-purple-500/10 text-purple-300 border border-purple-500/30 px-2 py-0.5 rounded font-mono text-[10px] font-bold">
                        ✨ Gemini 3.7 Flash Escalation
                      </span>
                    )}
                  </div>
                  <span className="text-[10px] text-gray-500 font-mono">{testResult.latencyMs}ms</span>
                </div>

                <div className="grid grid-cols-2 gap-2 text-[11px]">
                  <div className="p-2 rounded-lg bg-[#151518] border border-white/5">
                    <div className="text-[10px] text-gray-500 uppercase tracking-widest">Detected Intent</div>
                    <div className="text-emerald-400 font-bold font-mono mt-0.5">{testResult.intent}</div>
                  </div>
                  <div className="p-2 rounded-lg bg-[#151518] border border-white/5">
                    <div className="text-[10px] text-gray-500 uppercase tracking-widest">Dialect &amp; Confidence</div>
                    <div className="text-gray-200 font-medium mt-0.5">{testResult.dialect} ({Math.round(testResult.confidence * 100)}%)</div>
                  </div>
                  <div className="p-2 rounded-lg bg-[#151518] border border-white/5">
                    <div className="text-[10px] text-gray-500 uppercase tracking-widest">Lead Scoring Tier</div>
                    <div className="flex items-center gap-1 font-bold mt-0.5">
                      {testResult.leadTier === 'HOT' ? (
                        <span className="text-red-400 flex items-center gap-1 text-[11px]"><Flame className="w-3 h-3" /> HOT LEAD ({testResult.urgencyScore}/10)</span>
                      ) : (
                        <span className="text-amber-400 flex items-center gap-1 text-[11px]"><ThermometerSun className="w-3 h-3" /> WARM LEAD</span>
                      )}
                    </div>
                  </div>
                  <div className="p-2 rounded-lg bg-[#151518] border border-white/5">
                    <div className="text-[10px] text-gray-500 uppercase tracking-widest">Action Route</div>
                    <div className="text-blue-400 font-bold font-mono mt-0.5">{testResult.action}</div>
                  </div>
                </div>

                {/* Sanitization note */}
                {testResult.sanitization && testResult.sanitization.redactedEntities.length > 0 && (
                  <div className="p-2 rounded-lg bg-red-500/10 border border-red-500/20 text-[11px] text-red-300">
                    🛡️ <strong className="uppercase tracking-wider text-[10px]">PII Redacted:</strong> {testResult.sanitization.redactedEntities.map((e: any) => e.token).join(', ')}
                  </div>
                )}

                {/* Suggested reply preview */}
                <div className="p-2.5 rounded-lg bg-[#151518] border border-white/5">
                  <div className="text-[10px] text-gray-500 uppercase tracking-widest font-bold mb-1">Generated WhatsApp Reply:</div>
                  <div className="text-gray-200 text-xs whitespace-pre-line leading-relaxed italic">
                    "{testResult.suggestedReply}"
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Pidgin & Slang Lexicon */}
          <div className="bg-[#151518] border border-white/5 rounded-2xl p-4 shadow-sm">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <BookOpen className="w-4 h-4 text-amber-400" />
                <h3 className="text-xs font-semibold text-gray-300 uppercase tracking-widest">Nigerian Commercial Slang Lexicon</h3>
              </div>
              <div className="relative w-48">
                <Search className="w-3.5 h-3.5 absolute left-2.5 top-2 text-gray-500" />
                <input
                  type="text"
                  placeholder="Filter dictionary..."
                  value={searchSlang}
                  onChange={(e) => setSearchSlang(e.target.value)}
                  className="w-full bg-[#0e0e10] border border-white/5 text-[11px] pl-7 pr-2 py-1 rounded-lg text-gray-200 focus:outline-none focus:border-emerald-500"
                />
              </div>
            </div>

            <div className="space-y-2 max-h-56 overflow-y-auto pr-1">
              {filteredSlang.map((item, idx) => (
                <div key={idx} className="p-2.5 rounded-xl bg-[#0e0e10] border border-white/5 text-xs flex justify-between items-center">
                  <div>
                    <div className="font-medium text-emerald-400 font-mono">{item.phrase}</div>
                    <div className="text-[11px] text-gray-400">{item.english}</div>
                  </div>
                  <span className="text-[9px] bg-white/5 text-gray-400 px-2 py-0.5 rounded font-mono border border-white/10">
                    {item.intent}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Right: Dynamic Lead Qualification Matrix Table */}
        <div className="lg:col-span-6 space-y-4">
          <div className="bg-[#151518] border border-white/5 rounded-2xl p-4 flex flex-col h-full shadow-sm">
            <div className="flex items-center justify-between pb-3 border-b border-white/5">
              <div>
                <h3 className="text-xs font-semibold text-gray-300 uppercase tracking-widest flex items-center gap-2">
                  <TrendingUp className="w-4 h-4 text-blue-400" />
                  <span>Real-Time Lead Qualification Matrix</span>
                </h3>
                <p className="text-[11px] text-gray-500 mt-0.5">
                  Dynamic: <em>Urgency</em> &times; <em>Budget (₦)</em> &times; <em>Technical Scope</em>
                </p>
              </div>
              <span className="text-[10px] bg-white/5 text-gray-400 px-2 py-0.5 rounded font-mono border border-white/10">
                {leads.length} Active Leads
              </span>
            </div>

            <div className="space-y-3 mt-3 overflow-y-auto flex-1">
              {leads.map((lead, idx) => (
                <div
                  key={idx}
                  className="p-3.5 rounded-xl border border-white/5 bg-[#0e0e10] text-xs space-y-2"
                >
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="font-semibold text-white">{lead.name}</div>
                      <div className="text-[10px] text-gray-500 font-mono">{lead.phone}</div>
                    </div>

                    <span
                      className={`px-2 py-0.5 rounded-full text-[10px] font-bold font-mono flex items-center gap-1 ${
                        lead.tier === 'HOT'
                          ? 'bg-red-500/10 text-red-400 border border-red-500/30'
                          : lead.tier === 'WARM'
                          ? 'bg-amber-500/10 text-amber-400 border border-amber-500/30'
                          : 'bg-blue-500/10 text-blue-400 border border-blue-500/30'
                      }`}
                    >
                      {lead.tier === 'HOT' && <Flame className="w-3 h-3" />}
                      {lead.tier === 'WARM' && <ThermometerSun className="w-3 h-3" />}
                      {lead.tier === 'COLD' && <Snowflake className="w-3 h-3" />}
                      {lead.tier} LEAD
                    </span>
                  </div>

                  {/* Intent & Location */}
                  <div className="grid grid-cols-2 gap-2 text-[11px] pt-2 border-t border-white/5">
                    <div>
                      <span className="text-[10px] text-gray-500 uppercase tracking-widest">Detected Intent:</span>
                      <div className="font-semibold text-emerald-400 font-mono mt-0.5">{lead.detectedIntent}</div>
                    </div>
                    <div>
                      <span className="text-[10px] text-gray-500 uppercase tracking-widest">Estimated Budget:</span>
                      <div className="font-bold text-gray-200 mt-0.5">₦{lead.budgetNaira.toLocaleString()}</div>
                    </div>
                  </div>

                  {/* Routing action */}
                  <div className="p-2 rounded-lg bg-[#151518] border border-white/5 text-[11px] flex items-center justify-between">
                    <span className="text-[10px] text-gray-400 uppercase tracking-widest">Action:</span>
                    <span className="text-blue-400 font-mono font-medium">{lead.suggestedAction}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
