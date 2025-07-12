/**
 * Unified Cart System for Restaurant Management
 * Handles all cart operations across different pages
 */

// Global cart state
let unifiedCart = [];

// Cart configuration
const CART_CONFIG = {
    storageKey: 'restaurant_cart',
    maxQuantity: 99,
    currency: window.systemSettings?.currency || 'EGP'
};

// Initialize cart system
function initializeCart() {
    // Load cart from localStorage
    loadCartFromStorage();
    // Update cart display
    updateCartDisplay();
    // Update cart count in navbar
    updateCartCount();
}

// Load cart from localStorage
function loadCartFromStorage() {
    try {
        const savedCart = localStorage.getItem(CART_CONFIG.storageKey);
        if (savedCart) {
            const cartData = JSON.parse(savedCart);
            // Clean up invalid items (those with timestamp IDs)
            unifiedCart = cartData.filter(item => {
                const itemId = parseInt(item.id);
                const isValid = !isNaN(itemId) && itemId < 1000000;
                if (!isValid) {
                    console.log('Removing invalid cart item with ID:', item.id);
                }
                return isValid;
            });

            // Save cleaned cart back to storage if we removed items
            if (unifiedCart.length !== cartData.length) {
                console.log(`Cleaned cart: removed ${cartData.length - unifiedCart.length} invalid items`);
                saveCartToStorage();
            }
        }
    } catch (error) {
        console.error('Error loading cart from storage:', error);
        unifiedCart = [];
    }
}

// Save cart to localStorage
function saveCartToStorage() {
    try {
        localStorage.setItem(CART_CONFIG.storageKey, JSON.stringify(unifiedCart));
    } catch (error) {
        console.error('Error saving cart to storage:', error);
    }
}

// Utility function for notifications
function safeShowNotification(title, message, type = 'info') {
    if (typeof showNotification === 'function') {
        showNotification(title, message, type);
    } else if (typeof window.RestaurantApp !== 'undefined' && window.RestaurantApp.showNotification) {
        window.RestaurantApp.showNotification(title, message, type);
    } else if (typeof showBaseNotification === 'function') {
        showBaseNotification(title, message, type);
    } else {
        // Visual feedback only - no browser alerts
        console.log(`Notification: ${title}: ${message}`);
    }
}

// Add item to cart
function addToCart(item) {
    // Validate item
    if (!item || !item.id || !item.name || !item.price) {
        console.error('Invalid item data:', item);
        safeShowNotification('Error', 'Invalid item data', 'danger');
        return false;
    }

    // Validate that item ID is a valid database ID (not a timestamp)
    const itemId = parseInt(item.id);
    if (isNaN(itemId) || itemId > 1000000) {
        console.error('Invalid item ID (appears to be timestamp):', item.id);
        safeShowNotification('Error', 'Invalid item. Please refresh the page and try again.', 'danger');
        return false;
    }

    // Check if item already exists in cart
    const existingItemIndex = unifiedCart.findIndex(cartItem => cartItem.id === item.id);

    if (existingItemIndex !== -1) {
        // Update quantity of existing item
        const newQuantity = unifiedCart[existingItemIndex].quantity + (item.quantity || 1);
        if (newQuantity <= CART_CONFIG.maxQuantity) {
            unifiedCart[existingItemIndex].quantity = newQuantity;
        } else {
            safeShowNotification('Warning', `Maximum quantity (${CART_CONFIG.maxQuantity}) reached for this item`, 'warning');
            return false;
        }
    } else {
        // Add new item to cart
        const cartItem = {
            id: item.id,
            name: item.name,
            price: parseFloat(item.price),
            quantity: item.quantity || 1,
            image: item.image || 'https://images.unsplash.com/photo-1546833999-b9f581a1996d?w=300&h=200&fit=crop',
            specialInstructions: item.specialInstructions || '',
            category: item.category || 'Main Courses'
        };
        unifiedCart.push(cartItem);
    }

    // Save to storage
    saveCartToStorage();

    // Update displays
    updateCartDisplay();
    updateCartCount();

    // Show success notification
    safeShowNotification('Success', `${item.name} added to cart`, 'success');

    return true;
}

