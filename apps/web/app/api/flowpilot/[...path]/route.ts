import type { NextRequest } from "next/server";

const internalApiBaseUrl = process.env.INTERNAL_API_BASE_URL ?? "http://localhost:8000";
const authMode = process.env.FLOWPILOT_WEB_AUTH_MODE ?? "demo";

const forwardedRequestHeaders = [
  "content-type",
  "idempotency-key",
  "last-event-id",
  "x-request-id",
] as const;

function upstreamHeaders(request: NextRequest): Headers {
  const headers = new Headers();
  for (const name of forwardedRequestHeaders) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  if (authMode === "demo") {
    headers.set("X-Tenant-ID", process.env.DEMO_TENANT_ID ?? "tenant-demo");
    headers.set("X-User-ID", process.env.DEMO_USER_ID ?? "user-demo");
    headers.set("X-User-Email", process.env.DEMO_USER_EMAIL ?? "operator@northstar.example");
    headers.set("X-User-Role", "approver");
    return headers;
  }
  const authorization =
    request.headers.get("authorization") ??
    request.headers.get("x-forwarded-access-token") ??
    request.cookies.get("flowpilot_access_token")?.value;
  if (authorization) {
    headers.set(
      "Authorization",
      authorization.toLowerCase().startsWith("bearer ")
        ? authorization
        : `Bearer ${authorization}`,
    );
  }
  return headers;
}

async function proxy(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
): Promise<Response> {
  const { path } = await context.params;
  const upstreamUrl = new URL(`/v1/${path.join("/")}`, internalApiBaseUrl);
  upstreamUrl.search = request.nextUrl.search;
  const hasBody = !["GET", "HEAD"].includes(request.method);
  const upstream = await fetch(upstreamUrl, {
    method: request.method,
    headers: upstreamHeaders(request),
    body: hasBody ? await request.arrayBuffer() : undefined,
    cache: "no-store",
    redirect: "manual",
  });
  const responseHeaders = new Headers();
  for (const name of ["content-type", "cache-control", "x-request-id"]) {
    const value = upstream.headers.get(name);
    if (value) responseHeaders.set(name, value);
  }
  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: responseHeaders,
  });
}

export const dynamic = "force-dynamic";
export const GET = proxy;
export const POST = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
