export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    // 1. Try serving static assets directly from edge binding if available
    if (env && env.ASSETS) {
      try {
        const assetResponse = await env.ASSETS.fetch(request);
        if (assetResponse && assetResponse.status !== 404) {
          return assetResponse;
        }
      } catch (err) {
        // Fall back to backend origin
      }
    }

    // 2. Reverse proxy to Render backend
    const BACKEND_ORIGIN = "https://scout-ai-1-0gs9.onrender.com";
    const targetUrl = new URL(url.pathname + url.search, BACKEND_ORIGIN);

    const headers = new Headers(request.headers);
    headers.set("X-Forwarded-Host", url.host);
    headers.set("X-Forwarded-Proto", url.protocol.replace(":", ""));

    const proxyRequest = new Request(targetUrl, {
      method: request.method,
      headers: headers,
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
      return new Response(`Gateway error connecting to Render backend: ${err.message}`, { status: 502 });
    }
  }
};
