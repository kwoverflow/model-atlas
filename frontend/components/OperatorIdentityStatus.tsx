"use client";

import { LoaderCircle, LogIn, LogOut, UserRound } from "lucide-react";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { API_BASE_URL } from "@/lib/apiBase";
import { browserApiFetch } from "@/lib/browserApi";
import type { BrowserOIDCStatus, OperatorIdentity } from "@/types/api";

export function OperatorIdentityStatus() {
  const pathname = usePathname();
  const [identity, setIdentity] = useState<OperatorIdentity | null>(null);
  const [oidc, setOidc] = useState<BrowserOIDCStatus | null>(null);
  const [signingOut, setSigningOut] = useState(false);

  useEffect(() => {
    let active = true;
    Promise.all([
      browserApiFetch(`${API_BASE_URL}/operator-identity/me`, { cache: "no-store" }),
      browserApiFetch(`${API_BASE_URL}/operator-identity/browser-config`, {
        cache: "no-store"
      })
    ])
      .then(async ([identityResponse, oidcResponse]) => {
        if (!identityResponse.ok || !oidcResponse.ok) return;
        const nextIdentity = (await identityResponse.json()) as OperatorIdentity;
        const nextOidc = (await oidcResponse.json()) as BrowserOIDCStatus;
        if (active) {
          setIdentity(nextIdentity);
          setOidc(nextOidc);
        }
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, []);

  const returnTo = encodeURIComponent(pathname || "/");
  const loginUrl = `${API_BASE_URL}/operator-identity/login?return_to=${returnTo}`;
  const logoutUrl = `${API_BASE_URL}/operator-identity/logout?return_to=${returnTo}`;
  const verified = Boolean(identity?.identity_verified);

  async function signOut() {
    if (signingOut) return;
    setSigningOut(true);
    try {
      const response = await browserApiFetch(logoutUrl, { method: "POST" });
      if (!response.ok) throw new Error("Sign out failed");
      const payload = (await response.json()) as BrowserLogoutResponse;
      const target = new URL(payload.redirect_url, window.location.origin);
      if (!['http:', 'https:'].includes(target.protocol)) {
        throw new Error("Invalid sign out redirect");
      }
      window.location.assign(target.toString());
    } catch {
      setSigningOut(false);
    }
  }

  return (
    <div className="grid gap-2">
      <div className="flex min-w-0 items-center gap-2">
        <span className="grid h-8 w-8 shrink-0 place-items-center rounded-md bg-neutral-100 text-neutral-700">
          <UserRound size={16} aria-hidden="true" />
        </span>
        <span className="min-w-0">
          <span className="block truncate text-xs font-semibold text-neutral-800">
            {identity?.display_name ?? "Local UI"}
          </span>
          <span className="block truncate text-xs text-neutral-500">
            {identity?.role ?? (verified ? "Verified operator" : "Unverified session")}
          </span>
        </span>
      </div>
      {oidc?.enabled ? (
        verified ? (
          <button
            type="button"
            onClick={signOut}
            disabled={signingOut}
            title="Sign out"
            className="flex h-9 items-center justify-center gap-2 rounded-md border border-line text-xs font-medium text-neutral-700 hover:bg-neutral-50 disabled:cursor-wait disabled:opacity-60"
          >
            {signingOut ? (
              <LoaderCircle className="animate-spin" size={15} aria-hidden="true" />
            ) : (
              <LogOut size={15} aria-hidden="true" />
            )}
            {signingOut ? "Signing out" : "Sign out"}
          </button>
        ) : (
          <a
            href={loginUrl}
            title="Sign in with the configured identity provider"
            className="flex h-9 items-center justify-center gap-2 rounded-md bg-ink text-xs font-medium text-white hover:bg-neutral-800"
          >
            <LogIn size={15} aria-hidden="true" />
            Sign in
          </a>
        )
      ) : null}
    </div>
  );
}

type BrowserLogoutResponse = {
  redirect_url: string;
  provider_logout: boolean;
  session_revoked: boolean;
};