// Remove item from cart
function removeFromCart(itemId) {
    const itemIndex = unifiedCart.findIndex(item => item.id === itemId);
    if (itemIndex !== -1) {
        const removedItem = unifiedCart.splice(itemIndex, 1)[0];
        saveCartToStorage();
        updateCartDisplay();
        updateCartCount();
        safeShowNotification('Info', `${removedItem.name} removed from cart`, 'info');
        return true;
    }
    return false;
}

// Update item quantity in cart
function updateCartItemQuantity(itemId, newQuantity) {
    const itemIndex = unifiedCart.findIndex(item => item.id === itemId);
    if (itemIndex !== -1) {
        if (newQuantity <= 0) {
            removeFromCart(itemId);
        } else if (newQuantity <= CART_CONFIG.maxQuantity) {
            unifiedCart[itemIndex].quantity = newQuantity;
            saveCartToStorage();
            updateCartDisplay();
            updateCartCount();
        } else {
            safeShowNotification('Warning', `Maximum quantity (${CART_CONFIG.maxQuantity}) reached`, 'warning');
        }
    }
}

// Increase item quantity
function increaseCartQuantity(itemId) {
    const item = unifiedCart.find(item => item.id === itemId);
    if (item) {
        updateCartItemQuantity(itemId, item.quantity + 1);
    }
}

// Decrease item quantity
function decreaseCartQuantity(itemId) {
    const item = unifiedCart.find(item => item.id === itemId);
    if (item) {
        updateCartItemQuantity(itemId, item.quantity - 1);
    }
}

// Clear entire cart
function clearCart() {
    if (unifiedCart.length === 0) {
        safeShowNotification('Info', 'Cart is already empty', 'info');
        return;
    }

    // Show confirmation modal instead of browser confirm
    showClearCartConfirmationModal();
}

function showClearCartConfirmationModal() {
    const modalHtml = `
        <div class="modal fade" id="clearCartConfirmModal" tabindex="-1" aria-hidden="true">
            <div class="modal-dialog modal-dialog-centered">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title">
                            <i class="fas fa-exclamation-triangle text-warning me-2"></i>
                            Clear Cart
                        </h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        <p class="mb-0">Are you sure you want to clear your entire cart? This action cannot be undone.</p>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
                        <button type="button" class="btn btn-danger" onclick="confirmClearCart()">
                            <i class="fas fa-trash me-2"></i>Clear Cart
                        </button>
                    </div>
                </div>
            </div>
        </div>
    `;

    // Remove existing modal if any
    const existingModal = document.getElementById('clearCartConfirmModal');
    if (existingModal) {
        existingModal.remove();
    }

    // Add modal to body
    document.body.insertAdjacentHTML('beforeend', modalHtml);

    // Show modal
    const modal = new bootstrap.Modal(document.getElementById('clearCartConfirmModal'));
    modal.show();
}

function confirmClearCart() {
    unifiedCart = [];
    saveCartToStorage();
    updateCartDisplay();
    updateCartCount();
    safeShowNotification('Info', 'Cart cleared', 'info');

    // Hide modal
    const modal = bootstrap.Modal.getInstance(document.getElementById('clearCartConfirmModal'));
    if (modal) {
        modal.hide();
    }
}

// Get cart total
function getCartTotal() {
    return unifiedCart.reduce((total, item) => total + (item.price * item.quantity), 0);
}

// Get cart item count
function getCartItemCount() {
    return unifiedCart.reduce((count, item) => count + item.quantity, 0);
}

