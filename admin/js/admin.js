"use strict";

const STATUSES = ["Received", "New", "Contacted", "Processing", "Shipped", "Delivered", "Cancelled"];
const CATEGORY_ICONS = [
    ["♧", "Necklace"], ["♙", "Earrings"], ["◉", "Ring"], ["◌", "Bracelet"],
    ["⌁", "Anklet"], ["◇", "Pendant"], ["⌘", "Chain"], ["◎", "Bangle"],
    ["✧", "Mangalsutra"], ["✦", "Nose pin"], ["○", "Toe ring"],
    ["❖", "Jewellery set"], ["✥", "Gold"], ["♢", "Oxidised"], ["❋", "Hair accessory"],
    ["♕", "Gift"], ["▣", "Mystery jar"]
];
const $ = (selector) => document.querySelector(selector);

class ApiFailure extends Error {
    constructor(message, status) {
        super(message);
        this.status = status;
    }
}

async function api(path, options = {}) {
    const headers = new Headers(options.headers || {});
    if (options.body !== undefined && !(options.body instanceof FormData)) headers.set("Content-Type", "application/json");
    const response = await fetch(`/api/admin${path}`, {
        ...options,
        headers,
        credentials: "same-origin"
    });
    let result;
    try {
        result = await response.json();
    } catch (error) {
        throw new Error("The server returned an invalid response.");
    }
    if (!response.ok) throw new ApiFailure(result.error || "The request could not be completed.", response.status);
    return result;
}

function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (character) => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    })[character]);
}

function money(value) {
    return `$${Number(value).toFixed(2)}`;
}

function productImage(image) {
    if (!image) return "";
    if (image.startsWith("/")) return image;
    return image.startsWith("http://") || image.startsWith("https://")
        ? image
        : `https://images.unsplash.com/${encodeURIComponent(image)}?auto=format&fit=crop&w=160&q=80`;
}

function showToast(message) {
    const toast = $("#toast");
    toast.textContent = message;
    toast.hidden = false;
    clearTimeout(showToast.timeout);
    showToast.timeout = setTimeout(() => { toast.hidden = true; }, 3200);
}

function displayLogin(message = "") {
    $("#adminView").hidden = true;
    $("#loginView").hidden = false;
    $("#loginError").textContent = message;
}

function displayAdmin(email) {
    $("#loginView").hidden = true;
    $("#adminView").hidden = false;
    $("#adminEmail").textContent = email;
}

function orderMarkup(order, compact = false) {
    const name = escapeHtml(order.name || order.customer_name);
    const status = STATUSES.includes(order.status) ? order.status : "Received";
    const details = [
        order.phone && escapeHtml(order.phone),
        order.email && escapeHtml(order.email),
        order.created_at && escapeHtml(order.created_at),
        money(order.total)
    ].filter(Boolean).join(" · ");
    return `<article class="item-row">
        <div><strong>${escapeHtml(order.id)} · ${name}</strong>
        <p>${details}</p>${order.address && !compact ? `<p>${escapeHtml(order.address)}</p>` : ""}</div>
        <div class="item-actions">
            ${compact
                ? `<span>${escapeHtml(status)}</span>`
                : `<label>Order status<select data-order-id="${escapeHtml(order.id)}" aria-label="Status for order ${escapeHtml(order.id)}">
                    ${STATUSES.map((option) => `<option value="${option}"${option === status ? " selected" : ""}>${option}</option>`).join("")}
                </select></label>`}
        </div>
    </article>`;
}

function renderProducts(products) {
    $("#productList").innerHTML = products.length ? products.map((product) => `
        <article class="item-row product-row">
            ${productImage(product.imageUrl || product.img) ? `<img class="product-image" src="${escapeHtml(productImage(product.imageUrl || product.img))}" alt="" loading="lazy">` : `<div class="product-image"></div>`}
            <div><strong>${escapeHtml(product.name)}</strong>
                <p>${escapeHtml(product.category || product.cat)} · ${money(product.price)}${product.badge ? ` · ${escapeHtml(product.badge)}` : ""}</p>
            </div>
            <button class="danger" type="button" data-delete-product="${Number(product.id)}" aria-label="Delete ${escapeHtml(product.name)}">Delete</button>
        </article>`).join("") : `<p class="empty">No products are in the catalog yet.</p>`;
}

