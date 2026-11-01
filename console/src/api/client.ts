/** The CAVE API, from the browser. Errors carry the server's own words, ready to show. */

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string,
  ) {
    super(detail);
  }
}

const FALLBACK = "Something went wrong. Try again.";
const NO_REDIRECT = ["/login", "/setup", "/enroll"];

/** After a session ends: a kiosk screen signs back in with its key on /enroll; people get the sign-in page. */
export function signInAgain(): void {
  let screen: string | null = null;
  try {
    screen = localStorage.getItem("cave-screen-id"); // set by /enroll on the tablet
  } catch {
    // storage blocked: treat it as a person's browser
  }
  location.assign(screen ? "/enroll" : `/login?next=${encodeURIComponent(location.pathname + location.search)}`);
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const response = await fetch(`/api/v1${path}`, {
    method,
    credentials: "same-origin",
    headers: body === undefined ? {} : { "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (response.status === 204) return undefined as T;
  const data: unknown = await response.json().catch(() => undefined);
  if (!response.ok) {
    const detail =
      data && typeof data === "object" && "detail" in data && typeof data.detail === "string" ? data.detail : FALLBACK;
    if (response.status === 401 && !NO_REDIRECT.includes(location.pathname)) signInAgain();
    throw new ApiError(response.status, detail);
  }
  return data as T;
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, body ?? {}),
  put: <T>(path: string, body: unknown) => request<T>("PUT", path, body),
  patch: <T>(path: string, body: unknown) => request<T>("PATCH", path, body),
  del: <T = void>(path: string) => request<T>("DELETE", path),
};

export function message(error: unknown): string {
  return error instanceof ApiError ? error.detail : FALLBACK;
}
