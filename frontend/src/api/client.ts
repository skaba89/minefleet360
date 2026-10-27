// Client HTTP de l'API MINEFLEET 360.
// Jeton d'accès gardé en mémoire uniquement (jamais localStorage) ; le jeton de rafraîchissement est un
// cookie httpOnly que le navigateur envoie seul à /api/v1/auth/refresh (ADR-003).
import type { components, paths } from "./schema";

export type Schemas = components["schemas"];

export const API_PREFIX = "/api/v1";

export interface ErrorBody {
  code: string;
  message_fr: string;
  details: unknown;
  request_id: string | null;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: unknown;
  readonly requestId: string | null;

  constructor(status: number, body: ErrorBody) {
    super(body.message_fr);
    this.status = status;
    this.code = body.code;
    this.details = body.details;
    this.requestId = body.request_id;
  }
}

let accessToken: string | null = null;
let refreshing: Promise<boolean> | null = null;
let onSessionLost: () => void = () => undefined;

export function setAccessToken(token: string | null): void {
  accessToken = token;
}

export function onSessionExpired(handler: () => void): void {
  onSessionLost = handler;
}

async function parseError(response: Response): Promise<ApiError> {
  try {
    return new ApiError(response.status, (await response.json()) as ErrorBody);
  } catch {
    return new ApiError(response.status, {
      code: "NETWORK_ERROR",
      message_fr: "Le serveur est injoignable ou a renvoyé une réponse inattendue.",
      details: null,
      request_id: null,
    });
  }
}

/** Renouvelle le jeton d'accès via le cookie ; une seule tentative en vol à la fois. */
export function refreshSession(): Promise<boolean> {
  refreshing ??= (async () => {
    try {
      const response = await fetch(`${API_PREFIX}/auth/refresh`, {
        method: "POST",
        credentials: "same-origin",
      });
      if (!response.ok) {
        accessToken = null;
        return false;
      }
      const body = (await response.json()) as Schemas["TokenResponse"];
      accessToken = body.access_token;
      return true;
    } catch {
      return false;
    } finally {
      refreshing = null;
    }
  })();
  return refreshing;
}

export interface RequestOptions {
  method?: "GET" | "POST" | "PATCH";
  body?: unknown;
  query?: Record<string, string | number | boolean | null | undefined>;
  ifMatch?: string | null;
}

export interface ApiResponse<T> {
  data: T;
  etag: string | null;
}

function buildUrl(path: string, query: RequestOptions["query"]): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== null && value !== undefined && value !== "") params.set(key, String(value));
  }
  const qs = params.toString();
  return `${API_PREFIX}${path}${qs ? `?${qs}` : ""}`;
}

export async function request<T>(path: string, options: RequestOptions = {}, retried = false): Promise<ApiResponse<T>> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  if (options.ifMatch) headers["If-Match"] = options.ifMatch;
  let response: Response;
  try {
    response = await fetch(buildUrl(path, options.query), {
      method: options.method ?? "GET",
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      credentials: "same-origin",
    });
  } catch {
    throw new ApiError(0, {
      code: "NETWORK_ERROR",
      message_fr: "Connexion au serveur impossible. Vérifiez le réseau puis réessayez.",
      details: null,
      request_id: null,
    });
  }
  if (response.status === 401 && !retried && !path.startsWith("/auth/")) {
    if (await refreshSession()) return request<T>(path, options, true);
    onSessionLost();
  }
  if (!response.ok) throw await parseError(response);
  const data = response.status === 204 ? (undefined as T) : ((await response.json()) as T);
  return { data, etag: response.headers.get("ETag") };
}

export async function get<T>(path: string, query?: RequestOptions["query"]): Promise<T> {
  return (await request<T>(path, { query })).data;
}

// --- Appels typés depuis le schéma OpenAPI (chemins, paramètres, corps, réponses) --------------------
// Un paramètre de requête inconnu (ex. `search` au lieu de `q`) est une erreur de compilation.

type Method = "get" | "post" | "patch";
export type ApiPath = keyof paths extends infer K ? (K extends `/api/v1${infer R}` ? R : never) : never;
type Operation<P extends ApiPath, M extends Method> = NonNullable<paths[`/api/v1${P}`][M]>;
type MethodsOf<P extends ApiPath> = {
  [M in Method]: paths[`/api/v1${P}`][M] extends undefined ? never : M;
}[Method];
type QueryOf<O> = O extends { parameters: { query?: infer Q } } ? NonNullable<Q> : never;
type PathOf<O> = O extends { parameters: { path: infer T } } ? T : never;
type BodyOf<O> = O extends { requestBody?: { content: { "application/json": infer B } } } ? B : never;
type Success<R> = R extends { 200: { content: { "application/json": infer J } } }
  ? J
  : R extends { 201: { content: { "application/json": infer J } } }
    ? J
    : undefined;
export type ResponseOf<P extends ApiPath, M extends Method> = Operation<P, M> extends { responses: infer R }
  ? Success<R>
  : never;

export interface CallOptions<O> {
  path?: PathOf<O>;
  query?: QueryOf<O>;
  body?: BodyOf<O>;
  ifMatch?: string | null;
}

/** Appel typé : `call("get", "/vehicles/{vehicle_id}", { path: { vehicle_id } })`. */
export function call<P extends ApiPath, M extends MethodsOf<P>>(
  method: M,
  template: P,
  options: CallOptions<Operation<P, M>> = {},
): Promise<ApiResponse<ResponseOf<P, M>>> {
  const params = (options.path ?? {}) as Record<string, string>;
  const path = template.replace(/\{(\w+)\}/g, (_, name: string) => encodeURIComponent(params[name] ?? ""));
  return request<ResponseOf<P, M>>(path, {
    method: method.toUpperCase() as RequestOptions["method"],
    query: options.query as RequestOptions["query"],
    body: options.body,
    ifMatch: options.ifMatch,
  });
}

/** Lecture typée renvoyant directement le corps. */
export async function read<P extends ApiPath>(
  template: P,
  options: CallOptions<Operation<P, "get">> = {},
): Promise<ResponseOf<P, "get">> {
  const response = await call<P, MethodsOf<P>>("get" as MethodsOf<P>, template, options as never);
  return response.data as ResponseOf<P, "get">;
}