// Update cart count in navbar
function updateCartCount() {
    const cartCountElements = [
        document.getElementById('globalCartCount'),
        document.getElementById('cartCount'),
        document.querySelector('.cart-count'),
        document.querySelector('.cart-badge')
    ];

    const totalItems = getCartItemCount();

    cartCountElements.forEach(element => {
        if (element) {
            element.textContent = totalItems;
            // Always show the badge with the count (even if 0)
            element.style.display = 'flex';
        }
    });
}

// Update cart display in modal
function updateCartDisplay() {
    console.log('🔧 Updating cart display...');
    const cartContainers = [
        document.getElementById('globalCartItems')
    ];

    const cartTotalElements = [
        document.getElementById('globalCartTotal')
    ];

    const cartFooterActions = document.getElementById('cartFooterActions');

    // Show/hide clear cart button
    if (cartFooterActions) {
        cartFooterActions.style.display = unifiedCart.length > 0 ? 'block' : 'none';
    }

    // Update total
    const total = getCartTotal();
    cartTotalElements.forEach(element => {
        if (element) {
            element.textContent = `${total.toFixed(2)} ${CART_CONFIG.currency}`;
        }
    });

    // Update cart items display
    cartContainers.forEach((container, containerIndex) => {
        if (container) {
            console.log(`🔧 Updating container ${containerIndex}:`, container.id);
            if (unifiedCart.length === 0) {
                container.innerHTML = `
                    <div class="empty-cart-message">
                        <div class="empty-cart-icon">
                            <i class="fas fa-shopping-cart"></i>
                        </div>
                        <h5 class="empty-cart-title">Your cart is empty</h5>
                        <p class="empty-cart-text">Add some delicious items to get started!</p>
                        <a href="/customer/menu" class="hero-btn primary empty-cart-btn">Browse Menu</a>
                    </div>
                `;
            } else {
                let cartHTML = '';
                unifiedCart.forEach((item, index) => {
                    const itemHTML = generateCartItemHTML(item, index);
                    cartHTML += itemHTML;
                    console.log(`🔧 Generated HTML for item ${item.name}:`, itemHTML.includes('cart-item-edit'));
                });
                container.innerHTML = cartHTML;
                console.log(`🔧 Container ${container.id} updated with ${unifiedCart.length} items`);

                // Check if edit buttons are actually in the DOM
                const editButtons = container.querySelectorAll('.cart-item-edit');
                console.log(`🔧 Found ${editButtons.length} edit buttons in container ${container.id}`);
                editButtons.forEach((btn, idx) => {
                    console.log(`🔧 Edit button ${idx}:`, btn.getAttribute('data-item-id'), btn.onclick);
                });
            }
        }
    });
}

// Generate HTML for cart item
function generateCartItemHTML(item, index) {
    const html = `
        <div class="new-cart-item">
            <img src="${item.image}" class="cart-item-image" alt="${item.name}">
            <div class="cart-item-details">
                <div class="cart-item-name">${item.name}</div>
                <div class="cart-item-desc">${item.specialInstructions || item.category}</div>
                <div class="cart-item-price">${item.price.toFixed(2)} ${CART_CONFIG.currency}</div>
            </div>
            <div class="cart-item-controls">
                <div class="new-quantity-controls">
                    <button class="new-quantity-btn" onclick="decreaseCartQuantity('${item.id}')">-</button>
                    <span class="new-quantity-display">${item.quantity}</span>
                    <button class="new-quantity-btn" onclick="increaseCartQuantity('${item.id}')">+</button>
                </div>
                <div class="cart-item-actions">
                    <button class="cart-item-edit" data-item-id="${item.id}" onclick="editCartItem('${item.id}')" title="Edit quantity and special instructions">
                        <i class="fas fa-edit"></i> Edit
                    </button>
                    <button class="cart-item-remove" onclick="removeFromCart('${item.id}')" title="Remove from cart">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            </div>
        </div>
    `;
    return html;
}

