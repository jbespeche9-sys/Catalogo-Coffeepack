import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PHOTO_ROOT =
  process.env.COFFEEPACK_PHOTO_ROOT ||
  "C:\\Users\\Juan Bautista\\OneDrive\\Escritorio\\COFFEEPACK\\IMAGENES COFFEPACK";
const PORT = Number(process.env.PORT || 4173);

const IMAGE_EXTENSIONS = new Set([
  ".jpg",
  ".jpeg",
  ".png",
  ".webp",
  ".avif",
  ".gif",
  ".bmp",
]);

const MIME_TYPES = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".png": "image/png",
  ".webp": "image/webp",
  ".avif": "image/avif",
  ".gif": "image/gif",
  ".bmp": "image/bmp",
  ".svg": "image/svg+xml",
};

let cachedProducts = null;
let cachedAt = 0;

function send(res, status, body, headers = {}) {
  res.writeHead(status, headers);
  res.end(body);
}

function normalizeText(value) {
  return value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
}

function cleanProductName(name) {
  return name
    .replace(/\s{2,}/g, " ")
    .trim();
}

function mergeKey(product) {
  return [product.type, product.material, product.name].map(normalizeText).join("::");
}

function neutralImageScore(fileName) {
  const name = normalizeText(fileName);
  let score = 0;
  const preferred = ["principal", "frente", "producto", "pack", "blanco", "kraft"];
  const avoided = ["detalle", "medida", "medidas", "lateral", "dorso", "logo", "ambient", "uso", "zoom", "copia"];
  for (const word of preferred) {
    if (name.includes(word)) score -= 8;
  }
  for (const word of avoided) {
    if (name.includes(word)) score += 10;
  }
  if (/(\b|_|\-)1(\b|_|\-|\.)/.test(name)) score -= 3;
  return score;
}

function walkProducts(dir, products = []) {
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  const imageFiles = entries
    .filter((entry) => entry.isFile() && IMAGE_EXTENSIONS.has(path.extname(entry.name).toLowerCase()))
    .map((entry) => entry.name)
    .sort((a, b) => neutralImageScore(a) - neutralImageScore(b) || a.localeCompare(b, "es"));

  if (imageFiles.length) {
    const relativeDir = path.relative(PHOTO_ROOT, dir);
    const parts = relativeDir.split(path.sep).filter(Boolean);
    const personalized = parts[0]?.toUpperCase() === "PERSONALIZADO";
    const type = personalized ? parts[1] || "Personalizado" : parts[0] || "Productos";
    const productName = cleanProductName(parts.at(-1) || "Producto");
    let material = "Sin material";

    if (personalized && parts.length >= 4) {
      material = parts[2];
    } else if (!personalized && parts.length >= 3) {
      material = parts[1];
    }

    products.push({
      id: Buffer.from(relativeDir, "utf8").toString("base64url"),
      name: productName,
      type,
      material,
      personalized,
      path: parts.join(" / "),
      images: imageFiles.map((file) => path.join(relativeDir, file)),
    });
  }

  for (const entry of entries) {
    if (entry.isDirectory()) walkProducts(path.join(dir, entry.name), products);
  }
  return products;
}

function mergePersonalizableProducts(products) {
  const byProduct = new Map();

  for (const product of products) {
    const key = mergeKey(product);
    const existing = byProduct.get(key);

    if (!existing) {
      byProduct.set(key, {
        ...product,
        personalizable: product.personalized,
        sources: product.personalized ? ["personalizado"] : ["linea"],
      });
      continue;
    }

    existing.personalizable = existing.personalizable || product.personalized;
    existing.personalized = existing.personalized || product.personalized;
    existing.sources.push(product.personalized ? "personalizado" : "linea");

    const nextImages = product.images.filter((image) => !existing.images.includes(image));
    if (product.personalized) {
      existing.images.push(...nextImages);
    } else {
      existing.images.unshift(...nextImages);
      existing.id = product.id;
      existing.path = product.path;
    }
  }

  return [...byProduct.values()].map((product) => ({
    ...product,
    personalized: product.personalizable,
    sources: [...new Set(product.sources)],
  }));
}

function getProducts() {
  const now = Date.now();
  if (cachedProducts && now - cachedAt < 10_000) return cachedProducts;

  const products = mergePersonalizableProducts(walkProducts(PHOTO_ROOT)).sort((a, b) => {
    return (
      a.type.localeCompare(b.type, "es") ||
      a.material.localeCompare(b.material, "es") ||
      a.name.localeCompare(b.name, "es")
    );
  });
  cachedProducts = products;
  cachedAt = now;
  return products;
}

function safePhotoPath(relativePhotoPath) {
  const decoded = decodeURIComponent(relativePhotoPath || "");
  const absolute = path.resolve(PHOTO_ROOT, decoded);
  const root = path.resolve(PHOTO_ROOT);
  if (!absolute.startsWith(root + path.sep)) return null;
  return absolute;
}

function serveStatic(req, res) {
  const url = new URL(req.url, `http://${req.headers.host}`);
  const pathname = url.pathname === "/" ? "/index.html" : url.pathname;
  const absolute = path.resolve(__dirname, "." + pathname);
  if (!absolute.startsWith(__dirname + path.sep)) {
    send(res, 403, "Forbidden");
    return;
  }
  if (!fs.existsSync(absolute) || !fs.statSync(absolute).isFile()) {
    send(res, 404, "Not found");
    return;
  }
  const ext = path.extname(absolute).toLowerCase();
  res.writeHead(200, { "Content-Type": MIME_TYPES[ext] || "application/octet-stream" });
  fs.createReadStream(absolute).pipe(res);
}

const server = http.createServer((req, res) => {
  try {
    const url = new URL(req.url, `http://${req.headers.host}`);
    if (url.pathname === "/api/products") {
      send(res, 200, JSON.stringify({ products: getProducts() }), {
        "Content-Type": "application/json; charset=utf-8",
        "Cache-Control": "no-store",
      });
      return;
    }

    if (url.pathname === "/photo") {
      const absolute = safePhotoPath(url.searchParams.get("path"));
      if (!absolute || !fs.existsSync(absolute)) {
        send(res, 404, "Image not found");
        return;
      }
      const ext = path.extname(absolute).toLowerCase();
      res.writeHead(200, {
        "Content-Type": MIME_TYPES[ext] || "application/octet-stream",
        "Cache-Control": "public, max-age=3600",
      });
      fs.createReadStream(absolute).pipe(res);
      return;
    }

    serveStatic(req, res);
  } catch (error) {
    console.error(error);
    send(res, 500, "Server error");
  }
});

server.listen(PORT, () => {
  console.log(`Catalogo Coffeepack listo en http://localhost:${PORT}`);
  console.log(`Fotos: ${PHOTO_ROOT}`);
});
