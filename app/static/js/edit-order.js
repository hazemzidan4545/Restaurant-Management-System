// Edit Order Modal Logic for Admin Orders Page

// Helper function to get CSRF token
function getCSRFToken() {
    // Look for meta tag with csrf-token
    const tokenMeta = document.querySelector('meta[name="csrf-token"]');
    if (tokenMeta) {
        return tokenMeta.getAttribute('content');
    }
    
    // If not found in meta, try to find it in a form
    const tokenInput = document.querySelector('input[name="csrf_token"]');
    if (tokenInput) {
        return tokenInput.value;
    }
    
    return '';
}

document.addEventListener('DOMContentLoaded', function() {
    console.log('Edit order script loaded');
      // Check if modal is already visible (shouldn't be)
    const modal = document.getElementById('editOrderModal');
    if (modal) {
        const modalInstance = bootstrap.Modal.getInstance(modal);
        if (modalInstance) {
            console.warn('Modal instance exists on page load - hiding it');
            modalInstance.hide();
        }
    }
    
    // Use event delegation for edit buttons
    document.body.addEventListener('click', function(e) {
        const editBtn = e.target.closest('.edit-order-btn');
        if (editBtn) {
            const orderId = editBtn.dataset.orderId;
            console.log('Edit button clicked for order:', orderId);
            openEditOrderModal(orderId);
            e.preventDefault(); // Prevent any default behavior
            e.stopPropagation(); // Stop event bubbling
        }
    });

    // Make sure modal exists before adding event listener
    const saveOrderBtn = document.getElementById('saveOrderEditBtn');
    if (saveOrderBtn) {
        console.log('Save order button found');
        saveOrderBtn.addEventListener('click', function() {
            console.log('Save button clicked');
            saveOrderEdit();
        });
    } else {
        console.error('Save order button not found in the DOM');
    }
    
    // Check if edit buttons exist
    const editButtons = document.querySelectorAll('.edit-order-btn');
    console.log(`Found ${editButtons.length} edit buttons`);
});

