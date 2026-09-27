/*
 * main.js — client-side behavior for the Gold Creation storefront.
 * Runs after the DOM is ready and wires up: Lucide icon rendering,
 * flash-message dismissal, mobile navigation, currency switching
 * (site-wide cart currency + per-product preview), the product media
 * gallery (thumbnails, prev/next, keyboard & swipe), quantity pickers,
 * AJAX form submission, and product detail tab switching.
 */
document.addEventListener('DOMContentLoaded', function() {

    /* --- Icon rendering & feedback --- lucide creates SVG icons from <i data-lucide>. */
    lucide.createIcons();

    /* Auto-dismiss global .flash-message elements after 3s so they don't linger. */
    setTimeout(() => {
        document.querySelectorAll('.flash-message').forEach(el => el.remove());
    }, 3000);

    /* --- Mobile navigation toggle --- #mobile-menu-btn shows/hides #mobile-nav. */
    const menuBtn = document.getElementById('mobile-menu-btn');
    const mobileNav = document.getElementById('mobile-nav');
    if(menuBtn && mobileNav) {
        menuBtn.addEventListener('click', () => {
            mobileNav.classList.toggle('hidden');
        });
    }

    // --- Currency selection ---
    // Header dropdown (.gc-currency-select): the site-wide "shopping currency" —
    // it's what the cart and checkout total in, so picking it updates every price
    // on the page AND persists (cookie, via /currency/set).
    // Per-product dropdown (.gc-price-currency-select): a "preview in..." control —
    // it's independent per product, only changes that one product's displayed
    // price, doesn't touch any other product or the shopping currency, and isn't
    // persisted. Two different products can be shown in two different currencies
    // at the same time.
    /* Formats an INR base price into the target currency using server rates (window.GC_CURRENCY_RATES). */
    function gcFormatCurrency(amountInr, code) {
        const rates = window.GC_CURRENCY_RATES || {};
        const info = rates[code] || { symbol: code + ' ', rate_to_inr: 1 };
        const converted = parseFloat(amountInr) / parseFloat(info.rate_to_inr);
        const decimals = code === 'JPY' ? 0 : 2;
        const formatted = converted.toLocaleString('en-US', { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
        return `${info.symbol}${formatted}`;
    }

    /* Recomputes every .gc-price and syncs both .gc-currency-select dropdowns to `code`. */
    function gcApplyCurrency(code) {
        window.GC_CURRENT_CURRENCY = code;
        document.querySelectorAll('.gc-price[data-base-price-inr]').forEach(el => {
            el.textContent = gcFormatCurrency(el.dataset.basePriceInr, code);
        });
        document.querySelectorAll('.gc-currency-select').forEach(sel => {
            sel.value = code;
        });
        document.querySelectorAll('.gc-price-currency-select').forEach(sel => {
            sel.value = code;
        });
    }

    /* Applies currency then persists the site-wide choice via POST to /currency/set (best-effort). */
    function gcSetCurrency(code) {
        gcApplyCurrency(code);
        if (!window.GC_SET_CURRENCY_URL) return;
        fetch(window.GC_SET_CURRENCY_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin',
            body: JSON.stringify({ currency: code })
        }).catch(() => { /* cookie persistence is best-effort; the page already reflects the choice */ });
    }

    /* Bind site-wide currency change on .gc-currency-select to update + persist. */
    document.querySelectorAll('.gc-currency-select').forEach(sel => {
        sel.addEventListener('change', (e) => gcSetCurrency(e.target.value));
    });

    /* Bind per-product preview: .gc-price-currency-select only reformats its own product's .gc-price. */
    document.querySelectorAll('.gc-price-currency-select').forEach(sel => {
        sel.addEventListener('change', (e) => {
            const code = e.target.value;
            // Only touch this dropdown's own price, wherever it sits relative to it
            // (sibling in the price-macro markup, or an ancestor's .gc-price on
            // pages that lay it out differently) — never any other product.
            const scope = e.target.closest('span, div, li, article') || document;
            const priceEl = scope.querySelector('.gc-price[data-base-price-inr]');
            if (priceEl) {
                priceEl.textContent = gcFormatCurrency(priceEl.dataset.basePriceInr, code);
            }
        });
    });

    /* --- Product media gallery --- #product-media-gallery holds .media-thumb rows. */
    const gallery = document.getElementById('product-media-gallery');
    if(gallery) {
        const thumbs = gallery.querySelectorAll('.media-thumb');
        const mainImg = document.getElementById('main-media-img');
        const mainVideo = document.getElementById('main-media-video');
        let currentIndex = 0;
        const mediaList = Array.from(thumbs);

        /* Returns 'image' or 'video' for the gallery item at `index` (defaults to image). */
        function getMediaType(index) {
            if (!mediaList[index]) return 'image';
            return (mediaList[index].dataset.mediaType || 'image').toLowerCase();
        }

        /* Hides both the main image (#main-media-img) and video (#main-media-video). */
        function hideMainMedia() {
            if (mainImg) mainImg.style.display = 'none';
            if (mainVideo) mainVideo.style.display = 'none';
        }

        /* Shows the image/video at `index` and marks its .media-thumb as active. */
        function showMedia(index) {
            if(!mediaList[index]) return;
            currentIndex = index;
            hideMainMedia();
            const mType = getMediaType(index);
            
            if (mType === 'video') {
                if (mainVideo) {
                    const src = mediaList[index].dataset.videoSrc || '';
                    const poster = mediaList[index].dataset.poster || '';
                    if (src) {
                        mainVideo.querySelector('source').src = src;
                        mainVideo.poster = poster;
                        mainVideo.load();
                        mainVideo.style.display = 'block';
                    }
                }
            } else {
                if (mainImg) {
                    const src = mediaList[index].querySelector('img')?.src || '';
                    if (src) {
                        mainImg.src = src;
                        mainImg.style.display = 'block';
                    }
                }
            }
            
            mediaList.forEach((t, i) => {
                t.classList.toggle('border-[#8B1E3F]', i === index);
                t.classList.toggle('border-transparent', i !== index);
            });
        }

        /* Clicking a .media-thumb shows that item in the gallery. */
        thumbs.forEach((thumb, i) => {
            thumb.addEventListener('click', () => showMedia(i));
        });

        /* .media-prev navigates to the previous gallery item. */
        document.querySelectorAll('.media-prev').forEach(btn => {
            btn.addEventListener('click', () => {
                const next = (currentIndex - 1 + mediaList.length) % mediaList.length;
                showMedia(next);
            });
        });

        /* .media-next navigates to the next gallery item. */
        document.querySelectorAll('.media-next').forEach(btn => {
            btn.addEventListener('click', () => {
                const next = (currentIndex + 1) % mediaList.length;
                showMedia(next);
            });
        });

        /* Left/Right arrow keys cycle the gallery. */
        document.addEventListener('keydown', (e) => {
            if(e.key === 'ArrowLeft') {
                showMedia((currentIndex - 1 + mediaList.length) % mediaList.length);
            }
            if(e.key === 'ArrowRight') {
                showMedia((currentIndex + 1) % mediaList.length);
            }
        });

        /* Touch swipe on the gallery: right-to-left = next, left-to-right = prev. */
        let touchStartX = 0;
        gallery.addEventListener('touchstart', e => touchStartX = e.changedTouches[0].screenX);
        gallery.addEventListener('touchend', e => {
            const diff = touchStartX - e.changedTouches[0].screenX;
            if(Math.abs(diff) > 50) {
                if(diff > 0) {
                    showMedia((currentIndex + 1) % mediaList.length);
                } else {
                    showMedia((currentIndex - 1 + mediaList.length) % mediaList.length);
                }
            }
        });

        /* Initialize the gallery to the first media item if any exist. */
        if (mediaList.length > 0) {
            showMedia(0);
        }
    }

    /* --- Product page quantity stepper --- #qty-minus/#qty-plus adjust #qty-input (no submit). */
    const qtyMinus = document.getElementById('qty-minus');
    const qtyPlus = document.getElementById('qty-plus');
    const qtyInput = document.getElementById('qty-input');
    if(qtyMinus && qtyInput) {
        qtyMinus.addEventListener('click', () => {
            if(parseInt(qtyInput.value) > 1) qtyInput.value = parseInt(qtyInput.value) - 1;
        });
    }
    if(qtyPlus && qtyInput) {
        qtyPlus.addEventListener('click', () => {
            qtyInput.value = parseInt(qtyInput.value) + 1;
        });
    }

    /* --- Cart line-item steppers --- .qty-decr/.qty-incr mutate .qty-input then submit the form. */
    document.querySelectorAll('.qty-decr').forEach(btn => {
        btn.addEventListener('click', () => {
            const form = btn.closest('form');
            const input = form ? form.querySelector('.qty-input') : null;
            if(input && parseInt(input.value, 10) > 1) {
                input.value = parseInt(input.value, 10) - 1;
                form.submit();
            }
        });
    });
    document.querySelectorAll('.qty-incr').forEach(btn => {
        btn.addEventListener('click', () => {
            const form = btn.closest('form');
            const input = form ? form.querySelector('.qty-input') : null;
            if(input) {
                input.value = parseInt(input.value, 10) + 1;
                form.submit();
            }
        });
    });

    /* AJAX form: any [data-ajax-form] posts via fetch with the CSRF token, then reloads on success. */
    document.querySelectorAll('[data-ajax-form]').forEach(form => {
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const formData = new FormData(form);
            const response = await fetch(form.action, {
                method: 'POST',
                headers: {'X-CSRFToken': formData.get('csrf_token')},
                body: formData
            });
            const data = await response.json();
            if(data.success) {
                location.reload();
            } else {
                alert(data.message || 'Error');
            }
        });
    });

    /* Star rating container (#star-rating) — referenced for potential rating widgets. */
    const starRating = document.getElementById('star-rating');
    /* --- Product detail tabs --- .info-tab-btn toggles which .info-tab-panel is visible. */
    const infoTabBtns = document.querySelectorAll('.info-tab-btn');
    if (infoTabBtns.length) {
        infoTabBtns.forEach(btn => {
            btn.addEventListener('click', () => {
                const tab = btn.dataset.tab;
                infoTabBtns.forEach(b => {
                    const active = b === btn;
                    b.classList.toggle('border-[#8B1E3F]', active);
                    b.classList.toggle('text-[#8B1E3F]', active);
                    b.classList.toggle('border-transparent', !active);
                    b.classList.toggle('text-[#6B6B6B]', !active);
                });
                document.querySelectorAll('.info-tab-panel').forEach(panel => {
                    panel.classList.toggle('hidden', panel.dataset.tabPanel !== tab);
                });
            });
        });
    }
});