function renderCategories(categories) {
    const iconOptions = (selected = "✧") => CATEGORY_ICONS.map(([icon, label]) =>
        `<option value="${icon}"${icon === selected ? " selected" : ""}>${icon} ${label}</option>`
    ).join("");
    $("#categoryForm [data-category-icon-select]").innerHTML = iconOptions();
    const select = $("#productCategory");
    select.innerHTML = `<option value="">Choose a category</option>${categories.map((category) =>
        `<option value="${escapeHtml(category.name)}">${escapeHtml(category.name)}</option>`
    ).join("")}`;
    $("#categoryList").innerHTML = categories.length ? categories.map((category) => `
        <article class="item-row category-row" data-category-row="${Number(category.id)}" data-product-count="${Number(category.product_count)}">
            <label class="category-edit">Category name<input data-category-name="${Number(category.id)}" maxlength="80" value="${escapeHtml(category.name)}" required></label>
            <label>Storefront icon<select data-category-icon="${Number(category.id)}">${iconOptions(category.icon)}</select></label>
            <label>Move ${Number(category.product_count)} product(s) to<select data-category-target="${Number(category.id)}">
                <option value="">Choose when deleting</option>
                ${categories.filter((target) => target.id !== category.id).map((target) =>
                    `<option value="${Number(target.id)}">${escapeHtml(target.name)}</option>`
                ).join("")}
            </select></label>
            <button type="button" data-save-category="${Number(category.id)}">Save category</button>
            <button class="danger" type="button" data-delete-category="${Number(category.id)}">Delete</button>
        </article>`).join("") : `<p class="empty">No categories are configured.</p>`;
}

function renderOrders(orders) {
    $("#orderList").innerHTML = orders.length
        ? orders.map((order) => orderMarkup(order)).join("")
        : `<p class="empty">There are no orders yet.</p>`;
    $("#recentOrders").innerHTML = orders.length
        ? orders.slice(0, 5).map((order) => orderMarkup(order, true)).join("")
        : `<p class="empty">There are no orders yet.</p>`;
}

function renderCustomers(customers) {
    $("#customerList").innerHTML = customers.length ? customers.map((customer) => `
        <article class="item-row">
            <div><strong>${escapeHtml(customer.name)}</strong>
                <p>${escapeHtml(customer.email)} · Registered ${escapeHtml(customer.created_at)} · ${Number(customer.order_count)} order(s)</p>
            </div>
        </article>`).join("") : `<p class="empty">No customer accounts have registered yet.</p>`;
}

function renderNewsletter(subscriptions) {
    $("#newsletterList").innerHTML = subscriptions.length ? subscriptions.map((subscription) => `
        <article class="item-row">
            <div><strong>${escapeHtml(subscription.email)}</strong>
                <p>Subscribed ${escapeHtml(subscription.created_at)}</p>
            </div>
        </article>`).join("") : `<p class="empty">No one has subscribed yet.</p>`;
}

function renderReviews(reviews) {
    $("#reviewList").innerHTML = reviews.length ? reviews.map((review) => `
        <article class="item-row">
            ${review.image_url ? `<img class="product-image" src="${escapeHtml(review.image_url)}" alt="Photo shared with review from ${escapeHtml(review.name)}" loading="lazy">` : ""}
            <div><strong>${escapeHtml(review.name)} · ${"★".repeat(Number(review.rating))}</strong>
                <p>${escapeHtml(review.note)}${review.created_at ? ` · ${escapeHtml(review.created_at)}` : ""}</p>
                ${review.email || review.phone || review.state || review.address ? `<p>${[review.email, review.phone, review.state, review.address].filter(Boolean).map(escapeHtml).join(" · ")}</p>` : ""}
            </div>
        </article>`).join("") : `<p class="empty">There are no customer reviews yet.</p>`;
}

let logoPreviewUrl = "";
let videoPreviewUrl = "";
let heroImagePreviewUrl = "";
let footerSectionData = [];
let footerFilterCategories = [];