function openEditOrderModal(orderId) {
    // Fetch order details with additional debugging
    console.log(`Fetching order details for ID: ${orderId}`);
    
    const apiUrl = `/api/orders/${orderId}`;
    console.log(`API URL: ${apiUrl}`);
    
    // Show processing indicator
    if (window.RestaurantApp && window.RestaurantApp.showLoading) {
        window.RestaurantApp.showLoading('body');
    }
    
    fetch(apiUrl, {
        method: 'GET',
        headers: {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'X-CSRFToken': getCSRFToken()
        },
        credentials: 'same-origin'
    })
        .then(response => {
            console.log('Response status:', response.status);
            console.log('Response headers:', [...response.headers.entries()]);
            
            if (!response.ok) {
                return response.text().then(text => {
                    console.error('Error response body:', text);
                    throw new Error(`HTTP error! status: ${response.status}, message: ${text || 'No error message'}`);
                });
            }
            return response.json();
        })        .then(response => {
            console.log('Order details received:', response);
            
            // Hide loading indicator
            if (window.RestaurantApp && window.RestaurantApp.hideLoading) {
                window.RestaurantApp.hideLoading();
            }
            
            // Extract order data from API response
            const order = response.data || response;
            
            document.getElementById('editOrderId').value = order.order_id;
            document.getElementById('editOrderStatus').value = order.status || 'new';
            document.getElementById('editOrderNotes').value = order.notes || '';
              // Display order total in EGP
            const totalElement = document.getElementById('editOrderTotal');
            console.log('Total element found:', totalElement);
            console.log('Order data:', order);
            console.log('Total amount from order:', order.total_amount);
            
            if (totalElement) {
                if (order.total_amount !== undefined && order.total_amount !== null) {
                    const totalAmount = parseFloat(order.total_amount).toFixed(2);
                    totalElement.textContent = `${totalAmount} EGP`;
                    console.log('Order total set to:', `${totalAmount} EGP`);
                } else {
                    totalElement.textContent = '0.00 EGP';
                    console.log('No total_amount found, set to 0.00 EGP');
                }
            } else {
                console.error('Total element with ID "editOrderTotal" not found in DOM');
            }
            
            renderEditOrderItems(order.items);
            
            // Update status field styling after setting value
            const statusSelect = document.getElementById('editOrderStatus');
            if (statusSelect) {
                statusSelect.setAttribute('value', statusSelect.value);
            }
              // Show modal using Bootstrap 5 Modal API
            const modalElement = document.getElementById('editOrderModal');
            if (!modalElement) {
                console.error('Modal element not found in the DOM');
                throw new Error('Modal element not found');
            }
              console.log('Modal element found, showing with Bootstrap Modal');
            
            // Initialize and show Bootstrap modal WITHOUT any backdrop
            let modal = bootstrap.Modal.getInstance(modalElement);
            if (modal) {
                modal.dispose(); // Remove any existing instance
            }
            
            // Remove any existing backdrops first
            document.querySelectorAll('.modal-backdrop, .custom-modal-backdrop').forEach(backdrop => {
                backdrop.remove();
            });
            
            // Create new modal instance with no backdrop
            modal = new bootstrap.Modal(modalElement, {
                backdrop: false,  // No backdrop at all
                keyboard: true,
                focus: true
            });
            
            // Force modal to be visible and on top with background
            modalElement.style.cssText = `
                display: block !important;
                z-index: 999999 !important;
                position: fixed !important;
                top: 0 !important;
                left: 0 !important;
                width: 100% !important;
                height: 100% !important;
                pointer-events: auto !important;
                background-color: rgba(0, 0, 0, 0.5) !important;
            `;
            
            modalElement.classList.add('show');
            
            // Ensure modal dialog is centered and on top
            const modalDialog = modalElement.querySelector('.modal-dialog');
            if (modalDialog) {
                modalDialog.style.cssText = `
                    z-index: 1000000 !important;
                    position: relative !important;
                    margin: 1.75rem auto !important;
                    pointer-events: auto !important;
                `;
            }
            
            // Ensure modal content is visible
            const modalContent = modalElement.querySelector('.modal-content');
            if (modalContent) {
                modalContent.style.cssText = `
                    z-index: 1000001 !important;
                    position: relative !important;
                    background-color: white !important;
                    pointer-events: auto !important;
                    border-radius: 15px !important;
                    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3) !important;
                `;
            }
            
            modal.show();
            
            console.log('Modal shown without blocking backdrop');
            
            // Focus the notes field
            setTimeout(() => {
                document.getElementById('editOrderNotes').focus();
            }, 100);
        })
        .catch(error => {
            console.error('Error loading order details:', error);
            
            // Hide loading indicator
            if (window.RestaurantApp && window.RestaurantApp.hideLoading) {
                window.RestaurantApp.hideLoading();
            }
            
            if (window.RestaurantApp && window.RestaurantApp.showNotification) {
                window.RestaurantApp.showNotification('Error', 'Failed to load order details: ' + error.message, 'danger');
            } else {
                console.error('Error: Failed to load order details: ' + error.message);
            }
        });
}

function renderEditOrderItems(items) {
    const container = document.getElementById('editOrderItemsList');
    container.innerHTML = '';
    items.forEach((item, idx) => {
        const row = document.createElement('div');
        row.className = 'd-flex align-items-center mb-2 gap-2';
        row.innerHTML = `
            <span class="flex-grow-1">${item.name}</span>
            <input type="number" class="form-control form-control-sm" style="width:80px" min="1" value="${item.quantity}" data-idx="${idx}" />
            <input type="text" class="form-control form-control-sm" style="width:180px" placeholder="Note" value="${item.note || ''}" data-idx="${idx}" />
        `;
        container.appendChild(row);
    });
}

