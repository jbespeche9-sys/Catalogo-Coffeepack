import base64
import hashlib
import json
import os
import re
import shutil
import unicodedata
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps
from PIL import ImageDraw, ImageFilter

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
UNIFIED_BACKGROUND = (239, 237, 232)


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
        has_child_dirs = any(entry.is_dir() for entry in Path(dirpath).iterdir())
        if not image_files and has_child_dirs:
            continue

        relative_dir = Path(dirpath).relative_to(root)
        parts = relative_dir.parts
        if not parts:
            continue
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
                "personalized": is_personalizable_product(product_type, product_name, personalized),
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


def normalize_simple_background(image, force=False):
    width, height = image.size
    preview_max = 360
    scale = min(1, preview_max / max(width, height))
    preview_size = (max(1, int(width * scale)), max(1, int(height * scale)))
    preview = image.resize(preview_size, Image.Resampling.BILINEAR)
    arr = np.asarray(preview)
    preview_height, preview_width = arr.shape[:2]
    edge = max(6, min(width, height) // 40)
    edge = max(3, int(edge * scale))
    border = np.concatenate(
        [
            arr[:edge, :, :].reshape(-1, 3),
            arr[-edge:, :, :].reshape(-1, 3),
            arr[:, :edge, :].reshape(-1, 3),
            arr[:, -edge:, :].reshape(-1, 3),
        ],
        axis=0,
    )
    background = np.median(border, axis=0)
    distances = np.linalg.norm(border.astype(np.int16) - background.astype(np.int16), axis=1)

    # Si el borde no es bastante uniforme, suele ser una foto ambientada o con escena.
    if not force and (np.percentile(distances, 90) > 48 or np.percentile(distances, 98) > 86):
        return image, False

    fill_color = (255, 0, 255)
    flood = preview.copy()
    threshold_limit = 82 if force else 56
    threshold = int(max(22, min(threshold_limit, np.percentile(distances, 90) + 24)))
    seeds = [
        (0, 0),
        (preview_width - 1, 0),
        (0, preview_height - 1),
        (preview_width - 1, preview_height - 1),
        (preview_width // 2, 0),
        (preview_width // 2, preview_height - 1),
        (0, preview_height // 2),
        (preview_width - 1, preview_height // 2),
    ]

    for seed in seeds:
        ImageDraw.floodfill(flood, seed, fill_color, thresh=threshold)

    mask_arr = np.all(np.asarray(flood) == fill_color, axis=2).astype("uint8") * 255
    coverage = mask_arr.mean() / 255
    if not force and (coverage < 0.18 or coverage > 0.92):
        return image, False
    if force and (coverage < 0.08 or coverage > 0.995):
        return image, False

    mask = Image.fromarray(mask_arr, mode="L")
    mask = mask.resize(image.size, Image.Resampling.BILINEAR)
    mask = mask.filter(ImageFilter.GaussianBlur(1.2))
    background_layer = Image.new("RGB", image.size, UNIFIED_BACKGROUND)
    return Image.composite(background_layer, image, mask), True


def optimize_image(source, destination, force_background=False):
    with Image.open(source) as image:
        image = ImageOps.exif_transpose(image).convert("RGB")
        image.thumbnail((1100, 1100), Image.Resampling.LANCZOS)
        image, background_changed = normalize_simple_background(image, force=force_background)
        image.save(destination, "WEBP", quality=78, method=6)
        return background_changed


def image_content_hash(source):
    with Image.open(source) as image:
        image = ImageOps.exif_transpose(image).convert("RGB")
        image.thumbnail((700, 700), Image.Resampling.LANCZOS)
        return hashlib.sha256(image.tobytes()).hexdigest()


def remove_duplicate_images(sources):
    seen = set()
    unique_sources = []
    for source in sources:
        digest = image_content_hash(source)
        if digest in seen:
            continue
        seen.add(digest)
        unique_sources.append(source)
    return unique_sources


def should_preserve_context(source):
    name = normalize_text(Path(source).name)
    context_markers = [
        "producto-maestro",
        "ambient",
        "ambiente",
        "context",
        "lifestyle",
        "uso",
        "escena",
    ]
    return any(marker in name for marker in context_markers)


def should_force_background(source):
    normalized_source = normalize_text(str(source))
    name = normalize_text(Path(source).name)
    return "potes para salsas" in normalized_source and "bamboo" in normalized_source and "producto-maestro" not in name


def prioritize_product_images(product):
    if product["type"] == "Potes para salsas" and product["material"] == "Bamboo":
        product["sourceImages"].sort(key=lambda source: 1 if should_preserve_context(source) else 0)


def is_personalizable_product(product_type, product_name, personalized):
    normalized_name = normalize_text(product_name)
    if "tapa vasos polipapel" in normalized_name or "tapas vasos polipapel" in normalized_name:
        return False
    return personalized or product_type == "Portavasos"


def main():
    if not PHOTO_ROOT.exists():
        raise FileNotFoundError(f"No existe la carpeta de fotos: {PHOTO_ROOT}")

    shutil.rmtree(OUTPUT_ROOT, ignore_errors=True)
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    products = merge_personalizable_products(walk_products(PHOTO_ROOT))
    products.sort(key=lambda product: (product["type"].lower(), product["material"].lower(), product["name"].lower()))

    changed_backgrounds = 0
    skipped_backgrounds = 0

    for product_index, product in enumerate(products, start=1):
        product["sourceImages"] = remove_duplicate_images(product["sourceImages"])
        prioritize_product_images(product)
        product_slug = f"{product_index:03d}-{slugify(product['name'])}"
        product_dir = OUTPUT_ROOT / product_slug
        product_dir.mkdir(parents=True, exist_ok=True)

        images = []
        for image_index, source in enumerate(product["sourceImages"], start=1):
            destination = product_dir / f"{image_index:02d}.webp"
            if should_preserve_context(source):
                with Image.open(source) as image:
                    image = ImageOps.exif_transpose(image).convert("RGB")
                    image.thumbnail((1100, 1100), Image.Resampling.LANCZOS)
                    image.save(destination, "WEBP", quality=78, method=6)
                skipped_backgrounds += 1
            elif optimize_image(source, destination, force_background=should_force_background(source)):
                changed_backgrounds += 1
            else:
                skipped_backgrounds += 1
            images.append(f"assets/products/{product_slug}/{destination.name}")

        product["images"] = images
        del product["sourceImages"]

    CATALOG_PATH.write_text(json.dumps({"products": products}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Catalogo generado: {len(products)} productos")
    print(f"Fondos unificados: {changed_backgrounds}")
    print(f"Fondos conservados: {skipped_backgrounds}")
    print(f"Salida: {CATALOG_PATH}")


if __name__ == "__main__":
    main()
