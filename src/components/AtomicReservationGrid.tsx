import React, { useState } from 'react';
import { 
  Calendar as CalendarIcon, 
  Clock, 
  Lock, 
  Unlock, 
  CheckCircle2, 
  AlertTriangle, 
  ShieldCheck, 
  Sparkles, 
  Users, 
  RefreshCw,
  Plus
} from 'lucide-react';
import { ReservationSlot } from '../types';

interface AtomicReservationGridProps {
  slots: ReservationSlot[];
  onBookSlot: (slotId: string, phone: string) => Promise<void>;
  onReleaseSlot: (slotId: string) => void;
  onConfirmSlotPayment: (slotId: string) => void;
}

export const AtomicReservationGrid: React.FC<AtomicReservationGridProps> = ({
  slots,
  onBookSlot,
  onReleaseSlot,
  onConfirmSlotPayment,
}) => {
  const [bookingPhone, setBookingPhone] = useState('+2348031122334');
  const [selectedSlotId, setSelectedSlotId] = useState<string | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);

  const handleHoldSlot = async (slotId: string) => {
    setIsProcessing(true);
    await onBookSlot(slotId, bookingPhone);
    setIsProcessing(false);
  };

  return (
    <div className="space-y-6">
      {/* Top Banner */}
      <div className="bg-[#151518] border border-white/5 rounded-2xl p-5 shadow-sm">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="h-2 w-2 rounded-full bg-emerald-500"></span>
              <h2 className="text-sm font-semibold text-white tracking-tight">Atomic Reservation Engine &amp; Anti-No-Show Queue</h2>
            </div>
            <p className="text-xs text-gray-400 max-w-3xl leading-relaxed">
              Double bookings destroy trust for medical clinics, logistics fleet handovers, and consultation firms. 
              Our engine simulates PostgreSQL <strong className="text-purple-400 font-mono">GiST [TSTZRANGE]</strong> exclusion locks to mathematically prevent overlapping bookings, holding slots in a 10-minute queue until the deposit clears.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <div className="bg-[#0e0e10] border border-white/5 px-4 py-2 rounded-xl text-center">
              <div className="text-[10px] text-gray-500 uppercase tracking-widest font-mono">Concurrency Lock</div>
              <div className="text-base font-bold text-emerald-400 font-mono mt-0.5">GiST Exclusion</div>
            </div>
            <div className="bg-[#0e0e10] border border-white/5 px-4 py-2 rounded-xl text-center">
              <div className="text-[10px] text-gray-500 uppercase tracking-widest font-mono">Auto-Release Window</div>
              <div className="text-base font-bold text-amber-400 font-mono mt-0.5">10 Mins</div>
            </div>
          </div>
        </div>
      </div>

      {/* SQL & Mathematical Lock Architecture Diagram */}
      <div className="bg-[#151518] border border-white/5 rounded-2xl p-4 shadow-sm">
        <div className="flex items-center justify-between pb-2 mb-3 border-b border-white/5 text-xs">
          <div className="flex items-center gap-2 font-semibold text-gray-300 uppercase tracking-widest">
            <Lock className="w-4 h-4 text-purple-400" />
            <span>Mathematical Double-Booking Exclusion Constraint</span>
          </div>
          <span className="font-mono text-[10px] text-emerald-400 bg-[#0e0e10] px-2 py-0.5 rounded font-medium border border-white/5">
            CONSTRAINT no_overlapping_slots EXCLUDE USING gist (agent_id WITH =, time_slot WITH &amp;&amp;)
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
          <div className="p-3 rounded-xl bg-[#0e0e10] border border-white/5">
            <div className="text-[10px] text-gray-400 uppercase tracking-widest font-bold mb-1">1. User Requests Slot</div>
            <p className="text-gray-300 text-[11px] leading-relaxed">
              Customer clicks time slot in WhatsApp list message. System creates a provisional atomic range hold.
            </p>
          </div>
          <div className="p-3 rounded-xl bg-[#0e0e10] border border-white/5">
            <div className="text-[10px] text-amber-400 uppercase tracking-widest font-bold mb-1">2. 10-Min Anti-No-Show Queue</div>
            <p className="text-gray-300 text-[11px] leading-relaxed">
              Slot is blocked for all other users. If deposit webhook is not received in 10 minutes, Redis unlocks the range automatically.
            </p>
          </div>
          <div className="p-3 rounded-xl bg-[#0e0e10] border border-white/5">
            <div className="text-[10px] text-emerald-400 uppercase tracking-widest font-bold mb-1">3. Webhook Confirms Slot</div>
            <p className="text-gray-300 text-[11px] leading-relaxed">
              Inbound NIBSS transfer confirms appointment. GiST range transforms from <em>HELD</em> to permanent <em>CONFIRMED</em>.
            </p>
          </div>
        </div>
      </div>

      {/* Interactive Slot Grid */}
      <div className="bg-[#151518] border border-white/5 rounded-2xl p-4 shadow-sm">
        <div className="flex items-center justify-between pb-3 border-b border-white/5 mb-4">
          <h3 className="text-xs font-semibold text-gray-300 uppercase tracking-widest flex items-center gap-2">
            <CalendarIcon className="w-4 h-4 text-emerald-400" />
            <span>Live Appointment &amp; Consultation Slots</span>
          </h3>

          <div className="flex items-center gap-2 text-xs">
            <span className="text-[10px] text-gray-400 uppercase tracking-widest">Simulate Booker:</span>
            <input
              type="text"
              value={bookingPhone}
              onChange={(e) => setBookingPhone(e.target.value)}
              className="bg-[#0e0e10] border border-white/5 px-2.5 py-1 rounded-lg text-gray-200 font-mono text-xs focus:outline-none focus:border-emerald-500"
            />
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {slots.map((slot) => {
            const isHeld = slot.status === 'HELD_PENDING_PAYMENT';
            const isConfirmed = slot.status === 'CONFIRMED';
            const isAvailable = slot.status === 'AVAILABLE';

            return (
              <div
                key={slot.id}
                id={`slot-card-${slot.id}`}
                className={`p-4 rounded-xl border text-xs space-y-3 transition-all ${
                  isConfirmed
                    ? 'bg-emerald-500/5 border-emerald-500/20 text-gray-200'
                    : isHeld
                    ? 'bg-amber-500/5 border-amber-500/20 text-gray-200'
                    : 'bg-[#0e0e10] border-white/5 text-gray-200 hover:border-white/10'
                }`}
              >
                <div className="flex items-center justify-between">
                  <div className="font-semibold text-white text-sm">{slot.service}</div>
                  <span
                    className={`px-2 py-0.5 rounded-full text-[10px] font-bold font-mono ${
                      isConfirmed
                        ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30'
                        : isHeld
                        ? 'bg-amber-500/10 text-amber-400 border border-amber-500/30 animate-pulse'
                        : 'bg-white/5 text-gray-400 border border-white/10'
                    }`}
                  >
                    {slot.status}
                  </span>
                </div>

                <div className="grid grid-cols-2 gap-2 text-[11px] p-2.5 rounded-lg bg-[#151518] border border-white/5">
                  <div>
                    <span className="text-[10px] text-gray-500 uppercase tracking-widest">Consultant / Agent:</span>
                    <div className="font-medium text-gray-200 mt-0.5">{slot.agentName}</div>
                  </div>
                  <div>
                    <span className="text-[10px] text-gray-500 uppercase tracking-widest">Time Range:</span>
                    <div className="font-medium text-blue-400 font-mono mt-0.5">{slot.startTime} – {slot.endTime}</div>
                  </div>
                  <div>
                    <span className="text-[10px] text-gray-500 uppercase tracking-widest">Commitment Deposit:</span>
                    <div className="font-bold text-emerald-400 mt-0.5">₦{slot.priceNaira.toLocaleString()}</div>
                  </div>
                  <div>
                    <span className="text-[10px] text-gray-500 uppercase tracking-widest">Lock Status:</span>
                    <div className="font-mono text-purple-400 mt-0.5">
                      {isAvailable ? '🔓 Range Available' : '🔒 GiST Locked'}
                    </div>
                  </div>
                </div>

                {/* Status-specific Action Bar */}
                {isAvailable && (
                  <button
                    id={`book-slot-btn-${slot.id}`}
                    onClick={() => handleHoldSlot(slot.id)}
                    disabled={isProcessing}
                    className="w-full bg-purple-600 hover:bg-purple-500 text-white font-bold uppercase tracking-widest py-2 px-3 rounded-lg text-[10px] flex items-center justify-center gap-1.5 transition-colors shadow-sm"
                  >
                    <Lock className="w-3.5 h-3.5" />
                    <span>Lock Slot with 10-Minute Anti-No-Show Hold</span>
                  </button>
                )}

                {isHeld && (
                  <div className="space-y-2 pt-1">
                    <div className="text-[11px] text-amber-300 flex items-center justify-between">
                      <span>Provisional Hold for: <strong className="font-mono">{slot.heldByPhone}</strong></span>
                      <span className="font-bold font-mono">7:42 remaining</span>
                    </div>
                    <div className="grid grid-cols-2 gap-2">
                      <button
                        onClick={() => onConfirmSlotPayment(slot.id)}
                        className="bg-emerald-500 hover:bg-emerald-400 text-black font-bold uppercase tracking-widest py-1.5 px-2 rounded-lg text-[10px] flex items-center justify-center gap-1 transition-colors shadow-sm"
                      >
                        <CheckCircle2 className="w-3 h-3" />
                        <span>Simulate Deposit Webhook</span>
                      </button>
                      <button
                        onClick={() => onReleaseSlot(slot.id)}
                        className="bg-red-500/10 hover:bg-red-500/20 border border-red-500/30 text-red-300 font-bold uppercase tracking-widest py-1.5 px-2 rounded-lg text-[10px] flex items-center justify-center gap-1 transition-colors"
                      >
                        <Unlock className="w-3 h-3" />
                        <span>Release Slot</span>
                      </button>
                    </div>
                  </div>
                )}

                {isConfirmed && (
                  <div className="p-2.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-[11px] text-emerald-300 flex items-center justify-between">
                    <span>✓ Appointment confirmed &amp; synced to calendar</span>
                    <span className="font-mono text-[10px] text-gray-400">Ref: {slot.transactionRef}</span>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};
