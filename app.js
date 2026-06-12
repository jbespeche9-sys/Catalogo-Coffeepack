const state = {
  products: [],
  type: "all",
  material: "all",
  personalized: "all",
  search: "",
  sort: "name",
  slideById: new Map(),
};

const els = {
  shownProducts: document.querySelector("#shownProducts"),
  searchInput: document.querySelector("#searchInput"),
  typeSelect: document.querySelector("#typeSelect"),
  materialSelect: document.querySelector("#materialSelect"),
  personalizedSelect: document.querySelector("#personalizedSelect"),
  productsGrid: document.querySelector("#productsGrid"),
  emptyState: document.querySelector("#emptyState"),
  clearFilters: document.querySelector("#clearFilters"),
  sortSelect: document.querySelector("#sortSelect"),
};

function normalize(value) {
  return value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
}

function imageUrl(imagePath) {
  if (/^(https?:)?\/\//.test(imagePath) || imagePath.startsWith("assets/") || imagePath.startsWith("/assets/")) {
    return imagePath;
  }
  return `/photo?path=${encodeURIComponent(imagePath)}`;
}

function uniqueValues(key) {
  return [...new Set(state.products.map((product) => product[key]))].sort((a, b) => a.localeCompare(b, "es"));
}

function makeOption(label, value) {
  const option = document.createElement("option");
  option.value = value;
  option.textContent = label;
  return option;
}

function renderFilters() {
  els.typeSelect.replaceChildren(makeOption("Todos", "all"), ...uniqueValues("type").map((type) => makeOption(type, type)));
  els.typeSelect.value = state.type;

  const materials = uniqueValues("material").filter((material) => {
    return state.type === "all" || state.products.some((product) => product.type === state.type && product.material === material);
  });

  els.materialSelect.replaceChildren(makeOption("Todos", "all"), ...materials.map((material) => makeOption(material, material)));
  els.materialSelect.value = materials.includes(state.material) ? state.material : "all";
  els.personalizedSelect.value = state.personalized;
}

function getFilteredProducts() {
  const query = normalize(state.search.trim());
  return state.products
    .filter((product) => state.type === "all" || product.type === state.type)
    .filter((product) => state.material === "all" || product.material === state.material)
    .filter((product) => {
      if (state.personalized === "yes") return product.personalized;
      if (state.personalized === "no") return !product.personalized;
      return true;
    })
    .filter((product) => {
      if (!query) return true;
      return normalize(`${product.name} ${product.type} ${product.material} ${product.path}`).includes(query);
    })
    .sort((a, b) => {
      if (state.sort === "type") return a.type.localeCompare(b.type, "es") || a.name.localeCompare(b.name, "es");
      if (state.sort === "material") return a.material.localeCompare(b.material, "es") || a.name.localeCompare(b.name, "es");
      return a.name.localeCompare(b.name, "es");
    });
}

function renderProduct(product) {
  const card = document.createElement("article");
  card.className = "product-card";
  card.dataset.id = product.id;

  const currentIndex = state.slideById.get(product.id) || 0;
  const imagePath = product.images[currentIndex] || product.images[0];
  const hasCarousel = product.images.length > 1;

  card.innerHTML = `
    <div class="image-stage">
      <img src="${imageUrl(imagePath)}" alt="${product.name}" loading="lazy" />
      <div class="badge-row">
        ${product.personalized ? '<span class="badge">Personalizable</span>' : ""}
        ${hasCarousel ? `<span class="photo-count">${currentIndex + 1}/${product.images.length}</span>` : ""}
      </div>
      ${
        hasCarousel
          ? `<div class="carousel-controls">
              <button class="carousel-button" type="button" data-dir="-1" aria-label="Foto anterior">‹</button>
              <button class="carousel-button" type="button" data-dir="1" aria-label="Foto siguiente">›</button>
            </div>`
          : ""
      }
    </div>
    <div class="product-info">
      <h3>${product.name}</h3>
      <span class="product-chip">${product.material}</span>
      <p class="product-path">${product.type}</p>
    </div>
  `;

  card.querySelectorAll("[data-dir]").forEach((button) => {
    button.addEventListener("click", () => {
      const direction = Number(button.dataset.dir);
      const next = (currentIndex + direction + product.images.length) % product.images.length;
      state.slideById.set(product.id, next);
      renderProducts();
    });
  });

  return card;
}

function renderProducts() {
  const filtered = getFilteredProducts();
  els.shownProducts.textContent = `Mostrando ${filtered.length}`;
  els.emptyState.hidden = filtered.length !== 0;
  els.productsGrid.replaceChildren(...filtered.map(renderProduct));
}

function render() {
  renderFilters();
  renderProducts();
}

async function init() {
  let response = await fetch("assets/catalog.json");
  if (!response.ok) {
    response = await fetch("/api/products");
  }
  const { products } = await response.json();
  state.products = products;

  els.searchInput.addEventListener("input", (event) => {
    state.search = event.target.value;
    renderProducts();
  });

  els.sortSelect.addEventListener("change", (event) => {
    state.sort = event.target.value;
    renderProducts();
  });

  els.clearFilters.addEventListener("click", () => {
    state.type = "all";
    state.material = "all";
    state.personalized = "all";
    state.search = "";
    state.sort = "name";
    els.searchInput.value = "";
    els.sortSelect.value = "name";
    render();
  });

  els.typeSelect.addEventListener("change", (event) => {
    state.type = event.target.value;
    state.material = "all";
    render();
  });

  els.materialSelect.addEventListener("change", (event) => {
    state.material = event.target.value;
    renderProducts();
  });

  els.personalizedSelect.addEventListener("change", (event) => {
    state.personalized = event.target.value;
    renderProducts();
  });

  render();
}

init().catch((error) => {
  console.error(error);
  els.productsGrid.innerHTML = '<div class="empty-state"><h3>No se pudo cargar el catalogo</h3><p>Revisá que la carpeta de fotos esté disponible.</p></div>';
});
