// Rider Dashboard JavaScript

// Variables set by Jinja2 template
const csrfTokenValue = window.csrfTokenValue;
const updateStatusUrl = window.updateStatusUrl;

// WebSocket connection
let socket;
let isConnected = false;

// Function to accept an order
function acceptOrder(orderId) {
    if (!confirm('Are you sure you want to accept this order?')) {
        return;
    }
    
    const riderId = document.body.getAttribute('data-rider-id');
    if (!riderId) {
        showNotification('Error: Rider ID not found. Please refresh the page and try again.', 'danger');
        return;
    }
    
    fetch('/rider/accept-order', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfTokenValue
        },
        body: JSON.stringify({
            order_id: orderId,
            rider_id: riderId
        })
    })
    .then(response => {
        if (!response.ok) {
            return response.json().then(err => { throw err; });
        }
        return response.json();
    })
    .then(data => {
        if (data.success) {
            // Remove the order card from available orders
            const orderCard = document.querySelector(`[data-order-id="${orderId}"]`);
            if (orderCard) {
                // Add a success animation before removing
                orderCard.classList.add('border-success');
                orderCard.style.transition = 'all 0.5s ease';
                orderCard.style.opacity = '0';
                
                setTimeout(() => {
                    orderCard.remove();
                    
                    // Show no orders message if no more orders
                    const container = document.getElementById('availableOrdersContainer');
                    const noOrdersMessage = document.getElementById('noOrdersMessage');
                    if (container && noOrdersMessage && container.children.length === 1) {
                        noOrdersMessage.style.display = 'block';
                    }
                    
                    // Show success notification
                    showNotification(data.message || 'Order accepted successfully!', 'success');
                    
                    // If there's a success URL, redirect after a short delay
                    if (data.redirect_url) {
                        setTimeout(() => {
                            window.location.href = data.redirect_url;
                        }, 1500);
                    }
                }, 500);
            }
        } else {
            showNotification(data.message || 'Failed to accept order. Please try again.', 'danger');
        }
    })
    .catch(error => {
        console.error('Error accepting order:', error);
        showNotification(error.message || 'Failed to accept order. Please try again.', 'danger');
    });
}

// Function to view order details
function viewOrderDetails(orderId) {
    // Show loading state
    const modal = new bootstrap.Modal(document.getElementById('deliveryDetailModal'));
    const modalBody = document.getElementById('deliveryDetailContent');
    
    // Set loading content
    modalBody.innerHTML = `
        <div class="text-center py-4">
            <div class="spinner-border text-primary" role="status">
                <span class="visually-hidden">Loading...</span>
            </div>
            <p class="mt-2">Loading order details...</p>
        </div>
    `;
    
    // Show the modal
    modal.show();
    
    // Fetch order details
    fetch(`/rider/order/${orderId}/details`)
        .then(response => {
            if (!response.ok) {
                throw new Error('Failed to load order details');
            }
            return response.json();
        })
        .then(data => {
            if (data.success && data.html) {
                modalBody.innerHTML = data.html;
            } else {
                throw new Error(data.message || 'Failed to load order details');
            }
        })
        .catch(error => {
            console.error('Error loading order details:', error);
            modalBody.innerHTML = `
                <div class="alert alert-danger">
                    <i class="fas fa-exclamation-triangle me-2"></i>
                    ${error.message || 'Failed to load order details. Please try again.'}
                </div>
                <div class="text-center mt-3">
                    <button class="btn btn-primary" onclick="viewOrderDetails('${orderId}')">
                        <i class="fas fa-sync-alt me-1"></i> Try Again
                    </button>
                </div>
            `;
        });
}

