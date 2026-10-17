import React, { useEffect, useRef } from "react";
import { X, Check, ChevronDown, FileCheck2, ArrowUpRight } from "lucide-react";
import type { Run } from "./types";

export function Dialog({
  title,
  children,
  onClose,
}: {
  title: string;
  children: React.ReactNode;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    ref.current?.showModal();
    return () => ref.current?.close();
  }, []);
  return (
    <dialog
      ref={ref}
      className="dialog"
      onCancel={onClose}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="dialog-head">
        <span className="eyebrow">REWIRE / CONTROL ROOM</span>
        <button
          className="icon-button"
          aria-label="Close dialog"
          onClick={onClose}
        >
          <X size={19} />
        </button>
      </div>
      <h2>{title}</h2>
      {children}
    </dialog>
  );
}
export function ReceiptList({
  run,
  visibleCount,
  onAudit,
}: {
  run: Run | null;
  visibleCount: number;
  onAudit?: () => void;
}) {
  return (
    <>
      <div className="inspector-kicker">PROVIDER-CONFIRMED EVIDENCE</div>
      <h3>{visibleCount} receipts on record.</h3>
      <p className="explanation">
        A proposed step becomes confirmed only when a validated provider receipt
        is persisted in FalkorDB.
      </p>
      {run?.executionSteps
        .filter((s) => s.receiptId)
        .slice(0, visibleCount)
        .map((s) => (
          <details className="receipt-card" key={s.ordinal}>
            <summary>
              <span className="receipt-check">
                <Check size={16} />
              </span>
              <div>
                <strong>
                  {
                    run.plan.steps.find((p) => p.ordinal === s.ordinal)
                      ?.expectedOutputType
                  }
                </strong>
                <code>{s.providerRecordId}</code>
              </div>
              <ChevronDown size={14} />
            </summary>
            <div className="receipt-detail">
              <span className="section-label">STABLE OPERATION KEY</span>
              <code>{s.operationKey}</code>
              <span className="section-label">GRAPH RECEIPT</span>
              <code>{s.receiptId}</code>
            </div>
          </details>
        ))}
      {!visibleCount && (
        <div className="empty-inline small">
          <FileCheck2 size={26} />
          <p>No provider receipts yet.</p>
        </div>
      )}
      {onAudit && visibleCount > 0 && (
        <button className="text-button" onClick={onAudit}>
          Inspect independent provider audit <ArrowUpRight size={15} />
        </button>
      )}
    </>
  );
}