function saveOrderEdit() {
    console.log('Save order edit function called');
    
    const orderId = document.getElementById('editOrderId').value;
    if (!orderId) {
        console.error('No order ID found in form');
        alert('Error: Cannot save order - no order ID found');
        return;
    }
    
    console.log('Saving order with ID:', orderId);
      // Get form values
    const notes = document.getElementById('editOrderNotes').value;
    const status = document.getElementById('editOrderStatus').value;
    console.log('Order notes:', notes);
    console.log('Order status:', status);
    
    // Collect item data from form fields
    const items = [];
    const itemRows = document.querySelectorAll('#editOrderItemsList > div');
    console.log(`Processing ${itemRows.length} order items`);
    
    if (itemRows.length === 0) {
        console.warn('No order items found in the form');
    }
    
    // Debug: log all form elements
    console.log('Edit Order Form Elements:');
    const formElements = document.getElementById('editOrderForm').elements;
    for (let i = 0; i < formElements.length; i++) {
        const element = formElements[i];
        console.log(`Element ${i}:`, element.id, element.name, element.value);
    }
    
    itemRows.forEach((row, idx) => {
        try {
            const quantityInput = row.querySelector('input[type="number"]');
            const noteInput = row.querySelector('input[type="text"]');
            const nameSpan = row.querySelector('span');
            
            if (!quantityInput || !nameSpan) {
                console.error('Missing required inputs in item row', idx);
                return;
            }
            
            const quantity = parseInt(quantityInput.value) || 1;
            const note = noteInput ? noteInput.value : '';
            const name = nameSpan.textContent;            // Check if we have the id from the cached item data
            if (!window._editOrderLastItems || !window._editOrderLastItems[idx]) {
                console.error(`Missing item id reference for item ${idx}: ${name}`);
                console.error('Available cached items:', window._editOrderLastItems);
                return;
            }
            
            // Additional validation
            if (!window._editOrderLastItems[idx].id) {
                console.error(`Item ${idx} exists but has no id:`, window._editOrderLastItems[idx]);
                return;
            }
              items.push({
                item_id: window._editOrderLastItems[idx].id,  // Use 'id' from API response
                quantity,
                note
            });
            console.log(`Added item: ${name}, qty: ${quantity}, item_id: ${window._editOrderLastItems[idx].id}`);
        } catch (e) {
            console.error(`Error processing item row ${idx}:`, e);
        }
    });
    
    if (items.length === 0) {
        console.error('No valid items to save');
        alert('Error: No valid items to save');
        return;
    }
    
    console.log('Saving order edit for ID:', orderId);
    console.log('Items to save:', items);
    console.log('Notes:', notes);
    console.log('Status:', status);
    
    // Additional debugging - log the items structure
    items.forEach((item, idx) => {
        console.log(`Item ${idx}:`, item);
    });
    console.log('Items to save:', items);
    
    // Show saving indicator
    if (window.RestaurantApp && window.RestaurantApp.showLoading) {
        window.RestaurantApp.showLoading('body');
    }
    
    // Disable the save button to prevent double-submission
    const saveBtn = document.getElementById('saveOrderEditBtn');
    if (saveBtn) {
        saveBtn.disabled = true;
        saveBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Saving...';
    }
    
    fetch(`/api/orders/${orderId}`, {
        method: 'PUT',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCSRFToken()
        },        body: JSON.stringify({ 
            items: items, 
            notes: notes,
            status: status
        })
    })
    .then(response => {
        console.log('Update response status:', response.status);
          if (!response.ok) {
            return response.text().then(text => {
                console.error('Error response:', text);
                
                // Try to parse as JSON for better error messages
                try {
                    const errorData = JSON.parse(text);
                    const errorMsg = errorData.message || errorData.error || text;
                    throw new Error(`HTTP error! status: ${response.status}, message: ${errorMsg}`);
                } catch (parseError) {
                    // If not JSON, use the raw text
                    throw new Error(`HTTP error! status: ${response.status}, message: ${text || 'No error message'}`);
                }
            });
        }
        return response.json();
    })
    .then(data => {
        console.log('Order update response:', data);
        
        // Hide loading indicator
        if (window.RestaurantApp && window.RestaurantApp.hideLoading) {
            window.RestaurantApp.hideLoading();
        }
        
        // Re-enable save button
        if (saveBtn) {
            saveBtn.disabled = false;
            saveBtn.innerHTML = '<i class="fas fa-save me-2"></i>Save Changes';
        }
          if (data.status === 'success' && data.data && data.data.order_id) {
            // Show success message
            if (window.RestaurantApp && window.RestaurantApp.showNotification) {
                window.RestaurantApp.showNotification('Success', 'Order updated successfully', 'success');
            } else {
                alert('Success: Order updated successfully');
            }
            
            // Update the UI with new data instead of reloading
            updateOrderInTable(data.data);
              // Hide modal and clean up properly
            closeEditOrderModal();
        } else {
            // Show error message
            const errorMsg = data.message || data.error || 'Failed to update order';
            console.error('Error updating order:', errorMsg);
            
            if (window.RestaurantApp && window.RestaurantApp.showNotification) {
                window.RestaurantApp.showNotification('Error', errorMsg, 'danger');
            } else {
                alert('Error: ' + errorMsg);
            }
        }
    })    .catch(error => {
        console.error('Error updating order:', error);
        
        // Hide loading indicator
        if (window.RestaurantApp && window.RestaurantApp.hideLoading) {
            window.RestaurantApp.hideLoading();
        }
        
        // Re-enable save button
        if (saveBtn) {
            saveBtn.disabled = false;
            saveBtn.innerHTML = '<i class="fas fa-save me-2"></i>Save Changes';
        }
        
        // Show detailed error message
        let errorMessage = 'Failed to update order';
        if (error.message) {
            errorMessage = error.message;
        }
        
        console.error('Detailed error:', errorMessage);
        
        if (window.RestaurantApp && window.RestaurantApp.showNotification) {
            window.RestaurantApp.showNotification('Error', errorMessage, 'danger');
        } else {
            console.error('Error: ' + errorMessage);
        }
    });
}

