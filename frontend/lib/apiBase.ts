export const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:18000/api/v1"
).replace(/\/$/, "");

export const SERVER_API_BASE_URL = (
  process.env.SERVER_API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:18000/api/v1"
).replace(/\/$/, "");