// Initialize WebSocket connection
function initWebSocket() {
    if (typeof io === 'undefined') {
        console.error('Socket.IO is not loaded');
        showNotification('Real-time updates not available. Please refresh the page.', 'danger');
        return;
    }

    // Only initialize if not already connected
    if (!socket || !isConnected) {
        console.log('Initializing WebSocket connection...');
        
        // Connect to the WebSocket server
        socket = io({
            reconnection: true,
            reconnectionAttempts: 5,
            reconnectionDelay: 1000,
            reconnectionDelayMax: 5000,
            timeout: 20000
        });
        
        // Handle connection events
        socket.on('connect', function() {
            console.log('Connected to WebSocket server');
            isConnected = true;
            
            const riderId = document.body.getAttribute('data-rider-id');
            if (riderId) {
                console.log('Joining rider rooms for rider ID:', riderId);
                // Join the rider's personal room for direct messages
                socket.emit('rider_online', { rider_id: riderId });
                // Also join the general riders room for broadcast messages
                socket.emit('join_riders_room');
                
                // Mark rider as online in the database
                fetch('/rider/update-availability', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': csrfTokenValue
                    },
                    body: JSON.stringify({
                        is_online: true
                    })
                }).catch(console.error);
            }
        });

        // Handle new order confirmations
        socket.on('new_order_confirmed', function(data) {
            console.log('New order confirmed:', data);
            if (data && data.order) {
                addOrderToAvailableOrders(data.order);
            }
        });
        
        // Handle new delivery available
        socket.on('new_delivery_available', function(data) {
            console.log('New delivery available:', data);
            if (data && data.order) {
                addOrderToAvailableOrders(data.order);
            }
        });

        // Handle connection errors
        socket.on('connect_error', function(error) {
            console.error('WebSocket connection error:', error);
            isConnected = false;
            showNotification('Connection to server lost. Trying to reconnect...', 'warning');
        });
        
        // Handle reconnection
        socket.on('reconnect', function(attemptNumber) {
            console.log('Reconnected to WebSocket server after', attemptNumber, 'attempts');
            isConnected = true;
            showNotification('Reconnected to server', 'success');
            
            // Rejoin rooms after reconnection
            const riderId = document.body.getAttribute('data-rider-id');
            if (riderId) {
                socket.emit('rider_online', { rider_id: riderId });
                socket.emit('join_riders_room');
            }
        });
        
        // Handle disconnection
        socket.on('disconnect', function(reason) {
            console.log('Disconnected from WebSocket server:', reason);
            isConnected = false;
            if (reason === 'io server disconnect') {
                // The disconnection was initiated by the server, we need to reconnect manually
                socket.connect();
            }
        });
    }
}

