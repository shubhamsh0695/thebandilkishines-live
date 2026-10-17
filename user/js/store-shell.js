"use strict";

const mobileMenu = document.getElementById("mobileMenu");
const mainNavigation = document.getElementById("nav");

mobileMenu.addEventListener("click", () => {
    const expanded = mobileMenu.getAttribute("aria-expanded") === "true";
    mobileMenu.setAttribute("aria-expanded", String(!expanded));
    mobileMenu.setAttribute("aria-label", expanded ? "Open menu" : "Close menu");
    mainNavigation.classList.toggle("show", !expanded);
});

mainNavigation.addEventListener("click", (event) => {
    if (!event.target.closest("a") || !window.matchMedia("(max-width: 1100px)").matches) return;
    mainNavigation.classList.remove("show");
    mobileMenu.setAttribute("aria-expanded", "false");
    mobileMenu.setAttribute("aria-label", "Open menu");
});
