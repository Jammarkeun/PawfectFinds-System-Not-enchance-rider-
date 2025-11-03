class RiderWebSocket {
    constructor() {
        this.socket = null;
        this.riderId = document.body.dataset.riderId;
        this.initializeWebSocket();
        this.setupEventListeners();
    }

    initializeWebSocket() {
        // Connect to WebSocket server
        this.socket = io({
            path: '/socket.io',
            transports: ['websocket', 'polling'],
            upgrade: true,
            reconnection: true,
            reconnectionAttempts: 5,
            reconnectionDelay: 1000,
            reconnectionDelayMax: 5000,
            timeout: 20000
        });

        // Connection established
        this.socket.on('connect', () => {
            console.log('Connected to WebSocket server');
            
            // Join rider's personal room
            this.socket.emit('rider_online', { rider_id: this.riderId });
            
            // Join general riders room
            this.socket.emit('join_riders_room');
            
            // Update UI
            this.updateConnectionStatus(true);
        });

        // New delivery available
        this.socket.on('new_delivery_available', (data) => {
            console.log('New delivery available:', data);
            this.showNewOrderNotification(data);
            this.refreshAvailableOrders();
        });

        // Order was taken by another rider
        this.socket.on('order_taken', (data) => {
            console.log('Order taken by another rider:', data);
            if (data.order_id) {
                this.removeOrderFromList(data.order_id);
                this.showToast('Order taken', 'This order was accepted by another rider.', 'info');
            }
        });

        // Connection lost
        this.socket.on('disconnect', () => {
            console.log('Disconnected from WebSocket server');
            this.updateConnectionStatus(false);
        });

        // Reconnect
        this.socket.on('reconnect', () => {
            console.log('Reconnected to WebSocket server');
            this.socket.emit('rider_online', { rider_id: this.riderId });
            this.socket.emit('join_riders_room');
            this.updateConnectionStatus(true);
        });

        // Error handling
        this.socket.on('connect_error', (error) => {
            console.error('WebSocket connection error:', error);
            this.updateConnectionStatus(false);
        });
    }

    setupEventListeners() {
        // Handle order acceptance
        document.addEventListener('click', (e) => {
            const acceptBtn = e.target.closest('.accept-order-btn');
            if (acceptBtn) {
                e.preventDefault();
                const orderId = acceptBtn.dataset.orderId;
                this.acceptOrder(orderId, acceptBtn);
            }
        });

        // Handle page visibility changes
        document.addEventListener('visibilitychange', () => {
            if (document.visibilityState === 'visible') {
                this.refreshAvailableOrders();
            }
        });

        // Periodically update rider's location if on delivery
        if (navigator.geolocation) {
            setInterval(() => this.updateRiderLocation(), 30000); // Every 30 seconds
        }
    }

    async acceptOrder(orderId, button) {
        if (!orderId) return;

        const originalText = button.innerHTML;
        button.disabled = true;
        button.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Accepting...';

        try {
            const response = await fetch(`/rider/accept-order/${orderId}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                credentials: 'same-origin'
            });

            const data = await response.json();

            if (data.success) {
                // Show success message
                this.showToast('Success', 'Order accepted successfully!', 'success');
                
                // Redirect to order details
                if (data.redirect) {
                    window.location.href = data.redirect;
                }
            } else {
                throw new Error(data.message || 'Failed to accept order');
            }
        } catch (error) {
            console.error('Error accepting order:', error);
            this.showToast('Error', error.message || 'Failed to accept order', 'error');
            button.disabled = false;
            button.innerHTML = originalText;
        }
    }

    async refreshAvailableOrders() {
        try {
            const response = await fetch('/rider/available-orders', {
                headers: {
                    'X-Requested-With': 'XMLHttpRequest'
                }
            });
            
            if (response.ok) {
                const data = await response.json();
                this.updateOrdersList(data.orders);
            }
        } catch (error) {
            console.error('Error refreshing orders:', error);
        }
    }

    updateOrdersList(orders) {
        // Implement your UI update logic here
        // This is a placeholder - update according to your template structure
        const ordersContainer = document.getElementById('available-orders-list');
        if (!ordersContainer) return;

        if (orders.length === 0) {
            ordersContainer.innerHTML = '<div class="alert alert-info">No orders available at the moment.</div>';
            return;
        }

        // Clear existing orders
        ordersContainer.innerHTML = '';

        // Add each order to the list
        orders.forEach(order => {
            const orderElement = this.createOrderElement(order);
            ordersContainer.appendChild(orderElement);
        });
    }

    createOrderElement(order) {
        // Create order card element
        const orderEl = document.createElement('div');
        orderEl.className = 'card mb-3';
        orderEl.id = `order-${order.id}`;
        
        // Format order items list
        const itemsList = order.items.map(item => 
            `${item.quantity}x ${item.name} - $${item.price.toFixed(2)}`
        ).join('<br>');
        
        // Format created_at time
        const orderTime = new Date(order.created_at).toLocaleString();
        
        // Set inner HTML
        orderEl.innerHTML = `
            <div class="card-header">
                <h5 class="mb-0">Order #${order.id}</h5>
                <small class="text-muted">${orderTime}</small>
            </div>
            <div class="card-body">
                <p class="card-text"><strong>Amount:</strong> $${order.total_amount.toFixed(2)}</p>
                <p class="card-text"><strong>Items:</strong><br>${itemsList}</p>
                <p class="card-text"><strong>Delivery to:</strong> ${order.shipping_address}</p>
                <button class="btn btn-primary accept-order-btn" data-order-id="${order.id}">
                    Accept Order
                </button>
            </div>
        `;
        
        return orderEl;
    }

    removeOrderFromList(orderId) {
        const orderElement = document.getElementById(`order-${orderId}`);
        if (orderElement) {
            orderElement.remove();
        }
    }

    showNewOrderNotification(order) {
        // Play sound if enabled
        if (Notification.permission === 'granted') {
            new Notification('New Delivery Available', {
                body: `Order #${order.id} - $${order.total_amount.toFixed(2)}`,
                icon: '/static/PF-logo.png',
                vibrate: [200, 100, 200]
            });
        }

        // Show toast notification
        this.showToast(
            'New Delivery Available', 
            `Order #${order.id} - $${order.total_amount.toFixed(2)}`, 
            'info'
        );
    }

    showToast(title, message, type = 'info') {
        // Use your preferred toast library or implement a simple one
        // This is a placeholder implementation
        const toastContainer = document.getElementById('toast-container') || (() => {
            const container = document.createElement('div');
            container.id = 'toast-container';
            container.style.position = 'fixed';
            container.style.top = '20px';
            container.style.right = '20px';
            container.style.zIndex = '9999';
            document.body.appendChild(container);
            return container;
        })();

        const toast = document.createElement('div');
        toast.className = `toast show bg-${type} text-white`;
        toast.role = 'alert';
        toast.style.minWidth = '250px';
        toast.style.marginBottom = '10px';
        
        toast.innerHTML = `
            <div class="toast-header">
                <strong class="me-auto">${title}</strong>
                <button type="button" class="btn-close" data-bs-dismiss="toast" aria-label="Close"></button>
            </div>
            <div class="toast-body">
                ${message}
            </div>
        `;
        
        toastContainer.appendChild(toast);
        
        // Auto-remove after 5 seconds
        setTimeout(() => {
            toast.classList.remove('show');
            setTimeout(() => toast.remove(), 150);
        }, 5000);
    }

    updateConnectionStatus(connected) {
        const statusElement = document.getElementById('connection-status');
        if (statusElement) {
            statusElement.textContent = connected ? 'Online' : 'Offline';
            statusElement.className = `badge bg-${connected ? 'success' : 'danger'}`;
        }
    }

    updateRiderLocation() {
        if (navigator.geolocation) {
            navigator.geolocation.getCurrentPosition(
                (position) => {
                    const { latitude, longitude } = position.coords;
                    
                    // Update in database via API
                    fetch('/rider/update-location', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-Requested-With': 'XMLHttpRequest'
                        },
                        body: JSON.stringify({
                            lat: latitude,
                            lng: longitude
                        })
                    });
                    
                    // Emit location update via WebSocket
                    if (this.socket && this.socket.connected) {
                        this.socket.emit('update_location', {
                            rider_id: this.riderId,
                            lat: latitude,
                            lng: longitude
                        });
                    }
                },
                (error) => {
                    console.error('Error getting location:', error);
                },
                {
                    enableHighAccuracy: true,
                    maximumAge: 10000,  // 10 seconds
                    timeout: 5000
                }
            );
        }
    }
}

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    // Request notification permission
    if ('Notification' in window && Notification.permission !== 'granted' && Notification.permission !== 'denied') {
        Notification.requestPermission();
    }
    
    // Initialize WebSocket client if on rider dashboard
    if (document.body.classList.contains('rider-dashboard') && document.body.dataset.riderId) {
        window.riderWebSocket = new RiderWebSocket();
    }
});