// Open cart modal
function openCartModal() {
    console.log('Opening cart modal...');

    // Force refresh cart data before opening
    refreshCartDisplay();

    // Always use the global cart modal for consistency
    const globalModal = document.getElementById('globalCartModal');

    if (globalModal) {
        console.log('Found global cart modal');
        console.log('Cart items to display:', unifiedCart.length);
        const cartModal = new bootstrap.Modal(globalModal);
        cartModal.show();
    } else {
        console.error('Global cart modal not found!');
        safeShowNotification('Error', 'Cart modal not found', 'error');
    }
}

// Edit cart item functionality - redirects to item detail modal
function editCartItem(itemId) {
    console.log('🚨 EDIT BUTTON CLICKED! Item ID:', itemId);

    // Add click animation to the edit button
    const editButton = document.querySelector(`[data-item-id="${itemId}"]`);
    if (editButton) {
        editButton.classList.add('clicked');
        setTimeout(() => editButton.classList.remove('clicked'), 200);
    }

    // Find the item in the cart
    const item = unifiedCart.find(cartItem => cartItem.id === itemId);
    console.log('🔍 Looking for item with ID:', itemId);
    console.log('🔍 Current cart contents:', unifiedCart);
    console.log('🔍 Found item:', item);

    if (!item) {
        console.error('Item not found in cart!');
        safeShowNotification('Error', 'Item not found in cart', 'error');
        return;
    }

    // Check if we have the item detail modal available
    const itemDetailModal = document.getElementById('itemDetailModal');
    console.log('🔍 Looking for itemDetailModal:', !!itemDetailModal);
    console.log('🔍 All modals on page:', document.querySelectorAll('.modal').length);

    if (!itemDetailModal) {
        console.log('❌ itemDetailModal not found, using fallback modal');
        // Fallback: Create a simple modal for special instructions
        showEditInstructionsModal(item);
        return;
    }

    console.log('✅ itemDetailModal found, proceeding with modal method');

    try {
        // Close the global cart modal first
        const globalModal = document.getElementById('globalCartModal');
        if (globalModal) {
            const modalInstance = bootstrap.Modal.getInstance(globalModal);
            if (modalInstance) {
                modalInstance.hide();
            }
        }

        // Set up the item detail modal with current item data
        console.log('🔧 Setting modal data for item:', item);

        // Clear any existing data first
        document.getElementById('modalItemName').textContent = '';
        document.getElementById('modalItemIngredients').textContent = '';
        document.getElementById('modalItemPrice').textContent = '';
        document.getElementById('itemQuantity').textContent = '1';
        document.getElementById('specialInstructions').value = '';
        document.getElementById('modalTotalPrice').textContent = '0.00';

        // Set the actual item data
        document.getElementById('modalItemName').textContent = item.name;
        document.getElementById('modalItemIngredients').textContent = item.category || 'Main Course';
        document.getElementById('modalItemPrice').textContent = item.price.toFixed(2);
        document.getElementById('itemQuantity').textContent = item.quantity;
        document.getElementById('specialInstructions').value = item.specialInstructions || '';

        // Set the modal image
        const modalImage = document.getElementById('modalItemImage');
        if (modalImage) {
            modalImage.src = item.image || 'https://images.unsplash.com/photo-1504674900247-0877df9cc836?w=600&h=400&fit=crop';
            modalImage.onerror = function() {
                this.src = 'https://images.unsplash.com/photo-1504674900247-0877df9cc836?w=600&h=400&fit=crop';
            };
        }

        // Set category badge
        const categoryBadge = document.getElementById('modalItemCategory');
        if (categoryBadge) {
            categoryBadge.textContent = item.category || 'Main Course';
        }

        // Update modal total price
        const totalPrice = (item.price * item.quantity).toFixed(2);
        document.getElementById('modalTotalPrice').textContent = totalPrice;

        console.log('🔧 Modal data set - Name:', item.name, 'Price:', item.price, 'Qty:', item.quantity);

        // Store edit context - this tells the modal we're editing an existing item
        window.editingCartItem = {
            id: itemId,
            originalItem: { ...item }
        };

        // Change the button text and style to indicate editing
        const addToCartBtn = document.getElementById('addToCartModal');
        console.log('🔧 Found addToCartModal button:', !!addToCartBtn);
        if (addToCartBtn) {
            console.log('🔧 Changing button text to "Update Item"');
            addToCartBtn.innerHTML = '<i class="fas fa-shopping-cart"></i> Update Item - <span id="modalTotalPrice">' + totalPrice + '</span> EGP';
            addToCartBtn.style.background = '#28a745'; // Green for update
            addToCartBtn.style.borderColor = '#28a745';
        }

        // Show the item detail modal after a brief delay
        setTimeout(() => {
            const modal = new bootstrap.Modal(itemDetailModal);
            modal.show();
            console.log('Item detail modal opened for editing:', item.name);
        }, 300);

    } catch (error) {
        console.error('Error setting up edit modal:', error);
        safeShowNotification('Error', 'Could not open edit modal', 'error');
    }
}

