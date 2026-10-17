"use strict";

(function initializeStoreCategories() {
    const categoryNav = document.getElementById("categoryNav");
    const categoryGrid = document.getElementById("collectionGrid");
    const categoryFilter = document.getElementById("categoryFilter");
    if (!categoryNav || !categoryGrid || !categoryFilter) return;

    const fallbackImage = categoryGrid.querySelector(".category-card img")?.src || "";
    const seededCards = new Map(
        [...categoryGrid.querySelectorAll(".category-card")].map((card) => [
            card.querySelector("strong")?.textContent || "",
            {
                icon: card.querySelector(".category-icon")?.textContent || "✧",
                image: card.querySelector("img")?.src || fallbackImage
            }
        ])
    );
    const seededLinks = new Map(
        [...categoryNav.querySelectorAll(".category-link")].map((link) => [
            link.querySelector("span:nth-child(2)")?.textContent || "",
            link.querySelector(".list-icon")?.textContent || "✧"
        ])
    );
    const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (character) => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    })[character]);
    const displayName = (name) => name === "Bracelets" ? "Bracelets / Kadas" : name;
    let categories = [];
    let offset = 0;
    window.drawStoreCategoryTiles = drawCategoryTiles;
    window.drawCategoryTiles = () => {
        offset = categoryOffset;
        drawCategoryTiles();
    };

    function drawCategoryTiles() {
        if (!categories.length) {
            categoryGrid.innerHTML = "";
            return;
        }
        const count = Math.min(9, categories.length);
        const items = Array.from({ length: count }, (_, index) => categories[(offset + index) % categories.length]);
        categoryGrid.innerHTML = items.map((category, index) => `
            <a class="category-card" href="#shop" data-filter-category="${escapeHtml(category.name)}" style="animation:fadeUp .45s ${index * 45}ms both">
                <img loading="lazy" src="${escapeHtml(category.image)}" alt="${escapeHtml(category.name)} jewellery">
                <span class="category-caption"><span class="category-icon">${escapeHtml(category.icon)}</span><strong>${escapeHtml(category.name)}</strong><span class="category-arrow">→</span></span>
            </a>`).join("");
    }

    function renderCategoryControls(names, categoryIcons = {}) {
        const previousValue = categoryFilter.value;
        categories = names.map((name) => {
            const seed = seededCards.get(name);
            return {
                name,
                icon: categoryIcons[name] || seed?.icon || seededLinks.get(name) || "✧",
                image: seed?.image || fallbackImage
            };
        });
        offset = 0;
        categoryOffset = 0;
        categoryFilter.innerHTML = `<option value="All">All products</option>${categories.map((category) =>
            `<option value="${escapeHtml(category.name)}">${escapeHtml(displayName(category.name))}</option>`
        ).join("")}`;
        categoryFilter.value = names.includes(previousValue) ? previousValue : "All";
        if (categoryFilter.value !== previousValue) categoryFilter.dispatchEvent(new Event("change"));
        categoryNav.innerHTML = categories.map((category) => `
            <a class="category-link" href="#shop" data-filter-category="${escapeHtml(category.name)}">
                <span class="list-icon">${escapeHtml(category.icon)}</span><span>${escapeHtml(displayName(category.name))}</span><span class="arrow">→</span>
            </a>`).join("");

        const footer = document.getElementById("footerCategories");
        if (footer && !window.storeFooterSections) {
            footer.innerHTML = [
                `<a href="#shop" data-filter-category="All">${window.storeFooterIconMarkup("explore", { filter: "All", label: "Shop all" })}<span>Shop all</span></a>`,
                ...categories.map((category) =>
                    `<a href="#shop" data-filter-category="${escapeHtml(category.name)}">${window.storeFooterIconMarkup("explore", { filter: category.name, label: displayName(category.name) })}<span>${escapeHtml(displayName(category.name))}</span></a>`
                )
            ].join("");
        }
        const countLabel = document.querySelector(".category-list-head small");
        if (countLabel) countLabel.textContent = `${categories.length} styles`;
        const collectionNote = document.querySelector(".collection-note");
        if (collectionNote) {
            collectionNote.innerHTML = `<span>────</span>${categories.length} Categories, Endless Possibilities<span>────</span><br>✦`;
        }
        drawCategoryTiles();
    }

    window.setStoreCategories = (names, categoryIcons = {}) => {
        if (!Array.isArray(names) || names.some((name) => typeof name !== "string")) {
            throw new Error("Category service returned an invalid category list.");
        }
        renderCategoryControls(names, categoryIcons);
    };
})();
