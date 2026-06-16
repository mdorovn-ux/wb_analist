const http = require("http");
const fs = require("fs");
const path = require("path");

const publicDir = path.join(__dirname, "public");
const port = process.env.PORT || 3000;

const contentTypes = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".js": "application/javascript; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".zip": "application/zip"
};

function safePath(urlPath) {
  const decoded = decodeURIComponent(urlPath.split("?")[0]);
  const normalized = path.normalize(decoded).replace(/^(\.\.[/\\])+/, "");
  const filePath = path.join(publicDir, normalized === "/" ? "index.html" : normalized);
  return filePath.startsWith(publicDir) ? filePath : path.join(publicDir, "index.html");
}

const server = http.createServer((req, res) => {
  const filePath = safePath(req.url || "/");
  fs.stat(filePath, (statError, stats) => {
    const resolvedPath = !statError && stats.isFile() ? filePath : path.join(publicDir, "index.html");
    const ext = path.extname(resolvedPath).toLowerCase();
    res.writeHead(200, {
      "Content-Type": contentTypes[ext] || "application/octet-stream",
      "Cache-Control": ext === ".zip" ? "public, max-age=3600" : "public, max-age=300"
    });
    fs.createReadStream(resolvedPath).pipe(res);
  });
});

server.listen(port, () => {
  console.log(`WB analyst landing is running on port ${port}`);
});
