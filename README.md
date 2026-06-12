# Catalogo Coffeepack

Catalogo web interactivo para productos Coffeepack.

## Uso local

1. Instalar Node.js.
2. Generar el catalogo estatico:

```bash
python scripts/build_catalog.py
```

3. Ejecutar:

```bash
npm start
```

4. Abrir `http://localhost:4173`.

Por defecto el servidor lee las fotos desde:

```text
C:\Users\Juan Bautista\OneDrive\Escritorio\COFFEEPACK\IMAGENES COFFEPACK
```

Tambien se puede usar otra carpeta configurando `COFFEEPACK_PHOTO_ROOT` antes de generar el catalogo.

```bash
COFFEEPACK_PHOTO_ROOT="C:\ruta\a\imagenes" npm start
```
