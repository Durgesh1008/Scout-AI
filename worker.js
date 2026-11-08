export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    // 1. Only query static edge assets for GET/HEAD requests to actual static resources
    const isStaticAsset =
      ["GET", "HEAD"].includes(request.method) &&
      !url.pathname.startsWith("/api/") &&
      url.pathname !== "/" &&
      (url.pathname.startsWith("/static/") ||
        /\.(css|js|json|png|jpg|jpeg|gif|svg|ico|woff|woff2|ttf|eot)$/i.test(url.pathname));

    if (isStaticAsset && env && env.ASSETS) {
      try {
        let assetResponse = await env.ASSETS.fetch(request);
        if (assetResponse && assetResponse.ok) {
          return assetResponse;
        }

        // Try stripping '/static/' prefix if assets folder is mapped directly
        if (url.pathname.startsWith("/static/")) {
          const strippedUrl = new URL(request.url);
          strippedUrl.pathname = url.pathname.replace(/^\/static/, "");
          assetResponse = await env.ASSETS.fetch(new Request(strippedUrl, request));
          if (assetResponse && assetResponse.ok) {
            return assetResponse;
          }
        }
      } catch (err) {
        // Fall back to backend origin
      }
    }

    // 2. Reverse proxy all dynamic routes and API calls (including file uploads) to Render backend
    const BACKEND_HOST = "scout-ai-1-0gs9.onrender.com";
    const targetUrl = new URL(url.pathname + url.search, `https://${BACKEND_HOST}`);

    const forwardHeaders = new Headers(request.headers);
    forwardHeaders.set("Host", BACKEND_HOST);
    forwardHeaders.set("X-Forwarded-Host", url.host);
    forwardHeaders.set("X-Forwarded-Proto", "https");

    const proxyRequest = new Request(targetUrl, {
      method: request.method,
      headers: forwardHeaders,
      body: ["GET", "HEAD"].includes(request.method) ? undefined : request.body,
      redirect: "manual"
    });

    try {
      const response = await fetch(proxyRequest);
      return new Response(response.body, {
        status: response.status,
        statusText: response.statusText,
        headers: response.headers
      });
    } catch (err) {
      return new Response(
        JSON.stringify({ detail: `Gateway error connecting to backend: ${err.message}` }),
        {
          status: 502,
          headers: { "Content-Type": "application/json" }
        }
      );
    }
  }
};