// Checkout functionality
function proceedToCheckout() {
    console.log('Proceeding to checkout...', unifiedCart);

    if (unifiedCart.length === 0) {
        safeShowNotification('Warning', 'Your cart is empty!', 'warning');
        return;
    }

    console.log('Redirecting to checkout page...');
    // Redirect to checkout page
    window.location.href = '/customer/checkout';
}

// Initialize cart when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    console.log('Initializing unified cart system...');
    initializeCart();
    console.log('Cart initialized with', getCartItemCount(), 'items');
    console.log('Current cart contents:', unifiedCart);

    // Test item removed

    // Test checkout function availability
    if (typeof proceedToCheckout === 'function') {
        console.log('✓ proceedToCheckout function is available');
    } else {
        console.error('✗ proceedToCheckout function is NOT available');
    }

    // Test notification function availability
    if (typeof showNotification === 'function') {
        console.log('✓ showNotification function is available');
    } else if (typeof window.RestaurantApp !== 'undefined' && window.RestaurantApp.showNotification) {
        console.log('✓ RestaurantApp.showNotification is available');
    } else {
        console.warn('⚠ No notification function available, will use alert fallback');
    }

    // Add event delegation for edit buttons
    document.addEventListener('click', function(e) {
        console.log('🔧 Click detected on:', e.target);
        if (e.target.closest('.cart-item-edit')) {
            e.preventDefault();
            console.log('🔧 Edit button clicked via delegation!');
            const button = e.target.closest('.cart-item-edit');
            const itemId = button.getAttribute('data-item-id') || button.onclick?.toString().match(/'([^']+)'/)?.[1];
            console.log('🔧 Edit button clicked via delegation, item ID:', itemId);
            if (itemId) {
                editCartItem(itemId);
            } else {
                console.error('🔧 No item ID found on edit button');
            }
        }
    });

    // Debug test item removed
});

// Force refresh cart display
function refreshCartDisplay() {
    console.log('Forcing cart display refresh...');
    loadCartFromStorage();
    updateCartDisplay();
    updateCartCount();
    console.log('Cart refreshed. Current items:', unifiedCart.length);
}

// Test functions removed