function renderBranding(settings) {
    const heroImagePreview = $("#heroImagePreview");
    if (heroImagePreviewUrl) URL.revokeObjectURL(heroImagePreviewUrl);
    heroImagePreviewUrl = "";
    heroImagePreview.src = settings.heroImageUrl || "/images/storefront-hero.png";
    heroImagePreview.hidden = false;
    const logoPreview = $("#logoPreview");
    if (logoPreviewUrl) URL.revokeObjectURL(logoPreviewUrl);
    logoPreviewUrl = "";
    logoPreview.src = settings.logoUrl || "/user/assets/bandilki-mark.svg";
    logoPreview.hidden = false;
    const videoPreview = $("#videoPreview");
    if (videoPreviewUrl) URL.revokeObjectURL(videoPreviewUrl);
    videoPreviewUrl = "";
    videoPreview.pause();
    videoPreview.removeAttribute("src");
    if (settings.introVideoUrl) {
        videoPreview.src = settings.introVideoUrl;
        videoPreview.hidden = false;
    } else {
        videoPreview.hidden = true;
    }
}

function renderFooterEditor(sections, categoryNames = footerFilterCategories) {
    footerSectionData = sections;
    footerFilterCategories = categoryNames;
    $("#footerSectionEditor").innerHTML = sections.map((section, sectionIndex) => `
        <fieldset class="footer-admin-section">
            <legend>${escapeHtml(section.id === "legal" ? "Footer bottom links" : section.title)}</legend>
            ${section.id === "legal" ? "" : `<label>Section heading<input data-footer-title="${sectionIndex}" maxlength="60" value="${escapeHtml(section.title)}" required></label>`}
            <div class="list">
                ${section.links.map((link, linkIndex) => `
                    <div class="footer-link-row" data-footer-link="${sectionIndex}:${linkIndex}">
                        <label>Link name<input data-footer-label maxlength="80" value="${escapeHtml(link.label)}" required></label>
                        <label>Destination<input data-footer-url maxlength="1000" value="${escapeHtml(link.url)}" placeholder="#shop or https://..." required></label>
                        ${section.id === "explore"
                            ? `<label>Category filter (optional)<select data-footer-filter><option value="">Use destination</option><option value="All"${link.filter === "All" ? " selected" : ""}>All products</option>${categoryNames.map((name) => `<option value="${escapeHtml(name)}"${link.filter === name ? " selected" : ""}>${escapeHtml(name)}</option>`).join("")}</select></label>`
                            : `<input type="hidden" data-footer-filter value="">`}
                        <button class="danger" type="button" data-remove-footer-link>Remove</button>
                    </div>`).join("")}
            </div>
            <button class="button-secondary" type="button" data-add-footer-link="${sectionIndex}">Add link</button>
        </fieldset>`).join("");
}

function readFooterEditor() {
    return footerSectionData.map((section, sectionIndex) => ({
        id: section.id,
        title: section.id === "legal"
            ? ""
            : $(`[data-footer-title="${sectionIndex}"]`).value.trim(),
        links: [...document.querySelectorAll(`[data-footer-link^="${sectionIndex}:"]`)].map((row) => ({
            label: row.querySelector("[data-footer-label]").value.trim(),
            url: row.querySelector("[data-footer-url]").value.trim(),
            filter: row.querySelector("[data-footer-filter]").value.trim()
        }))
    }));
}

async function refreshData() {
    const [dashboard, products, categories, orders, customers, newsletter, reviews, branding] = await Promise.all([
        api("/dashboard"), api("/products"), api("/categories"), api("/orders"), api("/customers"),
        api("/newsletter"), api("/reviews"), api("/settings")
    ]);
    $("#customerCount").textContent = dashboard.customers;
    $("#orderCount").textContent = dashboard.orders;
    $("#productCount").textContent = dashboard.products;
    renderCategories(categories.categories);
    renderProducts(products.products);
    renderOrders(orders.orders);
    renderCustomers(customers.customers);
    renderNewsletter(newsletter.subscriptions);
    renderReviews(reviews.reviews);
    renderBranding(branding);
    renderFooterEditor(branding.footerSections, categories.categories.map((category) => category.name));
}

function formData(form) {
    return Object.fromEntries(new FormData(form).entries());
}

document.querySelectorAll(".nav-button").forEach((button) => {
    button.addEventListener("click", () => {
        document.querySelectorAll(".nav-button").forEach((item) => item.classList.toggle("active", item === button));
        document.querySelectorAll("[data-panel]").forEach((panel) => {
            panel.hidden = panel.dataset.panel !== button.dataset.page;
        });
    });
});

