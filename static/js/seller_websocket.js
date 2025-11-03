class SellerWebSocket {
    constructor() {
        this.socket = null;
        this.sellerId = document.body.dataset.sellerId;
        this.initializeWebSocket();
        this.setupEventListeners();
        this.initializeMap();
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
            console.log('Connected to WebSocket server as seller');
            
            // Join seller's personal room
            this.socket.emit('join_seller_room', { seller_id: this.sellerId });
            
            // Update UI
            this.updateConnectionStatus(true);
        });

        // Order was accepted by a rider
        this.socket.on('order_accepted', (data) => {
            console.log('Order accepted by rider:', data);
            this.showToast(
                'Order Accepted', 
                `Order #${data.order_id} was accepted by ${data.rider_name || 'a rider'}`,
                'success'
            );
            this.refreshOrder(data.order_id);
        });

        // Order status was updated
        this.socket.on('order_status_updated', (data) => {
            console.log('Order status updated:', data);
            this.updateOrderStatusUI(data.order_id, data.status, data.status_display);
        });

        // Rider location updated
        this.socket.on('rider_location_updated', (data) => {
            console.log('Rider location updated:', data);
            this.updateRiderLocationOnMap(data);
        });

        // Connection lost
        this.socket.on('disconnect', () => {
            console.log('Disconnected from WebSocket server');
            this.updateConnectionStatus(false);
        });

        // Reconnect
        this.socket.on('reconnect', () => {
            console.log('Reconnected to WebSocket server');
            this.socket.emit('join_seller_room', { seller_id: this.sellerId });
            this.updateConnectionStatus(true);
        });
    }

    setupEventListeners() {
        // Handle status updates
        document.addEventListener('click', (e) => {
            const statusBtn = e.target.closest('.update-status-btn');
            if (statusBtn) {
                e.preventDefault();
                const orderId = statusBtn.dataset.orderId;
                const newStatus = statusBtn.dataset.status;
                this.updateOrderStatus(orderId, newStatus, statusBtn);
            }
            
            // Handle view details button
            const viewDetailsBtn = e.target.closest('.view-details-btn');
            if (viewDetailsBtn) {
                e.preventDefault();
                const orderId = viewDetailsBtn.dataset.orderId;
                this.viewOrderDetails(orderId);
            }
        });
        
        // Handle tab changes to load data as needed
        const orderTabs = document.querySelectorAll('[data-bs-toggle="tab"][data-type="order-tab"]');
        orderTabs.forEach(tab => {
            tab.addEventListener('shown.bs.tab', (e) => {
                const status = e.target.dataset.status || 'all';
                this.loadOrders(status);
            });
        });
        
        // Initialize with first tab data
        const activeTab = document.querySelector('.nav-link.active[data-type="order-tab"]');
        if (activeTab) {
            const status = activeTab.dataset.status || 'all';
            this.loadOrders(status);
        }
    }
    
    initializeMap() {
        // Initialize map if on order detail page with map
        if (typeof initMap === 'function') {
            initMap();
        }
    }
    
    async updateOrderStatus(orderId, status, button) {
        if (!orderId || !status) return;
        
        const originalHtml = button ? button.innerHTML : '';
        if (button) {
            button.disabled = true;
            button.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>';
        }
        
        try {
            const response = await fetch(`/seller/order/${orderId}/update-status`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: `status=${encodeURIComponent(status)}`,
                credentials: 'same-origin'
            });
            
            const data = await response.json();
            
            if (!response.ok) {
                throw new Error(data.message || 'Failed to update status');
            }
            
            // Update UI
            this.showToast('Success', data.message || 'Order status updated', 'success');
            this.updateOrderStatusUI(orderId, data.status, data.status_display);
            
            // If order was marked as shipped, show notification
            if (status === 'shipped') {
                this.showToast(
                    'Order Shipped', 
                    'Riders have been notified about this delivery',
                    'info'
                );
            }
            
        } catch (error) {
            console.error('Error updating order status:', error);
            this.showToast('Error', error.message || 'Failed to update order status', 'error');
        } finally {
            if (button) {
                button.disabled = false;
                button.innerHTML = originalHtml;
            }
        }
    }
    
    async loadOrders(status = 'all', page = 1) {
        const ordersContainer = document.getElementById('orders-container');
        const loadingIndicator = document.getElementById('loading-orders');
        const pagination = document.getElementById('orders-pagination');
        
        if (loadingIndicator) loadingIndicator.classList.remove('d-none');
        if (ordersContainer) ordersContainer.innerHTML = '';
        
        try {
            const response = await fetch(`/seller/orders?status=${status}&page=${page}`, {
                headers: {
                    'X-Requested-With': 'XMLHttpRequest'
                }
            });
            
            if (!response.ok) {
                throw new Error('Failed to load orders');
            }
            
            const data = await response.json();
            
            if (data.orders && data.orders.length > 0) {
                this.renderOrders(data.orders);
                this.updatePagination(data, status, page);
            } else {
                this.showNoOrdersMessage(status);
            }
            
            // Update status counts in tabs
            this.updateStatusCounts(data.status_counts || {});
            
        } catch (error) {
            console.error('Error loading orders:', error);
            this.showToast('Error', 'Failed to load orders', 'error');
        } finally {
            if (loadingIndicator) loadingIndicator.classList.add('d-none');
        }
    }
    
    renderOrders(orders) {
        const ordersContainer = document.getElementById('orders-container');
        if (!ordersContainer) return;
        
        ordersContainer.innerHTML = orders.map(order => this.createOrderCard(order)).join('');
    }
    
    createOrderCard(order) {
        const orderDate = new Date(order.created_at).toLocaleString();
        const statusClass = this.getStatusBadgeClass(order.status);
        
        return `
            <div class="card mb-3 order-card" id="order-${order.id}" data-order-id="${order.id}">
                <div class="card-header d-flex justify-content-between align-items-center">
                    <div>
                        <h5 class="mb-0">Order #${order.order_number}</h5>
                        <small class="text-muted">${orderDate}</small>
                    </div>
                    <span class="badge ${statusClass}">${order.status_display || order.status}</span>
                </div>
                <div class="card-body">
                    <div class="row">
                        <div class="col-md-6">
                            <p class="mb-1"><strong>Customer:</strong> ${order.customer_name || 'N/A'}</p>
                            <p class="mb-1"><strong>Items:</strong> ${order.item_count || 0}</p>
                            <p class="mb-0"><strong>Total:</strong> $${order.total_amount ? order.total_amount.toFixed(2) : '0.00'}</p>
                        </div>
                        <div class="col-md-6 text-end">
                            ${this.getStatusButtons(order.status, order.id)}
                            <a href="/seller/order/${order.id}" class="btn btn-outline-primary btn-sm view-details-btn" data-order-id="${order.id}">
                                View Details
                            </a>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }
    
    getStatusBadgeClass(status) {
        const statusClasses = {
            'pending': 'bg-secondary',
            'confirmed': 'bg-info',
            'shipped': 'bg-primary',
            'out_for_delivery': 'bg-warning',
            'delivered': 'bg-success',
            'cancelled': 'bg-danger'
        };
        return statusClasses[status] || 'bg-secondary';
    }
    
    getStatusButtons(currentStatus, orderId) {
        const statusOptions = {
            'pending': ['Confirm', 'Cancel'],
            'confirmed': ['Mark as Shipped', 'Cancel'],
            'shipped': ['Mark as Delivered'],
            'out_for_delivery': ['Mark as Delivered']
        };
        
        const statusMap = {
            'Confirm': 'confirmed',
            'Cancel': 'cancelled',
            'Mark as Shipped': 'shipped',
            'Mark as Delivered': 'delivered'
        };
        
        let buttons = '';
        
        if (statusOptions[currentStatus]) {
            statusOptions[currentStatus].forEach(action => {
                const status = statusMap[action];
                const btnClass = action === 'Cancel' ? 'btn-danger' : 'btn-primary';
                
                buttons += `
                    <button class="btn btn-sm ${btnClass} me-2 mb-1 update-status-btn" 
                            data-order-id="${orderId}" 
                            data-status="${status}">
                        ${action}
                    </button>
                `;
            });
        }
        
        return buttons;
    }
    
    updateOrderStatusUI(orderId, status, statusDisplay) {
        // Update status badge
        const statusBadge = document.querySelector(`#order-${orderId} .badge`);
        if (statusBadge) {
            const statusClass = this.getStatusBadgeClass(status);
            statusBadge.className = `badge ${statusClass}`;
            statusBadge.textContent = statusDisplay || status;
        }
        
        // Update action buttons
        const buttonsContainer = document.querySelector(`#order-${orderId} .text-end`);
        if (buttonsContainer) {
            const viewDetailsBtn = buttonsContainer.querySelector('.view-details-btn');
            buttonsContainer.innerHTML = this.getStatusButtons(status, orderId);
            if (viewDetailsBtn) {
                buttonsContainer.appendChild(viewDetailsBtn);
            }
        }
    }
    
    async refreshOrder(orderId) {
        try {
            const response = await fetch(`/seller/order/${orderId}`, {
                headers: {
                    'X-Requested-With': 'XMLHttpRequest'
                }
            });
            
            if (response.ok) {
                const order = await response.json();
                this.updateOrderUI(order);
            }
        } catch (error) {
            console.error('Error refreshing order:', error);
        }
    }
    
    updateOrderUI(order) {
        // Update the order card in the list
        const orderElement = document.getElementById(`order-${order.id}`);
        if (orderElement) {
            orderElement.outerHTML = this.createOrderCard(order);
        }
        
        // If on the order detail page, update that as well
        if (document.querySelector('.order-detail-page')) {
            this.updateOrderDetailPage(order);
        }
    }
    
    updateOrderDetailPage(order) {
        // Update status display
        const statusElement = document.querySelector('.order-status');
        if (statusElement) {
            const statusClass = this.getStatusBadgeClass(order.status);
            statusElement.className = `badge ${statusClass} order-status`;
            statusElement.textContent = order.status_display || order.status;
        }
        
        // Update action buttons
        const actionsContainer = document.querySelector('.order-actions');
        if (actionsContainer) {
            actionsContainer.innerHTML = this.getStatusButtons(order.status, order.id);
        }
        
        // Update rider info if available
        if (order.rider) {
            const riderInfo = document.getElementById('rider-info');
            if (riderInfo) {
                riderInfo.innerHTML = `
                    <p><strong>Rider:</strong> ${order.rider.first_name} ${order.rider.last_name}</p>
                    <p><strong>Contact:</strong> ${order.rider.phone || 'N/A'}</p>
                    <div id="rider-location-map" style="height: 200px; width: 100%;"></div>
                `;
                
                // Initialize map with rider's location
                if (order.rider_location) {
                    this.initializeRiderMap(order.rider_location);
                }
            }
        }
    }
    
    initializeRiderMap(location) {
        // This would be implemented based on your map provider (Google Maps, Mapbox, etc.)
        // Here's a placeholder implementation
        console.log('Initializing map with location:', location);
        
        const mapElement = document.getElementById('rider-location-map');
        if (mapElement && window.initMap) {
            window.initMap(location.lat, location.lng);
        }
    }
    
    updateRiderLocationOnMap(data) {
        // This would update the rider's location on the map in real-time
        if (window.updateMapMarker) {
            window.updateMapMarker(data.lat, data.lng);
        }
    }
    
    showNoOrdersMessage(status) {
        const messages = {
            'all': 'No orders found',
            'pending': 'No pending orders',
            'confirmed': 'No confirmed orders',
            'shipped': 'No shipped orders',
            'out_for_delivery': 'No orders out for delivery',
            'delivered': 'No delivered orders',
            'cancelled': 'No cancelled orders'
        };
        
        const container = document.getElementById('orders-container');
        if (container) {
            container.innerHTML = `
                <div class="text-center py-5">
                    <i class="fas fa-box-open fa-3x text-muted mb-3"></i>
                    <h4>${messages[status] || messages['all']}</h4>
                    <p class="text-muted">When you have orders, they'll appear here</p>
                </div>
            `;
        }
    }
    
    updateStatusCounts(counts) {
        // Update the count badges in the navigation tabs
        Object.entries(counts).forEach(([status, count]) => {
            const tab = document.querySelector(`[data-status="${status}"] .badge`);
            if (tab) {
                tab.textContent = count;
            }
        });
    }
    
    updatePagination(data, status, currentPage) {
        const pagination = document.getElementById('orders-pagination');
        if (!pagination) return;
        
        if (!data.has_prev && !data.has_next) {
            pagination.innerHTML = '';
            return;
        }
        
        let html = '<nav aria-label="Page navigation"><ul class="pagination justify-content-center">';
        
        // Previous button
        html += `<li class="page-item ${data.has_prev ? '' : 'disabled'}">
            <a class="page-link" href="#" data-page="${currentPage - 1}" aria-label="Previous">
                <span aria-hidden="true">&laquo;</span>
            </a>
        </li>`;
        
        // Page numbers
        const startPage = Math.max(1, currentPage - 2);
        const endPage = Math.min(data.pages, startPage + 4);
        
        for (let i = startPage; i <= endPage; i++) {
            html += `<li class="page-item ${i === currentPage ? 'active' : ''}">
                <a class="page-link" href="#" data-page="${i}">${i}</a>
            </li>`;
        }
        
        // Next button
        html += `<li class="page-item ${data.has_next ? '' : 'disabled'}">
            <a class="page-link" href="#" data-page="${currentPage + 1}" aria-label="Next">
                <span aria-hidden="true">&raquo;</span>
            </a>
        </li>`;
        
        html += '</ul></nav>';
        
        pagination.innerHTML = html;
        
        // Add click handlers to pagination links
        pagination.querySelectorAll('.page-link').forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                const page = parseInt(link.dataset.page);
                if (!isNaN(page) && page >= 1 && page <= data.pages) {
                    this.loadOrders(status, page);
                    window.scrollTo({ top: 0, behavior: 'smooth' });
                }
            });
        });
    }
    
    showToast(title, message, type = 'info') {
        // Use your preferred toast library or implement a simple one
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
}

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    // Initialize WebSocket client if on seller dashboard
    if (document.body.classList.contains('seller-dashboard') && document.body.dataset.sellerId) {
        window.sellerWebSocket = new SellerWebSocket();
    }
    
    // Initialize tooltips
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
});
