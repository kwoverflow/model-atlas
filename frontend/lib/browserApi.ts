const CSRF_COOKIE_NAME =
  process.env.NEXT_PUBLIC_CSRF_COOKIE_NAME ?? "model_atlas_csrf";
const CSRF_HEADER_NAME =
  process.env.NEXT_PUBLIC_CSRF_HEADER_NAME ?? "x-model-atlas-csrf";
const UNSAFE_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

export function browserApiFetch(
  input: RequestInfo | URL,
  init: RequestInit = {}
): Promise<Response> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);
  if (UNSAFE_METHODS.has(method)) {
    const csrfToken = readCookie(CSRF_COOKIE_NAME);
    if (csrfToken) headers.set(CSRF_HEADER_NAME, csrfToken);
  }
  return fetch(input, {
    ...init,
    headers,
    credentials: "include"
  });
}

function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const prefix = `${encodeURIComponent(name)}=`;
  const cookie = document.cookie
    .split(";")
    .map((value) => value.trim())
    .find((value) => value.startsWith(prefix));
  return cookie ? decodeURIComponent(cookie.slice(prefix.length)) : null;
}