// Function to close modal properly
function closeEditOrderModal() {
    const modalElement = document.getElementById('editOrderModal');
    if (modalElement) {
        // Get the Bootstrap modal instance
        const modal = bootstrap.Modal.getInstance(modalElement);
        if (modal) {
            try {
                modal.hide();
                modal.dispose();
            } catch (err) {
                console.warn('Error hiding/disposing modal:', err);
            }
        }
        
        // Clean up modal styling
        modalElement.style.cssText = '';
        modalElement.classList.remove('show');
        modalElement.style.display = 'none';
        
        // Remove any backdrops
        document.querySelectorAll('.modal-backdrop, .custom-modal-backdrop').forEach(backdrop => {
            backdrop.remove();
        });
        
        // Force restore body scrolling capability
        document.body.classList.remove('modal-open');
        document.body.style.overflow = 'auto';
        document.body.style.paddingRight = '0';        
        
        // Remove any lingering modal states
        document.documentElement.classList.remove('modal-open');
        document.documentElement.style.overflow = 'auto';
        
        // Final check - if anything has position:fixed, clean it up
        const fixedElements = document.querySelectorAll('[style*="position: fixed"]');
        fixedElements.forEach(el => {
            if (el.classList.contains('modal') || el.classList.contains('modal-backdrop')) {
                el.style.position = '';
            }
        });
        
        console.log('Modal closed, scroll should be restored');
    }
}

// Add event listeners for cancel and close buttons
document.addEventListener('DOMContentLoaded', function() {
    // Handle cancel button
    const cancelBtn = document.querySelector('#editOrderModal [data-bs-dismiss="modal"]');
    if (cancelBtn) {
        cancelBtn.addEventListener('click', closeEditOrderModal);
    }
    
    // Handle X button
    const closeBtn = document.querySelector('#editOrderModal .btn-close');
    if (closeBtn) {
        closeBtn.addEventListener('click', closeEditOrderModal);
    }
    
    // Add event listener for Bootstrap's modal hidden event
    const modalElement = document.getElementById('editOrderModal');
    if (modalElement) {
        modalElement.addEventListener('hidden.bs.modal', function() {
            // Ensure body can scroll again when modal is hidden by any means
            document.body.classList.remove('modal-open');
            document.body.style.overflow = '';
            document.body.style.paddingRight = '';
            document.documentElement.classList.remove('modal-open');
            document.documentElement.style.overflow = '';
            
            // Remove any backdrops that might still be present
            document.querySelectorAll('.modal-backdrop').forEach(backdrop => {
                backdrop.remove();
            });
        });
    }
    
    // Handle ESC key
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            const modal = document.getElementById('editOrderModal');
            if (modal && modal.classList.contains('show')) {
                closeEditOrderModal();
            }
        }
    });
});

