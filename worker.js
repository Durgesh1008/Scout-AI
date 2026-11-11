const WAKING_UP_HTML = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Scout AI — Starting Up</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: #07090e;
      color: #e6edf3;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      display: flex;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
      padding: 20px;
    }
    .card {
      background: #0d1117;
      border: 1px solid #30363d;
      border-radius: 16px;
      padding: 40px 32px;
      max-width: 480px;
      width: 100%;
      text-align: center;
      box-shadow: 0 20px 40px rgba(0, 0, 0, 0.6);
    }
    .badge {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      background: rgba(56, 189, 248, 0.1);
      color: #38bdf8;
      border: 1px solid rgba(56, 189, 248, 0.25);
      border-radius: 999px;
      padding: 6px 14px;
      font-size: 13px;
      font-weight: 600;
      margin-bottom: 24px;
    }
    .pulse-dot {
      width: 8px;
      height: 8px;
      background: #38bdf8;
      border-radius: 50%;
      animation: pulse 1.5s infinite;
    }
    @keyframes pulse {
      0% { opacity: 0.3; transform: scale(0.9); }
      50% { opacity: 1; transform: scale(1.2); }
      100% { opacity: 0.3; transform: scale(0.9); }
    }
    h1 {
      font-size: 24px;
      font-weight: 700;
      color: #ffffff;
      margin-bottom: 12px;
      letter-spacing: -0.5px;
    }
    p {
      color: #8b949e;
      font-size: 14.5px;
      line-height: 1.6;
      margin-bottom: 24px;
    }
    .progress-bar-bg {
      background: #161b22;
      border: 1px solid #21262d;
      border-radius: 12px;
      height: 8px;
      overflow: hidden;
      margin-bottom: 16px;
    }
    .progress-bar-fill {
      background: linear-gradient(90deg, #38bdf8, #818cf8);
      height: 100%;
      width: 15%;
      border-radius: 12px;
      animation: loadingAnim 35s linear forwards;
    }
    @keyframes loadingAnim {
      0% { width: 10%; }
      30% { width: 45%; }
      70% { width: 80%; }
      95% { width: 95%; }
      100% { width: 98%; }
    }
    .status-text {
      font-size: 12.5px;
      color: #58a6ff;
      font-family: monospace;
      margin-bottom: 24px;
    }
    .btn {
      display: inline-block;
      background: #238636;
      color: #ffffff;
      border: 1px solid rgba(240, 246, 252, 0.1);
      padding: 10px 22px;
      border-radius: 8px;
      font-size: 14px;
      font-weight: 600;
      text-decoration: none;
      cursor: pointer;
      transition: background 0.2s;
    }
    .btn:hover { background: #2ea043; }
  </style>
</head>
<body>
  <div class="card">
    <div class="badge">
      <span class="pulse-dot"></span>
      Render Cloud Instance Waking Up
    </div>
    <h1>⚡ Scout AI is Starting Up</h1>
    <p>
      Your server is hosted on Render's free tier, which sleeps when idle. We've signaled the server — your autonomous studio is warming up now.
    </p>
    <div class="progress-bar-bg">
      <div class="progress-bar-fill"></div>
    </div>
    <div class="status-text" id="statusMsg">Connecting to server...</div>
    <button class="btn" onclick="checkNow()">Refresh Now</button>
  </div>
  <script>
    let attempts = 1;
    async function checkServer() {
      const msg = document.getElementById("statusMsg");
      try {
        const res = await fetch("/api/health", { cache: "no-store" });
        if (res.ok) {
          msg.innerText = "Connected! Loading Scout AI...";
          window.location.reload();
          return;
        }
      } catch (e) {}
      attempts++;
      msg.innerText = "Connecting to agent... (attempt " + attempts + ")";
      setTimeout(checkServer, 3000);
    }
    function checkNow() {
      document.getElementById("statusMsg").innerText = "Checking...";
      checkServer();
    }
    setTimeout(checkServer, 3000);
  </script>
</body>
</html>`;

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
      let response = await fetch(proxyRequest);

      // Auto-retry once after a short wait if Render is waking up
      if ((response.status === 502 || response.status === 503) && ["GET", "HEAD"].includes(request.method)) {
        await new Promise((resolve) => setTimeout(resolve, 2500));
        response = await fetch(
          new Request(targetUrl, {
            method: request.method,
            headers: forwardHeaders,
            redirect: "manual"
          })
        );
      }

      // If still 502/503 (Render is actively spinning up from sleep)
      if (response.status === 502 || response.status === 503) {
        const acceptHeader = request.headers.get("accept") || "";
        const isHtmlRequest = !url.pathname.startsWith("/api/") || acceptHeader.includes("text/html");

        if (isHtmlRequest) {
          return new Response(WAKING_UP_HTML, {
            status: 200,
            headers: {
              "Content-Type": "text/html; charset=utf-8",
              "Cache-Control": "no-store, no-cache, must-revalidate"
            }
          });
        }

        return new Response(
          JSON.stringify({
            status: "waking_up",
            message: "Render server is booting up. Please retry in a few seconds.",
            retry_after: 5
          }),
          {
            status: 503,
            headers: {
              "Content-Type": "application/json",
              "Retry-After": "5",
              "Cache-Control": "no-store"
            }
          }
        );
      }

      return new Response(response.body, {
        status: response.status,
        statusText: response.statusText,
        headers: response.headers
      });
    } catch (err) {
      const acceptHeader = request.headers.get("accept") || "";
      const isHtmlRequest = !url.pathname.startsWith("/api/") || acceptHeader.includes("text/html");

      if (isHtmlRequest) {
        return new Response(WAKING_UP_HTML, {
          status: 200,
          headers: {
            "Content-Type": "text/html; charset=utf-8",
            "Cache-Control": "no-store, no-cache, must-revalidate"
          }
        });
      }

      return new Response(
        JSON.stringify({
          detail: `Gateway error connecting to backend: ${err.message}`
        }),
        {
          status: 502,
          headers: { "Content-Type": "application/json" }
        }
      );
    }
  }
};
