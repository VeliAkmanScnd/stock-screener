import http from "node:http";
import { handleScreener, warmScreener } from "./screener-api.mjs";

const port = Number(process.env.CALC_API_PORT || process.env.PORT || 4318);
const host = process.env.CALC_API_HOST || "127.0.0.1";

const server = http.createServer({ keepAlive: false }, (req, res) => {
  res.setHeader("Connection", "close");
  if (req.method !== "GET" && req.method !== "HEAD") {
    res.writeHead(405, { "Content-Type": "text/plain; charset=utf-8" });
    res.end("Method Not Allowed");
    return;
  }
  const urlPath = (req.url || "/").split("?")[0];
  if (urlPath === "/health") {
    res.writeHead(200, { "Content-Type": "text/plain; charset=utf-8" });
    res.end("ok");
    return;
  }
  if (urlPath === "/api/screener") {
    handleScreener(req, res);
    return;
  }
  res.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" });
  res.end("Not Found");
});

server.listen(port, host, () => {
  console.log(`Calc API http://${host}:${port}`);
  warmScreener();
});