// Store last loaded items for mapping item_id
window._editOrderLastItems = [];

function renderEditOrderItems(items) {
    // Store the items for reference
    window._editOrderLastItems = items;
    
    const container = document.getElementById('editOrderItemsList');
    if (!container) {
        console.error('Order items container not found');
        return;
    }
    
    // Clear existing content
    container.innerHTML = '';
    
    if (!items || items.length === 0) {
        // Show a message if no items
        const emptyMessage = document.createElement('div');
        emptyMessage.className = 'alert alert-info';
        emptyMessage.textContent = 'No items in this order.';
        container.appendChild(emptyMessage);
        return;
    }
    
    // Create a nicely styled list of items
    items.forEach((item, idx) => {
        const row = document.createElement('div');
        row.className = 'd-flex align-items-center mb-3 p-2 border rounded';
        row.style.backgroundColor = '#f8f9fa';
        
        // Prepare price display
        const price = parseFloat(item.unit_price);
        const formattedPrice = new Intl.NumberFormat('en-EG', {
            style: 'currency',
            currency: 'EGP'
        }).format(price);
        
        row.innerHTML = `
            <div class="d-flex flex-column flex-grow-1">
                <span class="fw-bold">${item.name}</span>
                <small class="text-muted">${formattedPrice} each</small>
            </div>
            <div class="d-flex align-items-center gap-2">
                <label for="quantity-${idx}" class="form-label mb-0 me-1">Qty:</label>
                <input type="number" id="quantity-${idx}" class="form-control form-control-sm" 
                    style="width:60px" min="1" max="99" value="${item.quantity}" data-idx="${idx}" />
                
                <input type="text" class="form-control form-control-sm" 
                    style="width:150px" placeholder="Special instructions" 
                    value="${item.note || ''}" data-idx="${idx}" />
            </div>
        `;
        container.appendChild(row);
        
        // Add event listeners for the quantity input
        const quantityInput = row.querySelector(`#quantity-${idx}`);
        if (quantityInput) {
            quantityInput.addEventListener('change', function() {
                // Validate min/max values
                if (parseInt(this.value) < 1) this.value = 1;
                if (parseInt(this.value) > 99) this.value = 99;
            });
        }
    });
}

// Function to update order in the table without page reload
function updateOrderInTable(orderData) {
    try {
        console.log('Updating order in table with data:', orderData);
        
        // Find the order row in the table
        const orderRow = document.querySelector(`tr[data-order-id="${orderData.order_id}"]`);
        if (!orderRow) {
            console.log('Order row not found, reloading page...');
            setTimeout(() => location.reload(), 500);            return;
        }        // Update status badge
        const statusCell = orderRow.querySelector('.status-badge');
        if (statusCell && orderData.status) {
            // Get all classes except status-specific ones (but keep status-badge)
            const classes = statusCell.className.split(' ');
            const filteredClasses = classes.filter(cls => !cls.startsWith('status-') || cls === 'status-badge');
            
            // Add new status class and text - keep original status format
            const statusClass = orderData.status.toLowerCase().replace(' ', '-');
            filteredClasses.push(`status-${statusClass}`);
            
            statusCell.className = filteredClasses.join(' ');
            statusCell.textContent = orderData.status; // Keep original status text format
            
            // Update the data-status attribute on the row for filtering
            orderRow.dataset.status = statusClass;
        }
        
        // Update total amount
        const totalCell = orderRow.querySelector('.order-total');
        if (totalCell && orderData.total_amount) {
            totalCell.textContent = `${parseFloat(orderData.total_amount).toFixed(2)} EGP`;
        }
          // Add a subtle highlight effect to show the row was updated
        orderRow.style.backgroundColor = '#d4edda';
        setTimeout(() => {
            orderRow.style.backgroundColor = '';
        }, 2000);
        
        // Reapply any active filters after updating the row
        if (window.OrderFilters && typeof window.OrderFilters.applyFilters === 'function') {
            window.OrderFilters.applyFilters();
        }
        
        console.log('Order table updated successfully');
        
    } catch (error) {
        console.error('Error updating order in table:', error);
        // Fallback to page reload if update fails
        setTimeout(() => location.reload(), 500);
    }
}
