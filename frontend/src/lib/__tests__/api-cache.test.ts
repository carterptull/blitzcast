/** Live-path caching: reads go through unstable_cache keyed by a 5-minute window. */

const FIVE_MIN = 5 * 60 * 1000;

const unstableCache = jest.fn();

jest.mock("next/cache", () => ({
  unstable_cache: (...args: unknown[]) => unstableCache(...args),
}));

async function loadApi() {
  jest.resetModules();
  delete process.env.NEXT_PUBLIC_USE_MOCK;
  return import("../api");
}

function jsonResponse(body: unknown, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => body } as Response;
}

describe("API client freshness cache", () => {
  const originalFetch = global.fetch;
  let fetchMock: jest.Mock;

  beforeEach(() => {
    unstableCache.mockImplementation((fn: (...a: unknown[]) => unknown) => fn);
    fetchMock = jest.fn().mockResolvedValue(jsonResponse([]));
    global.fetch = fetchMock as unknown as typeof fetch;
  });

  afterEach(() => {
    global.fetch = originalFetch;
    jest.restoreAllMocks();
  });

  test("live reads go through unstable_cache with path, window and revalidate 30", async () => {
    const now = 7 * FIVE_MIN + 1234;
    jest.spyOn(Date, "now").mockReturnValue(now);
    const { getTeams } = await loadApi();

    await getTeams("NFL");

    expect(unstableCache).toHaveBeenCalledTimes(1);
    const [, keyParts, options] = unstableCache.mock.calls[0];
    expect(keyParts).toEqual(["api", "/api/teams?sport=NFL", "7"]);
    expect(options).toEqual({ revalidate: 30 });
  });

  test("the inner fetch is no-store so unstable_cache owns caching", async () => {
    const { getTeams } = await loadApi();

    await getTeams("NFL");

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://localhost:8000/api/teams?sport=NFL");
    expect(init).toEqual({ cache: "no-store" });
  });

  test("different 5-minute windows give different key parts", async () => {
    const nowSpy = jest.spyOn(Date, "now");
    const { getTeams } = await loadApi();

    nowSpy.mockReturnValue(3 * FIVE_MIN);
    await getTeams("NFL");
    nowSpy.mockReturnValue(4 * FIVE_MIN - 1);
    await getTeams("NFL");
    nowSpy.mockReturnValue(4 * FIVE_MIN);
    await getTeams("NFL");

    const keys = unstableCache.mock.calls.map((c) => c[1]);
    expect(keys[0]).toEqual(keys[1]);
    expect(keys[2]).not.toEqual(keys[1]);
    expect(keys[2][2]).toBe("4");
  });

  test("a 404 maps to NotFoundError", async () => {
    fetchMock.mockResolvedValue(jsonResponse({}, 404));
    const { getMatchup, NotFoundError } = await loadApi();

    await expect(getMatchup("2026_01_a_b")).rejects.toBeInstanceOf(NotFoundError);
  });

  test("a fetch rejection maps to ApiUnreachableError", async () => {
    fetchMock.mockRejectedValue(new TypeError("fetch failed"));
    const { getTeams, ApiUnreachableError } = await loadApi();

    await expect(getTeams("NFL")).rejects.toBeInstanceOf(ApiUnreachableError);
  });

  test("another non-OK status maps to ApiUnreachableError with the status", async () => {
    fetchMock.mockResolvedValue(jsonResponse({}, 503));
    const { getTeams, ApiUnreachableError } = await loadApi();

    const err = await getTeams("NFL").catch((e) => e);
    expect(err).toBeInstanceOf(ApiUnreachableError);
    expect(err.message).toContain("503");
  });
});
