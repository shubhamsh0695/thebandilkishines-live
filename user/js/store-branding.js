"use strict";

window.storeBrandingReady = fetch("/api/site-settings")
    .then((response) => {
        if (!response.ok) throw new Error(`Could not load store branding (${response.status}).`);
        return response.json();
    })
    .then((settings) => {
        const hero = document.querySelector(".hero");
        if (hero && settings.heroImageUrl) {
            const bannerUrl = new URL(settings.heroImageUrl, window.location.origin);
            if (bannerUrl.origin !== window.location.origin) {
                throw new Error("The storefront banner URL must use this site.");
            }
            hero.style.setProperty("--hero-image", `url("${bannerUrl.href}")`);
        }

        const ratingStars = document.getElementById("heroRatingStars");
        const ratingSummary = document.getElementById("heroRatingSummary");
        const deliveredCount = document.getElementById("deliveredOrderCount");
        const reviewCount = Number(settings.reviewCount) || 0;
        const averageRating = Number(settings.averageRating);
        const deliveredOrderCount = Number(settings.deliveredOrderCount) || 0;
        if (ratingStars && ratingSummary) {
            if (reviewCount > 0 && Number.isFinite(averageRating)) {
                ratingStars.textContent = "★".repeat(Math.round(averageRating)).padEnd(5, "☆");
                ratingStars.setAttribute("aria-label", `${averageRating.toFixed(1)} out of 5 stars`);
                ratingSummary.textContent = `${averageRating.toFixed(1)} / 5 from ${reviewCount} ${reviewCount === 1 ? "review" : "reviews"}`;
            } else {
                ratingStars.textContent = "☆☆☆☆☆";
                ratingStars.setAttribute("aria-label", "No customer ratings yet");
                ratingSummary.textContent = "No customer ratings yet";
            }
        }
        if (deliveredCount) {
            deliveredCount.textContent = `${deliveredOrderCount} ${deliveredOrderCount === 1 ? "order" : "orders"} successfully delivered`;
        }

        document.querySelectorAll('img[src$="bandilki-mark.svg"]').forEach((image) => {
            image.src = settings.logoUrl || "/user/assets/bandilki-mark.svg";
        });
        const favicon = document.querySelector('link[rel="icon"]');
        if (favicon) favicon.href = settings.logoUrl || "/user/assets/bandilki-mark.svg";

        if (Array.isArray(settings.footerSections) && typeof window.setStoreFooterSections === "function") {
            window.setStoreFooterSections(settings.footerSections);
        }

        if (settings.introVideoUrl) {
            const splash = document.getElementById("introSplash");
            if (splash) {
                const video = document.createElement("video");
                video.className = "intro-video";
                video.src = settings.introVideoUrl;
                video.autoplay = true;
                video.muted = true;
                video.playsInline = true;
                video.setAttribute("aria-hidden", "true");
                splash.prepend(video);
                splash.dataset.introVideo = "true";
            }
        } else {
            document.getElementById("introSplash")?.remove();
        }
        return settings;
    });
