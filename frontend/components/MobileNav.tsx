"use client";

import { Menu, X } from "lucide-react";
import { useEffect, useState } from "react";

import { Brand, NavigationLinks } from "@/components/SidebarNav";
import { OperatorIdentityStatus } from "@/components/OperatorIdentityStatus";

export function MobileNav() {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    document.body.style.overflow = open ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [open]);

  return (
    <>
      <header className="sticky top-0 z-30 flex h-16 items-center justify-between border-b border-line bg-panel px-4 lg:hidden">
        <Brand />
        <button
          type="button"
          onClick={() => setOpen(true)}
          aria-label="Open navigation"
          aria-expanded={open}
          className="grid h-10 w-10 place-items-center rounded-md border border-line text-neutral-700"
        >
          <Menu size={20} aria-hidden="true" />
        </button>
      </header>
      {open ? (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button
            type="button"
            aria-label="Close navigation overlay"
            className="absolute inset-0 bg-neutral-950/40"
            onClick={() => setOpen(false)}
          />
          <aside className="absolute inset-y-0 left-0 flex w-[min(88vw,320px)] flex-col border-r border-line bg-panel shadow-xl">
            <div className="flex h-16 items-center justify-between border-b border-line px-4">
              <Brand />
              <button
                type="button"
                onClick={() => setOpen(false)}
                aria-label="Close navigation"
                className="grid h-10 w-10 place-items-center rounded-md border border-line text-neutral-700"
              >
                <X size={20} aria-hidden="true" />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto px-3 py-5">
              <NavigationLinks onNavigate={() => setOpen(false)} />
            </div>
            <div className="border-t border-line px-4 py-4">
              <OperatorIdentityStatus />
            </div>
          </aside>
        </div>
      ) : null}
    </>
  );
}
