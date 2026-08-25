document.addEventListener("DOMContentLoaded", () => {
    const gallery = document.querySelector("[data-gallery]");
    if (!gallery) return;
    const slides = [...gallery.querySelectorAll("[data-gallery-slide]")];
    const thumbnails = [...gallery.querySelectorAll("[data-gallery-thumbnail]")];
    const previousButton = gallery.querySelector("[data-gallery-previous]");
    const nextButton = gallery.querySelector("[data-gallery-next]");
    const openButton = gallery.querySelector("[data-gallery-open]");
    const lightbox = document.querySelector("[data-gallery-lightbox]");
    const lightboxImage = lightbox?.querySelector("[data-lightbox-image]");
    const lightboxCounter = lightbox?.querySelector("[data-lightbox-counter]");
    const lightboxThumbnails = lightbox
        ? [...lightbox.querySelectorAll("[data-lightbox-thumbnail]")]
        : [];
    const lightboxClose = lightbox?.querySelector("[data-lightbox-close]");
    const lightboxPrevious = lightbox?.querySelector("[data-lightbox-previous]");
    const lightboxNext = lightbox?.querySelector("[data-lightbox-next]");
    if (slides.length !== 2 || !thumbnails.length) return;
    let currentSlide = slides[0];
    let incomingSlide = slides[1];
    let animating = false;
    let activeIndex = Math.max(0, thumbnails.findIndex(
        (thumbnail) => thumbnail.getAttribute("aria-current") === "true",
    ));
    const imageCache = new Map();
    const loadGalleryImage = (index) => {
        const normalizedIndex = (index + thumbnails.length) % thumbnails.length;
        const cached = imageCache.get(normalizedIndex);
        if (cached) return cached.promise;
        const source = thumbnails[normalizedIndex];
        const image = new Image();
        const entry = { status: "loading", image, url: source.dataset.src };
        entry.promise = new Promise((resolve, reject) => {
            image.addEventListener("load", async () => {
                try {
                    await image.decode();
                    entry.status = "ready";
                    resolve(entry);
                } catch (error) {
                    entry.status = "error";
                    reject(error);
                }
            }, { once: true });
            image.addEventListener("error", (error) => {
                entry.status = "error";
                reject(error);
            }, { once: true });
            image.src = source.dataset.src;
        });
        imageCache.set(normalizedIndex, entry);
        return entry.promise;
    };
    const preloadGallery = async () => {
        await loadGalleryImage(activeIndex).catch(() => null);
        await Promise.all([
            loadGalleryImage(activeIndex + 1).catch(() => null),
            loadGalleryImage(activeIndex - 1).catch(() => null),
        ]);
        const remaining = thumbnails
            .map((_thumbnail, index) => index)
            .filter((index) => !imageCache.has(index));
        const workers = Array.from({ length: Math.min(3, remaining.length) }, async () => {
            while (remaining.length) {
                const index = remaining.shift();
                await loadGalleryImage(index).catch(() => null);
            }
        });
        await Promise.all(workers);
    };
    const updateSelection = (selectedIndex, focusThumbnail) => {
        const selected = thumbnails[selectedIndex];
        thumbnails.forEach((thumbnail, thumbnailIndex) => {
            const active = thumbnailIndex === selectedIndex;
            thumbnail.classList.toggle("is-active", active);
            thumbnail.setAttribute("aria-current", active ? "true" : "false");
        });
        selected.scrollIntoView({ block: "nearest", inline: "nearest" });
        if (focusThumbnail) selected.focus();
    };

    const nextFrame = () => new Promise((resolve) => window.requestAnimationFrame(resolve));

    const showImage = async (index, direction, focusThumbnail = false) => {
        if (animating || thumbnails.length < 2) return;
        const targetIndex = (index + thumbnails.length) % thumbnails.length;
        if (targetIndex === activeIndex) return;
        animating = true;
        previousButton?.setAttribute("disabled", "");
        nextButton?.setAttribute("disabled", "");
        const selected = thumbnails[targetIndex];
        try {
            await loadGalleryImage(targetIndex);
        } catch (_error) {
            previousButton?.removeAttribute("disabled");
            nextButton?.removeAttribute("disabled");
            animating = false;
            return;
        }
        incomingSlide.src = selected.dataset.src;
        incomingSlide.srcset = selected.dataset.srcset;
        incomingSlide.alt = selected.dataset.alt;
        incomingSlide.setAttribute("aria-hidden", "false");
        incomingSlide.className = `gallery-main-image is-positioning ${direction > 0 ? "is-enter-from-right" : "is-enter-from-left"}`;

        try {
            await incomingSlide.decode();
        } catch (_error) {
            // A failed decode is still allowed to render through the browser's normal image path.
        }

        let finished = false;
        const finish = () => {
            if (finished) return;
            finished = true;
            currentSlide.className = "gallery-main-image";
            currentSlide.setAttribute("aria-hidden", "true");
            incomingSlide.classList.remove("is-animating");
            [currentSlide, incomingSlide] = [incomingSlide, currentSlide];
            activeIndex = targetIndex;
            updateSelection(activeIndex, focusThumbnail);
            previousButton?.removeAttribute("disabled");
            nextButton?.removeAttribute("disabled");
            animating = false;
        };
        const startTransition = () => {
            incomingSlide.classList.remove("is-positioning");
            currentSlide.classList.add("is-animating");
            incomingSlide.classList.add("is-animating");
            currentSlide.classList.remove("is-current");
            currentSlide.classList.add(direction > 0 ? "is-exit-to-left" : "is-exit-to-right");
            incomingSlide.classList.remove("is-enter-from-right", "is-enter-from-left");
            incomingSlide.classList.add("is-current");
            incomingSlide.addEventListener("transitionend", finish, { once: true });
            const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
            window.setTimeout(finish, reducedMotion ? 240 : 480);
        };
        await nextFrame();
        await nextFrame();
        startTransition();
    };
    void preloadGallery();
    previousButton?.addEventListener("click", () => showImage(activeIndex - 1, -1));
    nextButton?.addEventListener("click", () => showImage(activeIndex + 1, 1));
    thumbnails.forEach((thumbnail, index) => {
        thumbnail.addEventListener("click", () => {
            const direction = index > activeIndex ? 1 : -1;
            showImage(index, direction);
        });
    });
    gallery.addEventListener("keydown", (event) => {
        if (event.key === "ArrowLeft") {
            event.preventDefault();
            showImage(activeIndex - 1, -1, true);
        } else if (event.key === "ArrowRight") {
            event.preventDefault();
            showImage(activeIndex + 1, 1, true);
        }
    });

    let lightboxIndex = activeIndex;
    let returnFocus = null;
    let savedScrollY = 0;
    const updateLightbox = async (index, focusThumbnail = false) => {
        if (!lightboxImage || !lightboxCounter || !lightboxThumbnails.length) return;
        lightboxIndex = (index + lightboxThumbnails.length) % lightboxThumbnails.length;
        try {
            await loadGalleryImage(lightboxIndex);
        } catch (_error) {
            return;
        }
        const selected = lightboxThumbnails[lightboxIndex];
        lightboxImage.src = selected.dataset.src;
        lightboxImage.alt = selected.dataset.alt;
        lightboxCounter.textContent = `${lightboxIndex + 1} / ${lightboxThumbnails.length}`;
        lightboxThumbnails.forEach((thumbnail, thumbnailIndex) => {
            const active = thumbnailIndex === lightboxIndex;
            thumbnail.classList.toggle("is-active", active);
            thumbnail.setAttribute("aria-current", active ? "true" : "false");
        });
        selected.scrollIntoView({ block: "nearest", inline: "nearest" });
        if (focusThumbnail) selected.focus();
    };
    const openLightbox = async () => {
        if (!lightbox) return;
        returnFocus = document.activeElement;
        savedScrollY = window.scrollY;
        await updateLightbox(activeIndex);
        lightbox.hidden = false;
        document.body.classList.add("lightbox-open");
        lightboxClose?.focus();
    };
    const closeLightbox = () => {
        if (!lightbox || lightbox.hidden) return;
        lightbox.hidden = true;
        document.body.classList.remove("lightbox-open");
        window.scrollTo(0, savedScrollY);
        returnFocus?.focus();
    };
    openButton?.addEventListener("click", openLightbox);
    lightboxClose?.addEventListener("click", closeLightbox);
    lightboxPrevious?.addEventListener("click", () => updateLightbox(lightboxIndex - 1));
    lightboxNext?.addEventListener("click", () => updateLightbox(lightboxIndex + 1));
    lightboxThumbnails.forEach((thumbnail, index) => {
        thumbnail.addEventListener("click", () => updateLightbox(index, true));
    });
    lightbox?.addEventListener("click", (event) => {
        if (event.target === lightbox) closeLightbox();
    });
    document.addEventListener("keydown", (event) => {
        if (!lightbox || lightbox.hidden) return;
        if (event.key === "Escape") {
            event.preventDefault();
            closeLightbox();
        } else if (event.key === "ArrowLeft") {
            event.preventDefault();
            updateLightbox(lightboxIndex - 1);
        } else if (event.key === "ArrowRight") {
            event.preventDefault();
            updateLightbox(lightboxIndex + 1);
        } else if (event.key === "Tab") {
            const focusable = [lightboxClose, lightboxPrevious, lightboxNext, ...lightboxThumbnails]
                .filter((element) => element && !element.disabled);
            const first = focusable[0];
            const last = focusable[focusable.length - 1];
            if (event.shiftKey && document.activeElement === first) {
                event.preventDefault();
                last.focus();
            } else if (!event.shiftKey && document.activeElement === last) {
                event.preventDefault();
                first.focus();
            }
        }
    });
});
