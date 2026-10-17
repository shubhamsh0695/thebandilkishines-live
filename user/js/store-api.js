(() => {
    let signupMode = false;
    let currentUser = null;

    const message = (element, text, isError = false) => {
        if (!element) return;
        element.textContent = text;
        element.classList.toggle('error', isError);
    };

    const request = async (path, options = {}) => {
        const response = await fetch(path, {
            credentials: 'same-origin',
            ...options,
            headers: {
                ...(options.body && !(options.body instanceof FormData) ? { 'Content-Type': 'application/json' } : {}),
                ...options.headers
            }
        });
        const result = await response.json();
        if (!response.ok) {
            throw new Error(result.error || 'The request could not be completed.');
        }
        return result;
    };

    const submit = async (path, data, method = 'POST') => request(path, {
        method,
        body: JSON.stringify(data)
    });

    const formData = form => Object.fromEntries(new FormData(form).entries());
    const setBusy = (form, busy) => {
        const button = form.querySelector('button[type="submit"]');
        if (button) button.disabled = busy;
    };

    const renderReviewImage = window.showReview;
    if (typeof renderReviewImage === 'function') {
        window.showReview = index => {
            renderReviewImage(index);
            const card = document.getElementById('reviewCard');
            const reviews = JSON.parse(localStorage.getItem('bandilki-reviews') || '[]');
            const review = reviews[window.reviewIndex];
            if (card && review?.image_url) {
                const image = document.createElement('img');
                image.className = 'review-image';
                image.src = review.image_url;
                image.alt = `Photo shared by ${review.name || 'a customer'}`;
                const quote = card.querySelector('blockquote');
                card.insertBefore(image, quote || null);
            }
        };
    }

    const setAccountMode = signup => {
        signupMode = signup;
        const name = document.getElementById('accountName');
        const nameWrap = document.getElementById('accountNameWrap');
        const password = document.getElementById('accountPassword');
        if (name) name.required = signup;
        if (nameWrap) nameWrap.hidden = !signup;
        if (password) password.autocomplete = signup ? 'new-password' : 'current-password';
    };

    const setSignedIn = user => {
        currentUser = user;
        const title = document.getElementById('accountTitle');
        const copy = document.querySelector('#accountBackdrop .account-card>p');
        const toggle = document.getElementById('accountSwitch');
        const logout = document.getElementById('accountLogout');
        const form = document.getElementById('accountForm');
        if (user) {
            if (title) title.textContent = 'Welcome, ' + user.name;
            if (copy) copy.textContent = 'You are signed in as ' + user.email + '.';
            if (toggle) toggle.hidden = true;
            if (logout) logout.hidden = false;
            if (form) form.hidden = true;
            message(document.getElementById('accountMessage'), '');
        } else {
            setAccountMode(false);
            if (title) title.textContent = 'Welcome back';
            if (copy) copy.textContent = 'Sign in to keep your little treasures close.';
            if (toggle) toggle.hidden = false;
            if (toggle) toggle.textContent = 'Create an account';
            if (logout) logout.hidden = true;
            if (form) form.hidden = false;
            const submitButton = document.getElementById('accountSubmit');
            if (submitButton) submitButton.textContent = 'Continue';
        }
    };

    const showBackdrop = id => {
        const backdrop = document.getElementById(id);
        if (backdrop) backdrop.hidden = false;
    };

    const getCart = () => {
        try {
            const cart = JSON.parse(localStorage.getItem('bandilki-cart') || '[]');
            return Array.isArray(cart) ? cart : [];
        } catch (error) {
            console.error('Could not read the saved bag.', error);
            return [];
        }
    };

    const storeCart = items => {
        if (typeof cart !== 'undefined') {
            cart.splice(0, cart.length, ...items.map(item => ({
                id: Number(item.id),
                qty: Number(item.qty)
            })));
        }
        localStorage.setItem('bandilki-cart', JSON.stringify(items));
        const count = items.reduce((total, item) => total + (Number(item.qty) || 0), 0);
        const bagCount = document.getElementById('bagCount');
        if (bagCount) bagCount.textContent = String(count);
    };

    let cartSyncQueue = Promise.resolve();
    const syncCart = () => {
        cartSyncQueue = cartSyncQueue.then(async () => {
            try {
                await submit('/api/cart', { items: getCart() }, 'PUT');
            } catch (error) {
                console.error('Could not save bag to the database.', error);
                const toast = document.getElementById('toast');
                if (toast) {
                    toast.textContent = 'Your bag could not be saved. Please check your connection.';
                    toast.classList.add('show');
                }
            }
        });
        return cartSyncQueue;
    };

    const updateCheckoutSummary = () => {
        const summary = document.getElementById('checkoutSummary');
        const form = document.getElementById('orderForm');
        if (!summary || !form) return;

        const cart = getCart();
        summary.replaceChildren();
        if (!cart.length) {
            summary.textContent = 'Your bag is empty. Add a piece before checking out.';
            form.hidden = true;
            return;
        }

        form.hidden = false;
        let total = 0;
        const products = (() => {
            try {
                const parsed = JSON.parse(localStorage.getItem('bandilki-products') || '[]');
                return Array.isArray(parsed) ? parsed : [];
            } catch (error) {
                console.error('Could not read the product list.', error);
                return [];
            }
        })();
        cart.forEach(item => {
            const product = products.find(candidate => Number(candidate.id) === Number(item.id));
            if (!product) return;
            const quantity = Number(item.qty) || 0;
            total += Number(product.price) * quantity;
            const line = document.createElement('div');
            line.textContent = `${product.name} × ${quantity} — Rs ${(Number(product.price) * quantity).toFixed(2)}`;
            summary.append(line);
        });
        const totalLine = document.createElement('strong');
        totalLine.textContent = `Total — Rs ${total.toFixed(2)} (confirmed at order placement)`;
        summary.append(totalLine);
    };

    const closeBackdrop = backdrop => {
        if (backdrop) backdrop.hidden = true;
    };

    const openAccount = () => {
        showBackdrop('accountBackdrop');
        const field = document.getElementById(currentUser ? 'accountLogout' : 'accountEmail');
        if (field && !field.hidden) field.focus();
    };

    document.addEventListener('click', event => {
        const target = event.target instanceof Element ? event.target : null;
        if (!target) return;

        const orderStar = target.closest('[data-order-rating]');
        if (orderStar) {
            event.preventDefault();
            event.stopImmediatePropagation();
            const form = document.getElementById('orderRatingForm');
            const rating = Number(orderStar.dataset.orderRating);
            if (!form || rating < 1 || rating > 5) return;
            form.dataset.selectedRating = String(rating);
            form.querySelectorAll('[data-order-rating]').forEach(button => {
                const selected = Number(button.dataset.orderRating) <= rating;
                button.classList.toggle('selected', selected);
                button.setAttribute('aria-pressed', String(Number(button.dataset.orderRating) === rating));
            });
            return;
        }

        if (target.closest('#cartBtn')) {
            event.preventDefault();
            event.stopImmediatePropagation();
            updateCheckoutSummary();
            message(document.getElementById('orderMessage'), '');
            showBackdrop('checkoutBackdrop');
            return;
        }
        if (target.closest('[data-track-open]')) {
            event.preventDefault();
            event.stopImmediatePropagation();
            message(document.getElementById('trackingResult'), '');
            showBackdrop('trackOrderBackdrop');
            return;
        }
        if (target.closest('[data-contact-open]')) {
            event.preventDefault();
            event.stopImmediatePropagation();
            showBackdrop('contactBackdrop');
            return;
        }
        if (target.closest('[data-close-store-dialog]')) {
            closeBackdrop(target.closest('.store-dialog-backdrop'));
            return;
        }
        const backdrop = target.closest('.store-dialog-backdrop');
        if (backdrop && target === backdrop) {
            closeBackdrop(backdrop);
            return;
        }
        if (target.closest('#accountClose')) {
            closeBackdrop(document.getElementById('accountBackdrop'));
            return;
        }
        if (target.closest('#accountBackdrop') && target.id === 'accountBackdrop') {
            closeBackdrop(target);
            return;
        }
        if (target.closest('#accountBtn')) {
            event.preventDefault();
            event.stopImmediatePropagation();
            openAccount();
            return;
        }
        if (target.closest('#accountSwitch')) {
            event.preventDefault();
            event.stopImmediatePropagation();
            setAccountMode(!signupMode);
            const title = document.getElementById('accountTitle');
            const copy = document.querySelector('#accountBackdrop .account-card>p');
            const submitButton = document.getElementById('accountSubmit');
            const toggle = document.getElementById('accountSwitch');
            if (title) title.textContent = signupMode ? 'Create your account' : 'Welcome back';
            if (copy) copy.textContent = signupMode
                ? 'Create an account to keep your little treasures close.'
                : 'Sign in to keep your little treasures close.';
            if (submitButton) submitButton.textContent = signupMode ? 'Create account' : 'Continue';
            if (toggle) toggle.textContent = signupMode ? 'Back to sign in' : 'Create an account';
            message(document.getElementById('accountMessage'), '');
            return;
        }
        if (target.closest('#accountLogout')) {
            event.preventDefault();
            event.stopImmediatePropagation();
            request('/api/session', { method: 'DELETE' })
                .then(() => setSignedIn(null))
                .catch(error => message(document.getElementById('accountMessage'), error.message, true));
        }
    }, true);

    document.addEventListener('click', event => {
        const target = event.target instanceof Element ? event.target : null;
        if (target?.closest('[data-add]')) {
            void syncCart();
        }
    });

    document.addEventListener('submit', async event => {
        const form = event.target;
        if (!(form instanceof HTMLFormElement)) return;
        const supported = new Set([
            'accountForm', 'orderForm', 'orderRatingForm', 'trackOrderForm', 'contactForm',
            'newsletterForm', 'feedbackForm'
        ]);
        if (!supported.has(form.id)) return;
        event.preventDefault();
        event.stopImmediatePropagation();
        setBusy(form, true);

        try {
            if (form.id === 'accountForm') {
                const signup = !document.getElementById('accountNameWrap').hidden;
                const result = await submit(signup ? '/api/accounts' : '/api/session', formData(form));
                setSignedIn(result.user);
                message(document.getElementById('accountMessage'), signup
                    ? 'Your account is ready.'
                    : 'You are signed in.');
                document.getElementById('accountLogout').focus();
            } else if (form.id === 'orderForm') {
                const orderData = formData(form);
                const result = await submit('/api/orders', {
                    ...orderData,
                    items: getCart()
                });
                storeCart([]);
                await syncCart();
                form.reset();
                updateCheckoutSummary();
                const ratingForm = document.getElementById('orderRatingForm');
                ratingForm.elements.orderId.value = result.order.id;
                ratingForm.elements.phone.value = orderData.phone;
                ratingForm.dataset.selectedRating = '';
                ratingForm.hidden = false;
                ratingForm.querySelectorAll('[data-order-rating]').forEach(button => {
                    button.classList.remove('selected');
                    button.setAttribute('aria-pressed', 'false');
                });
                message(document.getElementById('orderRatingMessage'), '');
                message(
                    document.getElementById('orderMessage'),
                    `Order ${result.order.id} placed. Save this number to track your order.`
                );
            } else if (form.id === 'orderRatingForm') {
                const rating = Number(form.dataset.selectedRating || 0);
                if (!rating) {
                    message(document.getElementById('orderRatingMessage'), 'Choose a star rating first.', true);
                    return;
                }
                const result = await submit('/api/reviews', {
                    ...formData(form),
                    rating
                });
                form.reset();
                form.hidden = true;
                let reviews = [];
                try {
                    reviews = JSON.parse(localStorage.getItem('bandilki-reviews') || '[]');
                    if (!Array.isArray(reviews)) reviews = [];
                } catch (error) {
                    console.error('Could not read saved reviews.', error);
                }
                reviews.unshift(result.review);
                localStorage.setItem('bandilki-reviews', JSON.stringify(reviews));
                if (typeof window.showReview === 'function') window.showReview(0);
                message(document.getElementById('orderRatingMessage'), 'Thank you for rating your order.');
            } else if (form.id === 'trackOrderForm') {
                const data = formData(form);
                const query = new URLSearchParams(data);
                const result = await request('/api/orders/track?' + query.toString());
                const order = result.order;
                const detail = result.items.map(item =>
                    `${item.product_name} × ${item.quantity}`
                ).join(', ');
                message(
                    document.getElementById('trackingResult'),
                    `${order.id} — ${order.status}; Rs ${Number(order.total).toFixed(2)}. ${detail}`
                );
            } else if (form.id === 'contactForm') {
                const result = await submit('/api/contact', formData(form));
                form.reset();
                message(document.getElementById('contactMessage'), result.message);
            } else if (form.id === 'newsletterForm') {
                const result = await submit('/api/newsletter', formData(form));
                form.reset();
                message(document.getElementById('newsletterMessage'), result.message);
            } else if (form.id === 'feedbackForm') {
                const rating = form.querySelectorAll('#ratingStars button.selected').length;
                if (!rating) {
                    message(document.getElementById('formMessage'), 'Choose a star rating first.', true);
                    return;
                }
                const reviewData = new FormData(form);
                reviewData.set('name', document.getElementById('reviewName').value.trim() || 'Bandilki customer');
                reviewData.set('rating', String(rating));
                reviewData.set('note', document.getElementById('reviewText').value.trim());
                const result = await request('/api/reviews', { method: 'POST', body: reviewData });
                let reviews = [];
                try {
                    reviews = JSON.parse(localStorage.getItem('bandilki-reviews') || '[]');
                    if (!Array.isArray(reviews)) reviews = [];
                } catch (error) {
                    console.error('Could not read saved reviews.', error);
                }
                reviews.unshift(result.review);
                localStorage.setItem('bandilki-reviews', JSON.stringify(reviews));
                form.reset();
                form.querySelectorAll('#ratingStars button').forEach(button => button.classList.remove('selected'));
                if (typeof window.showReview === 'function') window.showReview(0);
                message(document.getElementById('formMessage'), 'Thank you for sharing your experience.');
            }
        } catch (error) {
            const ids = {
                accountForm: 'accountMessage',
                orderForm: 'orderMessage',
                orderRatingForm: 'orderRatingMessage',
                trackOrderForm: 'trackingResult',
                contactForm: 'contactMessage',
                newsletterForm: 'newsletterMessage',
                feedbackForm: 'formMessage'
            };
            message(document.getElementById(ids[form.id]), error.message, true);
        } finally {
            setBusy(form, false);
        }
    }, true);

    document.addEventListener('keydown', event => {
        if (event.key === 'Escape') {
            document.querySelectorAll('.store-dialog-backdrop:not([hidden])').forEach(closeBackdrop);
            closeBackdrop(document.getElementById('accountBackdrop'));
        }
    });

    const restoreServerState = async () => {
        try {
            const session = await request('/api/session');
            if (session.user) setSignedIn(session.user);
            const catalog = await request('/api/products');
            if (typeof products !== 'undefined') {
                products = catalog.products;
                renderProducts();
            }
            const categories = await request('/api/categories');
            if (typeof window.setStoreCategories === 'function') {
                window.setStoreCategories(categories.categories, categories.icons);
            }
            const result = await request('/api/cart');
            const localCart = getCart();
            const serverCart = result.items.map(item => ({ id: item.id, qty: item.qty }));
            if (serverCart.length || !localCart.length) {
                storeCart(serverCart);
            } else {
                await syncCart();
            }
            const savedReviews = await request('/api/reviews');
            localStorage.setItem('bandilki-reviews', JSON.stringify(savedReviews.reviews));
            if (savedReviews.reviews.length && typeof window.showReview === 'function') {
                window.showReview(0);
            }
        } catch (error) {
            console.error('Could not restore the saved store session.', error);
            const toast = document.getElementById('toast');
            if (toast) {
                toast.textContent = 'Store services are unavailable. Start the local server to save orders and account details.';
                toast.classList.add('show');
            }
        }
    };

    void restoreServerState();
})();