// Show notification
function showNotification(message, type = 'info') {
    // Create notification container if it doesn't exist
    let container = document.getElementById('notification-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'notification-container';
        container.style.position = 'fixed';
        container.style.top = '20px';
        container.style.right = '20px';
        container.style.zIndex = '9999';
        container.style.maxWidth = '350px';
        document.body.appendChild(container);
    }
    
    // Create notification element
    const notification = document.createElement('div');
    notification.className = `alert alert-${type} alert-dismissible fade show`;
    notification.role = 'alert';
    notification.style.marginBottom = '10px';
    notification.style.boxShadow = '0 4px 12px rgba(0, 0, 0, 0.15)';
    notification.style.transition = 'all 0.3s ease';
    notification.innerHTML = `
        <div class="d-flex align-items-center">
            <i class="${getNotificationIcon(type)} me-2"></i>
            <span>${message}</span>
            <button type="button" class="btn-close ms-auto" data-bs-dismiss="alert" aria-label="Close"></button>
        </div>
    `;
    
    // Add to container
    container.insertBefore(notification, container.firstChild);
    
    // Trigger reflow to enable animation
    notification.offsetHeight;
    notification.style.opacity = '1';
    
    // Auto-dismiss after delay
    const dismissTime = type === 'success' ? 5000 : 10000;
    const dismissTimeout = setTimeout(() => {
        notification.style.opacity = '0';
        notification.style.marginBottom = '0';
        notification.style.paddingTop = '0';
        notification.style.paddingBottom = '0';
        notification.style.height = '0';
        notification.style.overflow = 'hidden';
        
        // Remove from DOM after animation
        setTimeout(() => {
            notification.remove();
            
            // Remove container if no more notifications
            if (container && container.children.length === 0) {
                container.remove();
            }
        }, 300);
    }, dismissTime);
    
    // Pause auto-dismiss on hover
    notification.addEventListener('mouseenter', () => {
        clearTimeout(dismissTimeout);
    });
    
    notification.addEventListener('mouseleave', () => {
        setTimeout(() => {
            notification.style.opacity = '0';
            notification.style.marginBottom = '0';
            notification.style.paddingTop = '0';
            notification.style.paddingBottom = '0';
            notification.style.height = '0';
            notification.style.overflow = 'hidden';
            
            // Remove from DOM after animation
            setTimeout(() => {
                notification.remove();
                
                // Remove container if no more notifications
                if (container && container.children.length === 0) {
                    container.remove();
                }
            }, 300);
        }, 500);
    });
    
    // Handle close button click
    const closeButton = notification.querySelector('.btn-close');
    if (closeButton) {
        closeButton.addEventListener('click', (e) => {
            e.preventDefault();
            notification.style.opacity = '0';
            notification.style.marginBottom = '0';
            notification.style.paddingTop = '0';
            notification.style.paddingBottom = '0';
            notification.style.height = '0';
            notification.style.overflow = 'hidden';
            
            // Remove from DOM after animation
            setTimeout(() => {
                notification.remove();
                
                // Remove container if no more notifications
                if (container && container.children.length === 0) {
                    container.remove();
                }
            }, 300);
        });
    }
}

// Helper function to get appropriate icon for notification type
function getNotificationIcon(type) {
    switch (type) {
        case 'success':
            return 'fas fa-check-circle';
        case 'danger':
            return 'fas fa-exclamation-circle';
        case 'warning':
            return 'fas fa-exclamation-triangle';
        case 'info':
        default:
            return 'fas fa-info-circle';
    }
}

// Add order to available orders list
function addOrderToAvailableOrders(order) {
    console.log('Adding order to available orders:', order);
    const container = document.getElementById('availableOrdersContainer');
    const noOrdersMessage = document.getElementById('noOrdersMessage');
    
    if (!container) {
        console.error('Available orders container not found');
        return;
    }
    
    // Hide the no orders message if it's visible
    if (noOrdersMessage) {
        noOrdersMessage.style.display = 'none';
    }
    
    // Check if order already exists
    const existingOrder = document.querySelector(`[data-order-id="${order.order_id}"]`);
    if (existingOrder) {
        console.log('Order already exists in the list, updating...');
        updateExistingOrder(existingOrder, order);
        return;
    }
    
    // Create order card from template
    const template = document.getElementById('orderCardTemplate');
    if (!template) {
        console.error('Order card template not found');
        return;
    }
    
    const orderCard = template.content.cloneNode(true);
    const cardElement = orderCard.querySelector('.card');
    cardElement.setAttribute('data-order-id', order.order_id);
    
    // Format the order date
    const orderDate = order.created_at ? new Date(order.created_at) : new Date();
    const formattedDate = orderDate.toLocaleString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
    
    // Update order details
    if (order.order_number) {
        cardElement.querySelector('.order-number').textContent = order.order_number;
    } else {
        cardElement.querySelector('.order-number').textContent = order.order_id;
    }
    
    cardElement.querySelector('.order-amount').textContent = (order.total_amount || 0).toFixed(2);
    cardElement.querySelector('.order-item-count').textContent = order.item_count || 0;
    cardElement.querySelector('.order-date').textContent = formattedDate;
    
    // Set delivery address
    if (order.delivery_address) {
        if (typeof order.delivery_address === 'string') {
            cardElement.querySelector('.order-address').textContent = order.delivery_address;
        } else if (typeof order.delivery_address === 'object') {
            const address = [
                order.delivery_address.street_address,
                order.delivery_address.city,
                order.delivery_address.state,
                order.delivery_address.postal_code,
                order.delivery_address.country
            ].filter(Boolean).join(', ');
            cardElement.querySelector('.order-address').textContent = address || 'Not specified';
        } else {
            cardElement.querySelector('.order-address').textContent = 'Not specified';
        }
    }
    
    // Add event listeners
    const acceptButton = cardElement.querySelector('.accept-order');
    if (acceptButton) {
        acceptButton.addEventListener('click', function() {
            acceptOrder(order.order_id);
        });
    }
    
    const viewDetailsButton = cardElement.querySelector('.view-details');
    if (viewDetailsButton) {
        viewDetailsButton.addEventListener('click', function() {
            viewOrderDetails(order.order_id);
        });
    }
    
    // Insert at the top of the container
    container.insertBefore(orderCard, container.firstChild);
    
    // Show notification
    showNotification(`New order #${order.order_number || order.order_id} is available for delivery!`, 'success');
    modal.show();

    fetch('/rider/delivery/' + deliveryId + '/details')
        .then(function(response) { return response.json(); })
        .then(function(data) {
            content.innerHTML = data.html;
        })
        .catch(function(error) {
            content.innerHTML = '<div class="alert alert-danger"><i class="fas fa-exclamation-triangle"></i> Error loading delivery details. Please try again.</div>';
        });
}