$("#loginForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = event.currentTarget.querySelector("button[type=submit]");
    button.disabled = true;
    $("#loginError").textContent = "";
    try {
        const result = await api("/session", { method: "POST", body: JSON.stringify(formData(event.currentTarget)) });
        displayAdmin(result.admin.email);
        await refreshData();
    } catch (error) {
        displayLogin(error.message);
    } finally {
        button.disabled = false;
    }
});

$("#logoutButton").addEventListener("click", async () => {
    try {
        await api("/session", { method: "DELETE" });
        displayLogin();
        $("#loginForm").reset();
    } catch (error) {
        showToast(error.message);
    }
});

$("#productForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const button = form.querySelector("button[type=submit]");
    const preview = $("#productImagePreview");
    button.disabled = true;
    $("#productMessage").textContent = "";
    try {
        await api("/products", { method: "POST", body: new FormData(form) });
        form.reset();
        if (preview.src.startsWith("blob:")) URL.revokeObjectURL(preview.src);
        preview.hidden = true;
        preview.removeAttribute("src");
        await refreshData();
        showToast("Product added to the storefront catalog.");
    } catch (error) {
        $("#productMessage").textContent = error.message;
    } finally {
        button.disabled = false;
    }
});

$("#productImageInput").addEventListener("change", (event) => {
    const file = event.currentTarget.files[0];
    const preview = $("#productImagePreview");
    if (preview.src.startsWith("blob:")) URL.revokeObjectURL(preview.src);
    if (!file) {
        preview.hidden = true;
        preview.removeAttribute("src");
        return;
    }
    if (!["image/jpeg", "image/png"].includes(file.type) || file.size > 5 * 1024 * 1024) {
        event.currentTarget.value = "";
        preview.hidden = true;
        preview.removeAttribute("src");
        $("#productMessage").textContent = "Choose a JPEG or PNG image up to 5 MB.";
        return;
    }
    $("#productMessage").textContent = "";
    preview.src = URL.createObjectURL(file);
    preview.hidden = false;
});

$("#categoryForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const button = form.querySelector("button[type=submit]");
    button.disabled = true;
    $("#categoryMessage").textContent = "";
    try {
        await api("/categories", { method: "POST", body: JSON.stringify(formData(form)) });
        form.reset();
        await refreshData();
        showToast("Category added to the storefront.");
    } catch (error) {
        $("#categoryMessage").textContent = error.message;
    } finally {
        button.disabled = false;
    }
});

$("#logoInput").addEventListener("change", (event) => {
    const file = event.currentTarget.files[0];
    const preview = $("#logoPreview");
    if (logoPreviewUrl) URL.revokeObjectURL(logoPreviewUrl);
    logoPreviewUrl = "";
    if (!file) return;
    if (!["image/jpeg", "image/png"].includes(file.type) || file.size > 5 * 1024 * 1024) {
        event.currentTarget.value = "";
        $("#logoMessage").textContent = "Choose a JPEG or PNG logo up to 5 MB.";
        return;
    }
    $("#logoMessage").textContent = "";
    logoPreviewUrl = URL.createObjectURL(file);
    preview.src = logoPreviewUrl;
    preview.hidden = false;
});

$("#videoInput").addEventListener("change", (event) => {
    const file = event.currentTarget.files[0];
    const preview = $("#videoPreview");
    if (videoPreviewUrl) URL.revokeObjectURL(videoPreviewUrl);
    videoPreviewUrl = "";
    if (!file) return;
    if (!["video/mp4", "video/webm"].includes(file.type) || file.size > 25 * 1024 * 1024) {
        event.currentTarget.value = "";
        $("#videoMessage").textContent = "Choose an MP4 or WebM video up to 25 MB.";
        return;
    }
    $("#videoMessage").textContent = "";
    videoPreviewUrl = URL.createObjectURL(file);
    preview.src = videoPreviewUrl;
    preview.hidden = false;
});

$("#heroImageInput").addEventListener("change", (event) => {
    const file = event.currentTarget.files[0];
    const preview = $("#heroImagePreview");
    if (heroImagePreviewUrl) URL.revokeObjectURL(heroImagePreviewUrl);
    heroImagePreviewUrl = "";
    if (!file) return;
    if (!["image/jpeg", "image/png"].includes(file.type) || file.size > 5 * 1024 * 1024) {
        event.currentTarget.value = "";
        $("#heroImageMessage").textContent = "Choose a JPEG or PNG image up to 5 MB.";
        return;
    }
    $("#heroImageMessage").textContent = "";
    heroImagePreviewUrl = URL.createObjectURL(file);
    preview.src = heroImagePreviewUrl;
    preview.hidden = false;
});

