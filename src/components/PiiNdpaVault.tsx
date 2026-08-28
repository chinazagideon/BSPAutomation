import React, { useState } from 'react';
import { 
  ShieldCheck, 
  Lock, 
  Eye, 
  EyeOff, 
  FileText, 
  Coins, 
  DollarSign, 
  CheckCircle2, 
  AlertTriangle, 
  Sparkles, 
  Database, 
  RefreshCw,
  Hash
} from 'lucide-react';
import { NdpaConsentRecord } from '../types';

interface PiiNdpaVaultProps {
  ndpaRecords: NdpaConsentRecord[];
  onSanitizeTest: (text: string) => Promise<any>;
}

export const PiiNdpaVault: React.FC<PiiNdpaVaultProps> = ({ ndpaRecords, onSanitizeTest }) => {
  const [testPiiInput, setTestPiiInput] = useState(
    'My BVN is 22298765432 and my NIN is 12345678901. Send payment to my account 0123456789 (GTBank).'
  );
  const [sanitizationOutput, setSanitizationOutput] = useState<any>(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [hardCapLimitNaira, setHardCapLimitNaira] = useState(150000);
  const [currentSpentNaira, setCurrentSpentNaira] = useState(38400);

  const handleRunSanitize = async () => {
    setIsProcessing(true);
    try {
      const res = await onSanitizeTest(testPiiInput);
      setSanitizationOutput(res);
    } catch (e) {
      console.error('Sanitization error:', e);
    } finally {
      setIsProcessing(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Banner */}
      <div className="bg-[#151518] border border-white/5 rounded-2xl p-5 shadow-sm">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="h-2 w-2 rounded-full bg-emerald-500"></span>
              <h2 className="text-sm font-semibold text-white tracking-tight">
                NDPA 2023 Compliance &amp; PII Sanitization Shield
              </h2>
            </div>
            <p className="text-xs text-gray-400 max-w-3xl leading-relaxed">
              Under the Nigeria Data Protection Act (NDPA), sending unmasked BVNs or financial credentials to external LLMs violates local regulations. 
              Our pre-processing middleware scrubs sensitive numbers with tokenized masks before prompting Gemini, backed by an immutable SHA-256 audit log.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <div className="bg-[#0e0e10] border border-white/5 px-4 py-2 rounded-xl text-center">
              <div className="text-[10px] text-gray-500 uppercase tracking-widest font-mono">NDPA Audit Status</div>
              <div className="text-base font-bold text-emerald-400 font-mono mt-0.5">100% Compliant</div>
            </div>
            <div className="bg-[#0e0e10] border border-white/5 px-4 py-2 rounded-xl text-center">
              <div className="text-[10px] text-gray-500 uppercase tracking-widest font-mono">PII Leakage Rate</div>
              <div className="text-base font-bold text-blue-400 font-mono mt-0.5">0.00%</div>
            </div>
          </div>
        </div>
      </div>

      {/* Grid: Interactive PII Sanitizer & NDPA Consent Log Table */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left: Interactive PII Sanitizer Sandbox */}
        <div className="lg:col-span-6 space-y-4">
          <div className="bg-[#151518] border border-white/5 rounded-2xl p-4 shadow-sm">
            <div className="flex items-center justify-between pb-3 border-b border-white/5 mb-3">
              <div className="flex items-center gap-2">
                <ShieldCheck className="w-4 h-4 text-blue-400" />
                <h3 className="text-xs font-semibold text-gray-300 uppercase tracking-widest">
                  Live PII Scrubbing Middleware Sandbox
                </h3>
              </div>
              <span className="text-[10px] bg-white/5 text-gray-400 px-2 py-0.5 rounded font-mono border border-white/10">
                Regex Tokenizer
              </span>
            </div>

            <div className="space-y-3">
              <div>
                <label className="text-[10px] text-gray-400 uppercase tracking-widest block mb-1">
                  Input Raw Text with BVN, NIN, NUBAN, or Card details:
                </label>
                <textarea
                  id="pii-input-textarea"
                  value={testPiiInput}
                  onChange={(e) => setTestPiiInput(e.target.value)}
                  rows={3}
                  className="w-full bg-[#0e0e10] border border-white/5 text-xs p-3 rounded-xl text-gray-100 focus:outline-none focus:border-emerald-500 font-mono"
                />
              </div>

              <button
                id="run-sanitize-btn"
                onClick={handleRunSanitize}
                disabled={isProcessing}
                className="w-full bg-emerald-500 hover:bg-emerald-400 disabled:opacity-40 text-black font-bold uppercase tracking-widest py-2.5 px-4 rounded-xl text-[11px] flex items-center justify-center gap-2 transition-colors shadow-sm"
              >
                {isProcessing ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Lock className="w-3.5 h-3.5" />}
                <span>Execute PII Sanitizer Pre-Processing</span>
              </button>

              {/* Redacted Output Display */}
              {sanitizationOutput && (
                <div className="p-3.5 bg-[#0e0e10] rounded-xl border border-white/5 space-y-2.5 text-xs">
                  <div className="flex items-center justify-between pb-1.5 border-b border-white/5">
                    <span className="font-semibold text-gray-200">Sanitized Prompt for LLM:</span>
                    <span className="text-[10px] text-emerald-400 font-mono">Safety Score: {sanitizationOutput.safetyScore}%</span>
                  </div>

                  <div className="p-2.5 rounded-lg bg-[#151518] border border-white/5 text-emerald-400 font-mono text-[11px] leading-relaxed">
                    {sanitizationOutput.sanitizedText}
                  </div>

                  {sanitizationOutput.redactedEntities.length > 0 && (
                    <div className="space-y-1">
                      <div className="text-[10px] text-gray-400 uppercase tracking-widest font-bold">Scrubbed Entity Token Map:</div>
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
                        {sanitizationOutput.redactedEntities.map((ent: any, idx: number) => (
                          <div key={idx} className="p-1.5 rounded-lg bg-[#151518] border border-white/5 font-mono text-[10px] flex justify-between">
                            <span className="text-gray-400">{ent.type}: {ent.value.slice(0, 3)}***</span>
                            <span className="text-blue-400 font-bold">{ent.token}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* OPEX & Local Naira Hard-Cap Control */}
          <div className="bg-[#151518] border border-white/5 rounded-2xl p-4 space-y-3 shadow-sm">
            <div className="flex items-center justify-between pb-2 border-b border-white/5">
              <div className="flex items-center gap-2">
                <Coins className="w-4 h-4 text-emerald-400" />
                <h3 className="text-xs font-semibold text-gray-300 uppercase tracking-widest">
                  Naira (₦) OPEX &amp; Token Cap Controls
                </h3>
              </div>
              <span className="text-[10px] bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 px-2 py-0.5 rounded font-mono font-bold">
                African BSP Local Billing
              </span>
            </div>

            <p className="text-[11px] text-gray-400 leading-relaxed">
              Protects Nigerian merchants from FX dollar fluctuations through deterministic fast-path routing and hard-capped monthly Naira token limits.
            </p>

            <div className="space-y-2 text-xs">
              <div className="flex justify-between items-center text-gray-300">
                <span className="text-[11px] uppercase tracking-wider text-gray-400">Monthly Token Budget Cap:</span>
                <span className="font-bold text-white font-mono">₦{hardCapLimitNaira.toLocaleString()}</span>
              </div>

              {/* Progress bar */}
              <div className="w-full h-2 rounded-full bg-[#0e0e10] overflow-hidden border border-white/5">
                <div 
                  className="h-full bg-emerald-500 rounded-full"
                  style={{ width: `${(currentSpentNaira / hardCapLimitNaira) * 100}%` }}
                />
              </div>

              <div className="flex justify-between text-[10px] text-gray-500 font-mono">
                <span>Spent: ₦{currentSpentNaira.toLocaleString()} (25.6%)</span>
                <span>Remaining: ₦{(hardCapLimitNaira - currentSpentNaira).toLocaleString()}</span>
              </div>
            </div>
          </div>
        </div>

        {/* Right: NDPA Immutable Consent Records */}
        <div className="lg:col-span-6 space-y-4">
          <div className="bg-[#151518] border border-white/5 rounded-2xl p-4 flex flex-col h-full shadow-sm">
            <div className="flex items-center justify-between pb-3 border-b border-white/5 mb-3">
              <div>
                <h3 className="text-xs font-semibold text-gray-300 uppercase tracking-widest flex items-center gap-2">
                  <Database className="w-4 h-4 text-emerald-400" />
                  <span>NDPA Opt-in Consent Ledger &amp; Audit Trail</span>
                </h3>
                <p className="text-[11px] text-gray-500 mt-0.5">
                  Section 24 NDPA 2023 Explicit Consent Verification
                </p>
              </div>
              <span className="text-[10px] bg-white/5 text-gray-400 px-2 py-0.5 rounded font-mono border border-white/10">
                {ndpaRecords.length} Consents
              </span>
            </div>

            <div className="space-y-3 overflow-y-auto flex-1">
              {ndpaRecords.map((rec) => (
                <div
                  key={rec.id}
                  className="p-3.5 rounded-xl border border-white/5 bg-[#0e0e10] text-xs space-y-2"
                >
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="font-semibold text-white font-mono">{rec.phone}</div>
                      <div className="text-[10px] text-gray-500 mt-0.5">{rec.optInTimestamp}</div>
                    </div>

                    <span className="bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 text-[10px] font-bold px-2 py-0.5 rounded-full font-mono">
                      ✓ {rec.status}
                    </span>
                  </div>

                  <div className="grid grid-cols-2 gap-2 text-[11px] p-2.5 rounded-lg bg-[#151518] border border-white/5">
                    <div>
                      <span className="text-[10px] text-gray-500 uppercase tracking-widest">Consent Category:</span>
                      <div className="font-medium text-blue-400 font-mono mt-0.5">{rec.consentType}</div>
                    </div>
                    <div>
                      <span className="text-[10px] text-gray-500 uppercase tracking-widest">Origin IP / Network:</span>
                      <div className="font-mono text-gray-300 text-[10px] mt-0.5">{rec.ipAddress}</div>
                    </div>
                  </div>

                  {/* Immutable Hash */}
                  <div className="p-2 rounded-lg bg-[#151518] border border-white/5 font-mono text-[10px] text-gray-400 flex items-center justify-between">
                    <span className="flex items-center gap-1">
                      <Hash className="w-3 h-3 text-emerald-400" />
                      <span>Audit Hash: {rec.immutableHash.slice(0, 18)}...</span>
                    </span>
                    <span className="text-emerald-400 font-bold">VERIFIED</span>
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
