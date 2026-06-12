import base64
import json
import os
import re
import shutil
import unicodedata
from pathlib import Path

from PIL import Image, ImageOps

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PHOTO_ROOT = Path(
    os.environ.get(
        "COFFEEPACK_PHOTO_ROOT",
        r"C:\Users\Juan Bautista\OneDrive\Escritorio\COFFEEPACK\IMAGENES COFFEPACK",
    )
)
OUTPUT_ROOT = PROJECT_ROOT / "assets" / "products"
CATALOG_PATH = PROJECT_ROOT / "assets" / "catalog.json"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".avif", ".gif", ".bmp"}


def normalize_text(value):
    value = unicodedata.normalize("NFD", value)
    value = "".join(ch for ch in value if unicodedata.category(ch) != "Mn")
    return value.lower()


def clean_product_name(name):
    return re.sub(r"\s{2,}", " ", name).strip()


def slugify(value):
    slug = re.sub(r"[^a-z0-9]+", "-", normalize_text(value)).strip("-")
    return slug[:90] or "producto"


def merge_key(product):
    return "::".join(normalize_text(product[key]) for key in ("type", "material", "name"))


def neutral_image_score(file_name):
    name = normalize_text(file_name)
    score = 0
    preferred = ["principal", "frente", "producto", "pack", "blanco", "kraft"]
    avoided = ["detalle", "medida", "medidas", "lateral", "dorso", "logo", "ambient", "uso", "zoom", "copia"]
    for word in preferred:
        if word in name:
            score -= 8
    for word in avoided:
        if word in name:
            score += 10
    if re.search(r"(\b|_|-)1(\b|_|-|\.)", name):
        score -= 3
    return score


def walk_products(root):
    products = []
    for dirpath, _, filenames in os.walk(root):
        image_files = sorted(
            [name for name in filenames if Path(name).suffix.lower() in IMAGE_EXTENSIONS],
            key=lambda name: (neutral_image_score(name), name.lower()),
        )
        if not image_files:
            continue

        relative_dir = Path(dirpath).relative_to(root)
        parts = relative_dir.parts
        personalized = bool(parts and parts[0].upper() == "PERSONALIZADO")
        product_type = parts[1] if personalized and len(parts) > 1 else parts[0] if parts else "Productos"
        product_name = clean_product_name(parts[-1] if parts else "Producto")
        material = "Sin material"

        if personalized and len(parts) >= 4:
            material = parts[2]
        elif not personalized and len(parts) >= 3:
            material = parts[1]

        encoded_id = base64.urlsafe_b64encode(str(relative_dir).encode("utf-8")).decode("ascii").rstrip("=")
        products.append(
            {
                "id": encoded_id,
                "name": product_name,
                "type": product_type,
                "material": material,
                "personalized": personalized,
                "path": " / ".join(parts),
                "sourceImages": [str(Path(dirpath) / file_name) for file_name in image_files],
            }
        )
    return products


def merge_personalizable_products(products):
    by_product = {}
    for product in products:
        key = merge_key(product)
        existing = by_product.get(key)
        if existing is None:
            by_product[key] = {
                **product,
                "personalizable": product["personalized"],
                "sources": ["personalizado" if product["personalized"] else "linea"],
            }
            continue

        existing["personalizable"] = existing["personalizable"] or product["personalized"]
        existing["personalized"] = existing["personalized"] or product["personalized"]
        existing["sources"].append("personalizado" if product["personalized"] else "linea")

        next_images = [image for image in product["sourceImages"] if image not in existing["sourceImages"]]
        if product["personalized"]:
            existing["sourceImages"].extend(next_images)
        else:
            existing["sourceImages"] = next_images + existing["sourceImages"]
            existing["id"] = product["id"]
            existing["path"] = product["path"]

    merged = []
    for product in by_product.values():
        product["personalized"] = product["personalizable"]
        product["sources"] = list(dict.fromkeys(product["sources"]))
        merged.append(product)
    return merged


def optimize_image(source, destination):
    with Image.open(source) as image:
        image = ImageOps.exif_transpose(image).convert("RGB")
        image.thumbnail((1100, 1100), Image.Resampling.LANCZOS)
        image.save(destination, "WEBP", quality=78, method=6)


def main():
    if not PHOTO_ROOT.exists():
        raise FileNotFoundError(f"No existe la carpeta de fotos: {PHOTO_ROOT}")

    shutil.rmtree(OUTPUT_ROOT, ignore_errors=True)
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    products = merge_personalizable_products(walk_products(PHOTO_ROOT))
    products.sort(key=lambda product: (product["type"].lower(), product["material"].lower(), product["name"].lower()))

    for product_index, product in enumerate(products, start=1):
        product_slug = f"{product_index:03d}-{slugify(product['name'])}"
        product_dir = OUTPUT_ROOT / product_slug
        product_dir.mkdir(parents=True, exist_ok=True)

        images = []
        for image_index, source in enumerate(product["sourceImages"], start=1):
            destination = product_dir / f"{image_index:02d}.webp"
            optimize_image(source, destination)
            images.append(f"assets/products/{product_slug}/{destination.name}")

        product["images"] = images
        del product["sourceImages"]

    CATALOG_PATH.write_text(json.dumps({"products": products}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Catalogo generado: {len(products)} productos")
    print(f"Salida: {CATALOG_PATH}")


if __name__ == "__main__":
    main()
