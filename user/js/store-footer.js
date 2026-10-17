"use strict";

const footerLinkTargets = {
    explore: document.getElementById("footerCategories"),
    contact: document.querySelector(".footer-contact .footer-links"),
    follow: document.querySelector(".footer-follow .footer-links"),
    legal: document.getElementById("footerLegalLinks")
};
const footerHeadingTargets = {
    explore: document.getElementById("footerHeadingExplore"),
    contact: document.getElementById("footerHeadingContact"),
    follow: document.getElementById("footerHeadingFollow")
};

window.storeFooterSections = null;

window.storeFooterIconMarkup = (sectionId, link) => {
    const value = `${link.filter || ""} ${link.label || ""} ${link.url || ""}`.toLowerCase();
    let drawing = '<path d="m12 2 8 8-8 12L4 10l8-8Z"/><path d="M4 10h16M8 6h8"/>';

    if (/instagram/.test(value)) {
        drawing = '<rect x="3" y="3" width="18" height="18" rx="5"/><circle cx="12" cy="12" r="4"/><circle cx="17.5" cy="6.5" r=".7"/>';
    } else if (/whatsapp|broadcast/.test(value)) {
        drawing = '<path d="M20 11.5a8 8 0 0 1-12 7L4 20l1.5-4A8 8 0 1 1 20 11.5Z"/><path d="M9 9c.5 2 2 3.5 4.5 4.5"/>';
    } else if (/track|order/.test(value)) {
        drawing = '<path d="m4 7 8-4 8 4-8 4-8-4Z"/><path d="M4 7v10l8 4 8-4V7M12 11v10"/>';
    } else if (/mailto:|email/.test(value)) {
        drawing = '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m4 7 8 6 8-6"/>';
    } else if (/tel:|phone|call/.test(value)) {
        drawing = '<path d="M6 3h4l2 5-3 2c1.5 3 3.5 5 6 6l2-3 5 2v4c0 1-1 2-2 2C10 20 4 14 4 5c0-1 1-2 2-2Z"/>';
    } else if (/earring/.test(value)) {
        drawing = '<circle cx="8" cy="5" r="2"/><path d="M8 7v3a4 4 0 1 0 4 4"/><circle cx="15" cy="5" r="2"/><path d="M15 7v3"/>';
    } else if (/nose pin/.test(value)) {
        drawing = '<path d="m12 3 2.3 6.7L21 12l-6.7 2.3L12 21l-2.3-6.7L3 12l6.7-2.3L12 3Z"/><circle cx="12" cy="12" r="2"/>';
    } else if (/ring/.test(value)) {
        drawing = '<circle cx="12" cy="14" r="6"/><path d="m9 7 3-4 3 4"/><path d="m9 7 3 2 3-2"/>';
    } else if (/anklet|bracelet|bangle/.test(value)) {
        drawing = '<ellipse cx="12" cy="12" rx="7" ry="9"/><path d="M7 7c3 2 7 2 10 0M7 17c3-2 7-2 10 0"/>';
    } else if (/chain/.test(value)) {
        drawing = '<path d="M9 8 7 6a3 3 0 0 0-4 4l4 4a3 3 0 0 0 4 0l2-2"/><path d="m15 16 2 2a3 3 0 0 0 4-4l-4-4a3 3 0 0 0-4 0l-2 2"/><path d="m9 15 6-6"/>';
    } else if (/necklace|pendant|mangalsutra/.test(value)) {
        drawing = '<path d="M5 3c0 8 2 11 7 14 5-3 7-6 7-14"/><path d="M12 17v2"/><path d="m12 19 2 2-2 2-2-2 2-2Z"/>';
    } else if (/hair accessory/.test(value)) {
        drawing = '<path d="M12 12C7 5 3 8 6 11l6 1-6 1c-3 3 1 6 6-1Zm0 0c5-7 9-4 6-1l-6 1 6 1c3 3-1 6-6-1Z"/><circle cx="12" cy="12" r="1.5"/>';
    } else if (/gift/.test(value)) {
        drawing = '<path d="M3 10h18v11H3zM2 6h20v4H2zM12 6v15"/><path d="M12 6H8a2 2 0 1 1 2-2c0 1 2 2 2 2Zm0 0h4a2 2 0 1 0-2-2c0 1-2 2-2 2Z"/>';
    } else if (/mystery jar/.test(value)) {
        drawing = '<path d="M7 4h10v3l2 2v11H5V9l2-2V4Z"/><path d="M7 7h10M9 13l2 2 4-4"/>';
    } else if (/oxidised/.test(value)) {
        drawing = '<path d="m12 2 2.2 7.1L21 12l-6.8 2.9L12 22l-2.2-7.1L3 12l6.8-2.9L12 2Z"/>';
    } else if (/gold/.test(value)) {
        drawing = '<path d="m12 3 9 5-9 5-9-5 9-5Z"/><path d="M3 8v8l9 5 9-5V8M12 13v8"/>';
    } else if (/jewellery set/.test(value)) {
        drawing = '<path d="M5 4h14v16H5z"/><path d="M9 4v5l3 3 3-3V4M9 20v-5l3-3 3 3v5"/>';
    } else if (/necklaces?/.test(value)) {
        drawing = '<path d="m12 2 8 8-8 12L4 10l8-8Z"/><path d="M4 10h16"/>';
    }

    return `<svg class="footer-icon" viewBox="0 0 24 24" aria-hidden="true">${drawing}</svg>`;
};

function renderStoreFooter(sections) {
    if (!Array.isArray(sections)) throw new Error("Footer settings are not a valid section list.");
    sections.forEach((section) => {
        const container = footerLinkTargets[section.id];
        if (!container || !Array.isArray(section.links)) {
            throw new Error("Footer settings contain an unknown link group.");
        }
        const heading = footerHeadingTargets[section.id];
        if (heading) {
            const star = heading.querySelector(".footer-heading-star, .footer-heading-icon");
            heading.replaceChildren(...(star ? [star, document.createTextNode(" " + section.title)] : [document.createTextNode(section.title)]));
        }
        if (section.id === "legal") {
            container.querySelectorAll(":scope > a").forEach((link) => link.remove());
        } else {
            container.replaceChildren();
        }
        section.links.forEach((link) => {
            const anchor = document.createElement("a");
            anchor.href = link.filter ? "#shop" : link.url;
            if (link.filter) anchor.dataset.filterCategory = link.filter;
            if (link.url === "#trackOrderBackdrop") anchor.dataset.trackOpen = "";
            if (link.url === "#contactBackdrop") anchor.dataset.contactOpen = "";
            if (/^https?:\/\//i.test(link.url)) {
                anchor.target = "_blank";
                anchor.rel = "noopener noreferrer";
            }
            if (section.id !== "legal") {
                anchor.insertAdjacentHTML("afterbegin", window.storeFooterIconMarkup(section.id, link));
            }
            const label = document.createElement("span");
            label.textContent = link.label;
            anchor.append(label);
            if (section.id === "legal") {
                container.insertBefore(anchor, container.querySelector("#footerCurrency"));
            } else {
                container.append(anchor);
            }
        });
    });
}

window.setStoreFooterSections = (sections) => {
    window.storeFooterSections = sections;
    renderStoreFooter(sections);
};
