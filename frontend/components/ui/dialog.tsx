"use client";

import { useEffect, useRef, useState } from "react";
import { X } from "lucide-react";
import { ApiError } from "@/lib/api";
import { cn } from "@/lib/format";
import { Button } from "./button";
import { Alert } from "./feedback";

interface DialogProps {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: React.ReactNode;
  children?: React.ReactNode;
  footer?: React.ReactNode;
  className?: string;
}

/** Native <dialog>: focus trapping, Escape and top-layer for free. */
export function Dialog({ open, onClose, title, description, children, footer, className }: DialogProps) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      onClose={onClose}
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      onClick={(e) => {
        if (e.target === ref.current) onClose();
      }}
      aria-labelledby="dialog-title"
      className={cn(
        "m-auto w-[calc(100%-2rem)] max-w-md rounded-xl border border-line bg-surface p-0 text-fg shadow-pop",
        "open:animate-fade-in",
        className
      )}
    >
      {open && (
        <div className="p-6">
          <div className="flex items-start justify-between gap-4">
            <h2 id="dialog-title" className="text-base font-semibold">
              {title}
            </h2>
            <button
              type="button"
              onClick={onClose}
              className="-m-1 rounded-md p-1 text-muted hover:bg-surface-2 hover:text-fg"
              aria-label="Close dialog"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
          {description && <div className="mt-2 text-sm leading-relaxed text-muted">{description}</div>}
          {children && <div className="mt-5">{children}</div>}
          {footer && <div className="mt-6 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">{footer}</div>}
        </div>
      )}
    </dialog>
  );
}

interface ConfirmDialogProps {
  open: boolean;
  onClose: () => void;
  title: string;
  description: React.ReactNode;
  confirmLabel: string;
  tone?: "primary" | "danger";
  onConfirm: () => Promise<unknown>;
}

/** Confirmation with built-in pending and error handling. */
export function ConfirmDialog({
  open,
  onClose,
  title,
  description,
  confirmLabel,
  tone = "primary",
  onConfirm,
}: ConfirmDialogProps) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) setError(null);
  }, [open]);

  const confirm = async () => {
    setPending(true);
    setError(null);
    try {
      await onConfirm();
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The action could not be completed.");
    } finally {
      setPending(false);
    }
  };

  return (
    <Dialog
      open={open}
      onClose={pending ? () => undefined : onClose}
      title={title}
      description={description}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={pending}>
            Cancel
          </Button>
          <Button
            variant={tone === "danger" ? "danger" : "primary"}
            className={tone === "danger" ? "border-transparent bg-danger text-white hover:bg-danger hover:opacity-90 dark:text-[#1d1210]" : ""}
            onClick={confirm}
            loading={pending}
          >
            {confirmLabel}
          </Button>
        </>
      }
    >
      {error && <Alert>{error}</Alert>}
    </Dialog>
  );
}
