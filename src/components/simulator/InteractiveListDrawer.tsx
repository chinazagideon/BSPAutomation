import React from 'react';
import { X } from 'lucide-react';
import { InteractiveListSection } from '../../types';

interface InteractiveListDrawerProps {
  drawer: {
    title: string;
    sections: InteractiveListSection[];
  } | null;
  onClose: () => void;
  onSelectRow: (id: string, title: string) => void;
}

export const InteractiveListDrawer: React.FC<InteractiveListDrawerProps> = ({
  drawer,
  onClose,
  onSelectRow,
}) => {
  if (!drawer) return null;

  return (
    <div className="absolute inset-0 bg-black/75 z-20 flex flex-col justify-end animate-fadeIn">
      <div className="bg-[#151518] border-t border-white/10 rounded-t-3xl max-h-[75%] flex flex-col">
        <div className="px-4 py-3 border-b border-white/10 flex items-center justify-between">
          <span className="font-semibold text-xs text-white">{drawer.title}</span>
          <button onClick={onClose} className="text-gray-400 hover:text-white p-1">
            <X className="w-4 h-4" />
          </button>
        </div>
        <div className="p-3 overflow-y-auto space-y-3">
          {drawer.sections.map((sec, sIdx) => (
            <div key={sIdx} className="space-y-1.5">
              {sec.title && (
                <div className="text-[10px] font-bold uppercase tracking-wider text-emerald-400 px-1">
                  {sec.title}
                </div>
              )}
              {sec.rows.map((row) => (
                <button
                  key={row.id}
                  onClick={() => onSelectRow(row.id, row.title)}
                  className="w-full text-left p-2.5 rounded-xl bg-[#0e0e10] hover:bg-emerald-500/15 border border-white/5 hover:border-emerald-500/30 transition-colors"
                >
                  <div className="text-xs font-medium text-gray-100">{row.title}</div>
                  {row.description && (
                    <div className="text-[10px] text-gray-400 mt-0.5">{row.description}</div>
                  )}
                </button>
              ))}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
