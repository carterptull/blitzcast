import nextConfig from "../../../next.config";

async function routeHeaders() {
  const routes = await nextConfig.headers!();
  const all = routes.find((r) => r.source === "/:path*");
  expect(all).toBeDefined();
  return new Map(all!.headers.map((h) => [h.key, h.value]));
}

describe("security headers", () => {
  it("keeps frame-ancestors first and adds the hardening directives", async () => {
    const csp = (await routeHeaders()).get("Content-Security-Policy")!;
    const [frameAncestors, ...rest] = csp.split("; ");
    expect(frameAncestors).toMatch(
      /^frame-ancestors 'self' https:\/\/[a-z0-9.-]+ https:\/\/www\.[a-z0-9.-]+$/,
    );
    expect(rest).toEqual(["base-uri 'self'", "object-src 'none'", "form-action 'self'"]);
  });

  it("does not add default-src, script-src or img-src", async () => {
    const csp = (await routeHeaders()).get("Content-Security-Policy")!;
    expect(csp).not.toMatch(/default-src|script-src|img-src/);
  });

  it("sets the defense-in-depth headers", async () => {
    const headers = await routeHeaders();
    expect(headers.get("X-Content-Type-Options")).toBe("nosniff");
    expect(headers.get("Referrer-Policy")).toBe(
      "strict-origin-when-cross-origin",
    );
    expect(headers.get("Permissions-Policy")).toBe(
      "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
    );
  });

  it("disables the X-Powered-By header", () => {
    expect(nextConfig.poweredByHeader).toBe(false);
  });
});