// Update delivery status
function updateDeliveryStatus(deliveryId, status) {
    if (!confirm('Are you sure you want to mark this delivery as ' + status + '?')) {
        return;
    }

    const form = document.createElement('form');
    form.method = 'POST';
    form.action = updateStatusUrl;

    const csrfToken = document.createElement('input');
    csrfToken.type = 'hidden';
    csrfToken.name = 'csrf_token';
    csrfToken.value = csrfTokenValue;
    form.appendChild(csrfToken);

    const deliveryIdInput = document.createElement('input');
    deliveryIdInput.type = 'hidden';
    deliveryIdInput.name = 'delivery_id';
    deliveryIdInput.value = deliveryId;
    form.appendChild(deliveryIdInput);

    const statusInput = document.createElement('input');
    statusInput.type = 'hidden';
    statusInput.name = 'status';
    statusInput.value = status;
    form.appendChild(statusInput);

    document.body.appendChild(form);
    form.submit();
}

// Initialize the application when the DOM is fully loaded
document.addEventListener('DOMContentLoaded', function() {
    console.log('DOM fully loaded, initializing rider dashboard...');
    
    // Initialize WebSocket connection
    initWebSocket();
    
    // Initialize tooltips
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
    
    // Initialize any existing order cards that were loaded with the page
    document.querySelectorAll('.accept-order').forEach(button => {
        button.addEventListener('click', function() {
            const orderId = this.closest('[data-order-id]').getAttribute('data-order-id');
            acceptOrder(orderId);
        });
    });
    
    // Handle view details buttons
    document.querySelectorAll('.view-details').forEach(button => {
        button.addEventListener('click', function() {
            const orderId = this.closest('[data-order-id]').getAttribute('data-order-id');
            viewOrderDetails(orderId);
        });
    });

    // Function to view order details
    function viewOrderDetails(orderId) {
        fetch(`/rider/order/${orderId}/details`)
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    document.getElementById('orderDetailsContent').innerHTML = data.html;
                    const modal = new bootstrap.Modal(document.getElementById('orderDetailsModal'));
                    modal.show();
                } else {
                    showNotification(data.message || 'Failed to load order details', 'danger');
                }
            })
            .catch(error => {
                console.error('Error fetching order details:', error);
                showNotification('Failed to load order details', 'danger');
            });
    }
    
    // Set up a periodic check for WebSocket connection
    setInterval(() => {
        if (!isConnected) {
            console.log('WebSocket not connected, attempting to reconnect...');
            initWebSocket();
        }
    }, 10000); // Check every 10 seconds
    
    console.log('Rider dashboard initialization complete');
});
