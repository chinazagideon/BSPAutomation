import React, { useState } from 'react';
import { 
  ArrowRightLeft, 
  Clock, 
  CheckCircle2, 
  AlertTriangle, 
  CreditCard, 
  Send, 
  Sparkles, 
  Building2, 
  Layers, 
  CheckCheck,
  RefreshCw,
  Scale,
  DollarSign
} from 'lucide-react';
import { AntiGhostingCart, LedgerEntry } from '../types';

interface AntiGhostingLedgerProps {
  carts: AntiGhostingCart[];
  ledgerEntries: LedgerEntry[];
  onTriggerBankSettlement: (ref: string, amount: number) => Promise<void>;
  onValidateLedger: (data: any) => Promise<any>;
}

export const AntiGhostingLedger: React.FC<AntiGhostingLedgerProps> = ({
  carts,
  ledgerEntries,
  onTriggerBankSettlement,
  onValidateLedger,
}) => {
  const [selectedCart, setSelectedCart] = useState<AntiGhostingCart>(carts[0]);
  const [isSettling, setIsSettling] = useState(false);
  const [ledgerAuditForm, setLedgerAuditForm] = useState({
    assets: 195000,
    liabilities: 45000,
    equity: 150000,
    expectedAmount: 45000,
    receivedAmount: 42000,
    ref: 'TXN_NIBSS_AUDIT_991',
  });
  const [auditResult, setAuditResult] = useState<any>(null);
  const [isAuditing, setIsAuditing] = useState(false);

  const handleSimulatePayment = async (cart: AntiGhostingCart) => {
    setIsSettling(true);
    await onTriggerBankSettlement(cart.virtualAccount.ref, cart.totalNaira);
    setIsSettling(false);
  };

  const handleRunAudit = async () => {
    setIsAuditing(true);
    try {
      const res = await onValidateLedger(ledgerAuditForm);
      setAuditResult(res);
    } catch (e) {
      console.error('Ledger validation error:', e);
    } finally {
      setIsAuditing(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Architecture Banner */}
      <div className="bg-[#151518] border border-white/5 rounded-2xl p-5 shadow-sm">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="h-2 w-2 rounded-full bg-emerald-500"></span>
              <h2 className="text-sm font-semibold text-white tracking-tight">Asynchronous Anti-Ghosting Checkout &amp; Double-Entry Ledger</h2>
            </div>
            <p className="text-xs text-gray-400 max-w-3xl leading-relaxed">
              Nigerian shoppers frequently leave WhatsApp to open banking apps or dial USSD codes. 
              Our engine preserves checkout state for 10 minutes, generates dedicated virtual NUBANs (Moniepoint/Wema), and proactively pushes the WhatsApp receipt once the NIBSS settlement clears.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <div className="bg-[#0e0e10] border border-white/5 px-4 py-2 rounded-xl text-center">
              <div className="text-[10px] text-gray-500 uppercase tracking-widest font-mono">Anti-Ghosting Recovery</div>
              <div className="text-base font-bold text-emerald-400 font-mono mt-0.5">96.4%</div>
            </div>
            <div className="bg-[#0e0e10] border border-white/5 px-4 py-2 rounded-xl text-center">
              <div className="text-[10px] text-gray-500 uppercase tracking-widest font-mono">Ledger Accuracy</div>
              <div className="text-base font-bold text-blue-400 font-mono mt-0.5">100% (Balanced)</div>
            </div>
          </div>
        </div>
      </div>

      {/* Grid: Active Anti-Ghosting Carts & Double-Entry Ledger Table */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left: Active Anti-Ghosting Sessions */}
        <div className="lg:col-span-6 space-y-4">
          <div className="bg-[#151518] border border-white/5 rounded-2xl p-4 shadow-sm">
            <div className="flex items-center justify-between pb-3 border-b border-white/5">
              <div className="flex items-center gap-2">
                <Clock className="w-4 h-4 text-amber-400" />
                <h3 className="text-xs font-semibold text-gray-300 uppercase tracking-widest">Active 10-Minute Cart Holds</h3>
              </div>
              <span className="text-[10px] bg-white/5 text-gray-400 px-2 py-0.5 rounded font-mono border border-white/10">
                {carts.length} Active Sessions
              </span>
            </div>

            <div className="space-y-3 mt-3">
              {carts.map((cart) => (
                <div
                  key={cart.sessionId}
                  id={`cart-session-${cart.sessionId}`}
                  className="p-3.5 rounded-xl border border-white/5 bg-[#0e0e10] text-xs space-y-2.5"
                >
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="font-semibold text-white">{cart.customerName}</div>
                      <div className="text-[10px] text-gray-500 font-mono">{cart.customerPhone}</div>
                    </div>

                    <span
                      className={`px-2 py-0.5 rounded-full text-[10px] font-bold font-mono ${
                        cart.status === 'PAYMENT_RECEIVED'
                          ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30'
                          : 'bg-amber-500/10 text-amber-400 border border-amber-500/30 animate-pulse'
                      }`}
                    >
                      {cart.status === 'PAYMENT_RECEIVED' ? '✓ SETTLED & PUSHED' : '⏳ AWAITING BANK TRANSFER'}
                    </span>
                  </div>

                  {/* Items */}
                  <div className="p-2.5 rounded-lg bg-[#151518] border border-white/5 space-y-1">
                    {cart.items.map((it, idx) => (
                      <div key={idx} className="flex justify-between text-[11px]">
                        <span className="text-gray-300">{it.quantity}x {it.name}</span>
                        <span className="text-emerald-400 font-bold">₦{(it.quantity * it.unitPrice).toLocaleString()}</span>
                      </div>
                    ))}
                  </div>

                  {/* Dedicated Virtual NUBAN Account */}
                  <div className="p-2.5 rounded-lg bg-[#151518] border border-white/5 text-[11px] space-y-1">
                    <div className="text-[10px] text-gray-500 uppercase tracking-widest font-bold">Assigned Virtual Bank Account:</div>
                    <div className="flex justify-between font-mono">
                      <span className="text-gray-400">Bank: <strong className="text-gray-200">{cart.virtualAccount.bank}</strong></span>
                      <span className="text-gray-400">NUBAN: <strong className="text-emerald-400 font-bold">{cart.virtualAccount.accountNumber}</strong></span>
                    </div>
                  </div>

                  {/* Settlement Action Button */}
                  {cart.status !== 'PAYMENT_RECEIVED' && (
                    <button
                      onClick={() => handleSimulatePayment(cart)}
                      disabled={isSettling}
                      className="w-full bg-emerald-500 hover:bg-emerald-400 disabled:opacity-40 text-black font-bold uppercase tracking-widest py-2 px-3 rounded-lg text-[10px] flex items-center justify-center gap-1.5 transition-colors shadow-sm"
                    >
                      <CreditCard className="w-3.5 h-3.5" />
                      <span>Simulate Inbound Bank Settlement (Push WhatsApp Receipt)</span>
                    </button>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Right: Double-Entry Ledger & AI Discrepancy Reconciliation */}
        <div className="lg:col-span-6 space-y-4">
          {/* Double-Entry Ledger Validation Form */}
          <div className="bg-[#151518] border border-white/5 rounded-2xl p-4 shadow-sm">
            <div className="flex items-center justify-between mb-3 pb-2 border-b border-white/5">
              <div className="flex items-center gap-2">
                <Scale className="w-4 h-4 text-emerald-400" />
                <h3 className="text-xs font-semibold text-gray-300 uppercase tracking-widest">
                  Ledger Validation ($Assets = Liabilities + Equity$)
                </h3>
              </div>
              <span className="text-[10px] bg-white/5 text-gray-400 px-2 py-0.5 rounded font-mono border border-white/10">
                Pydantic Deterministic
              </span>
            </div>

            <div className="grid grid-cols-3 gap-2 text-xs mb-3">
              <div>
                <label className="text-[10px] text-gray-400 uppercase tracking-widest block mb-1">Assets (₦)</label>
                <input
                  type="number"
                  value={ledgerAuditForm.assets}
                  onChange={(e) => setLedgerAuditForm({ ...ledgerAuditForm, assets: Number(e.target.value) })}
                  className="w-full bg-[#0e0e10] border border-white/5 p-2 rounded-xl text-gray-200 font-mono text-xs focus:outline-none focus:border-emerald-500"
                />
              </div>
              <div>
                <label className="text-[10px] text-gray-400 uppercase tracking-widest block mb-1">Liabilities (₦)</label>
                <input
                  type="number"
                  value={ledgerAuditForm.liabilities}
                  onChange={(e) => setLedgerAuditForm({ ...ledgerAuditForm, liabilities: Number(e.target.value) })}
                  className="w-full bg-[#0e0e10] border border-white/5 p-2 rounded-xl text-gray-200 font-mono text-xs focus:outline-none focus:border-emerald-500"
                />
              </div>
              <div>
                <label className="text-[10px] text-gray-400 uppercase tracking-widest block mb-1">Equity (₦)</label>
                <input
                  type="number"
                  value={ledgerAuditForm.equity}
                  onChange={(e) => setLedgerAuditForm({ ...ledgerAuditForm, equity: Number(e.target.value) })}
                  className="w-full bg-[#0e0e10] border border-white/5 p-2 rounded-xl text-gray-200 font-mono text-xs focus:outline-none focus:border-emerald-500"
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-2 text-xs mb-3">
              <div>
                <label className="text-[10px] text-gray-400 uppercase tracking-widest block mb-1">Expected Deposit (₦)</label>
                <input
                  type="number"
                  value={ledgerAuditForm.expectedAmount}
                  onChange={(e) => setLedgerAuditForm({ ...ledgerAuditForm, expectedAmount: Number(e.target.value) })}
                  className="w-full bg-[#0e0e10] border border-white/5 p-2 rounded-xl text-gray-200 font-mono text-xs focus:outline-none focus:border-emerald-500"
                />
              </div>
              <div>
                <label className="text-[10px] text-gray-400 uppercase tracking-widest block mb-1">Actual Received (₦)</label>
                <input
                  type="number"
                  value={ledgerAuditForm.receivedAmount}
                  onChange={(e) => setLedgerAuditForm({ ...ledgerAuditForm, receivedAmount: Number(e.target.value) })}
                  className="w-full bg-[#0e0e10] border border-white/5 p-2 rounded-xl text-gray-200 font-mono text-xs focus:outline-none focus:border-emerald-500"
                />
              </div>
            </div>

            <button
              id="validate-ledger-btn"
              onClick={handleRunAudit}
              disabled={isAuditing}
              className="w-full bg-emerald-500 hover:bg-emerald-400 disabled:opacity-40 text-black font-bold uppercase tracking-widest py-2.5 px-4 rounded-xl text-[11px] flex items-center justify-center gap-2 transition-colors shadow-sm"
            >
              {isAuditing ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Scale className="w-3.5 h-3.5" />}
              <span>Verify Balance Sheet &amp; Run AI Discrepancy Check</span>
            </button>

            {/* Audit Output Result */}
            {auditResult && (
              <div className="mt-3 p-3.5 bg-[#0e0e10] rounded-xl border border-white/5 space-y-2 text-xs">
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-gray-200">Accounting Equation:</span>
                  <span className={`font-mono font-bold ${auditResult.isBalanced ? 'text-emerald-400' : 'text-red-400'}`}>
                    {auditResult.accountingEquation}
                  </span>
                </div>

                {auditResult.aiExplanation && (
                  <div className="p-2.5 rounded-lg bg-purple-500/10 border border-purple-500/20 text-[11px] text-purple-200 space-y-1">
                    <div className="font-bold flex items-center gap-1">
                      <Sparkles className="w-3.5 h-3.5 text-purple-400" />
                      <span className="uppercase tracking-widest text-[10px]">Gemini AI Discrepancy Reconciliation:</span>
                    </div>
                    <div className="leading-relaxed">{auditResult.aiExplanation}</div>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Ledger Historical Log Table */}
          <div className="bg-[#151518] border border-white/5 rounded-2xl p-4 shadow-sm">
            <h3 className="text-xs font-semibold text-gray-300 uppercase tracking-widest mb-3">Immutable Double-Entry Ledger Logs</h3>
            <div className="space-y-2 max-h-52 overflow-y-auto pr-1 text-xs">
              {ledgerEntries.map((entry) => (
                <div key={entry.id} className="p-2.5 rounded-xl bg-[#0e0e10] border border-white/5 space-y-1">
                  <div className="flex justify-between font-mono font-semibold">
                    <span className="text-gray-300">{entry.ref}</span>
                    <span className="text-emerald-400 font-bold">₦{entry.amountNaira.toLocaleString()}</span>
                  </div>
                  <div className="text-[11px] text-gray-400">{entry.customer}</div>
                  <div className="flex justify-between text-[10px] text-gray-500 pt-1 border-t border-white/5">
                    <span>Debit: {entry.debitAccount.slice(0, 20)}...</span>
                    <span className={entry.isBalanced ? 'text-emerald-400' : 'text-red-400'}>
                      {entry.isBalanced ? '✓ Balanced' : '⚠ Mismatch'}
                    </span>
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