$("#heroImageForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const button = form.querySelector("button[type=submit]");
    button.disabled = true;
    $("#heroImageMessage").textContent = "";
    try {
        await api("/settings", { method: "POST", body: new FormData(form) });
        form.reset();
        await refreshData();
        showToast("Storefront banner updated.");
    } catch (error) {
        $("#heroImageMessage").textContent = error.message;
    } finally {
        button.disabled = false;
    }
});

$("#logoForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const button = form.querySelector("button[type=submit]");
    button.disabled = true;
    $("#logoMessage").textContent = "";
    try {
        await api("/settings", { method: "POST", body: new FormData(form) });
        form.reset();
        await refreshData();
        showToast("Store logo updated.");
    } catch (error) {
        $("#logoMessage").textContent = error.message;
    } finally {
        button.disabled = false;
    }
});

$("#removeHeroImageButton").addEventListener("click", async (event) => {
    const button = event.currentTarget;
    button.disabled = true;
    $("#heroImageMessage").textContent = "";
    try {
        const data = new FormData();
        data.set("clearHeroImage", "true");
        await api("/settings", { method: "POST", body: data });
        $("#heroImageForm").reset();
        await refreshData();
        showToast("Default banner restored.");
    } catch (error) {
        $("#heroImageMessage").textContent = error.message;
    } finally {
        button.disabled = false;
    }
});

$("#videoForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const button = form.querySelector("button[type=submit]");
    button.disabled = true;
    $("#videoMessage").textContent = "";
    try {
        await api("/settings", { method: "POST", body: new FormData(form) });
        form.reset();
        await refreshData();
        showToast("Starting video updated.");
    } catch (error) {
        $("#videoMessage").textContent = error.message;
    } finally {
        button.disabled = false;
    }
});

$("#removeLogoButton").addEventListener("click", async (event) => {
    const button = event.currentTarget;
    button.disabled = true;
    $("#logoMessage").textContent = "";
    try {
        const data = new FormData();
        data.set("clearLogo", "true");
        await api("/settings", { method: "POST", body: data });
        $("#logoForm").reset();
        await refreshData();
        showToast("Default logo restored.");
    } catch (error) {
        $("#logoMessage").textContent = error.message;
    } finally {
        button.disabled = false;
    }
});

$("#removeVideoButton").addEventListener("click", async (event) => {
    const button = event.currentTarget;
    button.disabled = true;
    $("#videoMessage").textContent = "";
    try {
        const data = new FormData();
        data.set("clearIntroVideo", "true");
        await api("/settings", { method: "POST", body: data });
        $("#videoForm").reset();
        await refreshData();
        showToast("Starting video removed.");
    } catch (error) {
        $("#videoMessage").textContent = error.message;
    } finally {
        button.disabled = false;
    }
});

$("#footerSectionEditor").addEventListener("click", (event) => {
    const addButton = event.target.closest("[data-add-footer-link]");
    const removeButton = event.target.closest("[data-remove-footer-link]");
    if (!addButton && !removeButton) return;
    footerSectionData = readFooterEditor();
    if (addButton) {
        footerSectionData[Number(addButton.dataset.addFooterLink)].links.push({ label: "", url: "", filter: "" });
    } else {
        const [sectionIndex, linkIndex] = removeButton.closest("[data-footer-link]").dataset.footerLink.split(":").map(Number);
        footerSectionData[sectionIndex].links.splice(linkIndex, 1);
    }
    renderFooterEditor(footerSectionData);
});

$("#footerForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = event.currentTarget.querySelector("button[type=submit]");
    button.disabled = true;
    $("#footerMessage").textContent = "";
    try {
        const result = await api("/footer", {
            method: "POST",
            body: JSON.stringify({ sections: readFooterEditor() })
        });
        renderFooterEditor(result.sections);
        showToast("Footer navigation updated.");
    } catch (error) {
        $("#footerMessage").textContent = error.message;
    } finally {
        button.disabled = false;
    }
});