// Reset item detail modal to default state
function resetItemDetailModal() {
    console.log('Resetting item detail modal...');

    // Store edit context before clearing for return navigation
    const wasEditing = !!window.editingCartItem;

    // Clear edit context
    if (window.editingCartItem) {
        console.log('Clearing edit context for item:', window.editingCartItem.id);
        delete window.editingCartItem;
    }

    // Reset button text and styling
    const addToCartBtn = document.getElementById('addToCartModal');
    if (addToCartBtn) {
        addToCartBtn.innerHTML = '<i class="fas fa-shopping-cart"></i> Add to Cart - <span id="modalTotalPrice">0.00</span> EGP';
        addToCartBtn.style.background = '';
        addToCartBtn.style.borderColor = '';
    }

    // Reset quantity to 1
    const qtyElement = document.getElementById('itemQuantity');
    if (qtyElement) {
        qtyElement.textContent = '1';
    }

    // Clear special instructions
    const instructionsElement = document.getElementById('specialInstructions');
    if (instructionsElement) {
        instructionsElement.value = '';
    }

    // Reset modal total price
    const modalTotalPrice = document.getElementById('modalTotalPrice');
    if (modalTotalPrice) {
        modalTotalPrice.textContent = '0.00';
    }

    console.log('Item detail modal reset to default state. Was editing:', wasEditing);
    return wasEditing;
}

// Export functions for global access
window.unifiedCart = unifiedCart;
window.addToCart = addToCart;
window.removeFromCart = removeFromCart;
window.updateCartItemQuantity = updateCartItemQuantity;
window.increaseCartQuantity = increaseCartQuantity;
window.decreaseCartQuantity = decreaseCartQuantity;
window.clearCart = clearCart;
window.openCartModal = openCartModal;
window.proceedToCheckout = proceedToCheckout;
window.getCartTotal = getCartTotal;
window.getCartItemCount = getCartItemCount;
window.refreshCartDisplay = refreshCartDisplay;
window.updateCartDisplay = updateCartDisplay;
window.editCartItem = editCartItem;
window.resetItemDetailModal = resetItemDetailModal;

// Fallback modal for editing instructions when itemDetailModal is not available
function showEditInstructionsModal(item) {
    const modalHtml = `
        <div class="modal fade" id="editInstructionsModal" tabindex="-1" aria-hidden="true">
            <div class="modal-dialog modal-dialog-centered">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title">
                            <i class="fas fa-edit me-2"></i>
                            Edit Special Instructions
                        </h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        <p class="mb-3">Edit special instructions for <strong>${item.name}</strong>:</p>
                        <div class="mb-3">
                            <label for="editInstructionsText" class="form-label">Special Instructions</label>
                            <textarea class="form-control" id="editInstructionsText" rows="3"
                                      placeholder="Enter any special instructions...">${item.specialInstructions || ''}</textarea>
                        </div>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
                        <button type="button" class="btn btn-primary" onclick="saveEditedInstructions('${item.id}')">
                            <i class="fas fa-save me-2"></i>Save Changes
                        </button>
                    </div>
                </div>
            </div>
        </div>
    `;

    // Remove existing modal if any
    const existingModal = document.getElementById('editInstructionsModal');
    if (existingModal) {
        existingModal.remove();
    }

    // Add modal to body
    document.body.insertAdjacentHTML('beforeend', modalHtml);

    // Show modal
    const modal = new bootstrap.Modal(document.getElementById('editInstructionsModal'));
    modal.show();

    // Focus on textarea
    setTimeout(() => {
        document.getElementById('editInstructionsText').focus();
    }, 300);
}

function saveEditedInstructions(itemId) {
    const newInstructions = document.getElementById('editInstructionsText').value;

    // Find and update the item
    const item = unifiedCart.find(cartItem => cartItem.id == itemId);
    if (item) {
        item.specialInstructions = newInstructions;
        saveCartToStorage();
        updateCartDisplay();
        safeShowNotification('Success', 'Item updated successfully', 'success');
    }

    // Hide modal
    const modal = bootstrap.Modal.getInstance(document.getElementById('editInstructionsModal'));
    if (modal) {
        modal.hide();
    }
}

window.showEditInstructionsModal = showEditInstructionsModal;
window.saveEditedInstructions = saveEditedInstructions;
window.showClearCartConfirmationModal = showClearCartConfirmationModal;
window.confirmClearCart = confirmClearCart;