$("#categoryList").addEventListener("click", async (event) => {
    const saveButton = event.target.closest("[data-save-category]");
    const deleteButton = event.target.closest("[data-delete-category]");
    if (!saveButton && !deleteButton) return;
    const button = saveButton || deleteButton;
    const categoryId = button.dataset.saveCategory || button.dataset.deleteCategory;
    const row = button.closest("[data-category-row]");
    const input = row.querySelector(`[data-category-name="${categoryId}"]`);
    button.disabled = true;
    try {
        if (saveButton) {
            const icon = row.querySelector(`[data-category-icon="${categoryId}"]`).value;
            await api(`/categories/${categoryId}`, {
                method: "PUT",
                body: JSON.stringify({ name: input.value, icon })
            });
            await refreshData();
            showToast("Category and its products updated.");
            return;
        }
        const replacementId = row.querySelector(`[data-category-target="${categoryId}"]`).value;
        const productCount = Number(row.dataset.productCount);
        if (productCount && !replacementId) {
            showToast("Choose a category to move these products into before deleting.");
            return;
        }
        if (!window.confirm(productCount && replacementId
            ? "Delete this category and move its products to the selected category?"
            : "Delete this category from the storefront?")) return;
        await api(`/categories/${categoryId}`, {
            method: "DELETE",
            body: JSON.stringify({ replacementId })
        });
        await refreshData();
        showToast("Category deleted.");
    } catch (error) {
        showToast(error.message);
    } finally {
        button.disabled = false;
    }
});

$("#productList").addEventListener("click", async (event) => {
    const button = event.target.closest("[data-delete-product]");
    if (!button) return;
    if (!window.confirm("Delete this product from the catalog?")) return;
    button.disabled = true;
    try {
        await api(`/products/${button.dataset.deleteProduct}`, { method: "DELETE" });
        await refreshData();
        showToast("Product deleted.");
    } catch (error) {
        button.disabled = false;
        showToast(error.message);
    }
});

$("#manualOrderForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const button = form.querySelector("button[type=submit]");
    const values = formData(form);
    values.total = Number(values.total);
    button.disabled = true;
    $("#orderMessage").textContent = "";
    try {
        const result = await api("/orders", { method: "POST", body: JSON.stringify(values) });
        form.reset();
        await refreshData();
        showToast(`Order ${result.order.id} created.`);
    } catch (error) {
        $("#orderMessage").textContent = error.message;
    } finally {
        button.disabled = false;
    }
});

$("#orderList").addEventListener("change", async (event) => {
    const select = event.target.closest("[data-order-id]");
    if (!select) return;
    select.disabled = true;
    try {
        await api(`/orders/${encodeURIComponent(select.dataset.orderId)}/status`, {
            method: "PUT", body: JSON.stringify({ status: select.value })
        });
        await refreshData();
        showToast("Order status updated.");
    } catch (error) {
        showToast(error.message);
        await refreshData();
    }
});

$("#trackingForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const values = formData(event.currentTarget);
    const query = new URLSearchParams({ orderId: values.orderId, phone: values.phone });
    const message = $("#trackingMessage");
    const resultPanel = $("#trackingResult");
    message.textContent = "";
    resultPanel.hidden = true;
    try {
        const result = await api(`/orders/track?${query.toString()}`);
        const order = result.order;
        resultPanel.innerHTML = `<h2>Order ${escapeHtml(order.id)}</h2>
            <p><strong>Status:</strong> ${escapeHtml(order.status)}</p>
            <p><strong>Customer:</strong> ${escapeHtml(order.name)} · ${escapeHtml(order.phone)}</p>
            <p><strong>Delivery address:</strong> ${escapeHtml(order.address)}</p>
            <p><strong>Placed:</strong> ${escapeHtml(order.created_at)} · <strong>Total:</strong> ${money(order.total)}</p>
            <h3>Items</h3><ul>${result.items.map((item) => `<li>${escapeHtml(item.name)} × ${Number(item.qty)} — ${money(item.price)}</li>`).join("")}</ul>`;
        resultPanel.hidden = false;
    } catch (error) {
        message.textContent = error.message;
    }
});

(async function initialize() {
    try {
        const session = await api("/session");
        displayAdmin(session.admin.email);
        await refreshData();
    } catch (error) {
        if (error instanceof ApiFailure && error.status === 401) {
            displayLogin();
            return;
        }
        displayLogin(error.message);
    }
})();
