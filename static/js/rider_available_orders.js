/**
 * Rider Available Orders - Handles real-time order updates
 * Save as: static/js/rider_available_orders.js
 */

(function() {
    'use strict';
    
    console.log('=== Rider Available Orders Script Loaded ===');
    
    // Global variables
    let socket = null;
    let riderId = null;
    
    // Initialize when DOM is ready
    document.addEventListener('DOMContentLoaded', function() {
        console.log('Initializing available orders functionality...');
        
        // Get rider ID from dashboard element
        const dashboardEl = document.querySelector('.rider-dashboard');
        if (dashboardEl) {
            riderId = dashboardEl.dataset.riderId;
            console.log('Rider ID:', riderId);
        } else {
            const ordersSection = document.getElementById('availableOrdersSection');
            if (ordersSection) {
                riderId = ordersSection.dataset.riderId;
                console.log('Rider ID from section:', riderId);
            }
        }
        
        if (!riderId) {
            console.error('Rider ID not found!');
            return;
        }
        
        // Initialize
        initializeWebSocket();
        loadAvailableOrders();
        setupEventHandlers();
        
        // Refresh every 60 seconds
        setInterval(loadAvailableOrders, 60000);
    });
    
    /**
     * Initialize WebSocket
     */
    function initializeWebSocket() {
        console.log('Initializing WebSocket...');
        
        if (typeof io === 'undefined') {
            console.error('Socket.IO not loaded!');
            return;
        }
        
        try {
            socket = io({
                reconnection: true,
                reconnectionAttempts: 10,
                reconnectionDelay: 1000,
                transports: ['websocket', 'polling']
            });
            
            socket.on('connect', function() {
                console.log('✓ WebSocket connected');
                socket.emit('join', { room: 'rider_' + riderId });
                socket.emit('join', { room: 'available_orders' });
                socket.emit('rider_online', { rider_id: riderId });
            });
            
            socket.on('new_delivery_opportunity', handleNewOrder);
            socket.on('new_available_order', handleNewOrder);
            socket.on('new_order_confirmed', handleNewOrder);
            socket.on('order_taken', handleOrderTaken);
            socket.on('order_accepted', handleOrderAccepted);
            
            socket.on('disconnect', function(reason) {
                console.warn('WebSocket disconnected:', reason);
            });
            
            socket.on('reconnect', function() {
                console.log('Reconnected, reloading orders...');
                loadAvailableOrders();
            });
            
        } catch (error) {
            console.error('WebSocket error:', error);
        }
    }
    
    /**
     * Load available orders
     */
    function loadAvailableOrders() {
        console.log('Loading available orders...');
        
        const loadingEl = document.getElementById('ordersLoading');
        const noOrdersEl = document.getElementById('noOrdersMessage');
        const container = document.getElementById('availableOrdersContainer');
        
        if (loadingEl) loadingEl.style.display = 'block';
        if (noOrdersEl) noOrdersEl.style.display = 'none';
        if (container) container.style.display = 'none';
        
        fetch('/rider/available-orders')
            .then(response => response.json())
            .then(data => {
                console.log('Orders response:', data);
                
                if (loadingEl) loadingEl.style.display = 'none';
                
                if (data.success && data.orders && data.orders.length > 0) {
                    if (container) {
                        container.innerHTML = '';
                        container.style.display = 'block';
                    }
                    if (noOrdersEl) noOrdersEl.style.display = 'none';
                    
                    data.orders.forEach(order => addOrderCard(order));
                    console.log(`✓ Displayed ${data.orders.length} orders`);
                } else {
                    if (container) container.style.display = 'none';
                    if (noOrdersEl) noOrdersEl.style.display = 'block';
                    console.log('No orders available');
                }
            })
            .catch(error => {
                console.error('Error loading orders:', error);
                if (loadingEl) loadingEl.style.display = 'none';
                showToast('Error', 'Failed to load orders', 'danger');
            });
    }
    
    /**
     * Add order card to UI
     */
    function addOrderCard(order) {
        const container = document.getElementById('availableOrdersContainer');
        const template = document.getElementById('orderCardTemplate');
        
        if (!container || !template) {
            console.error('Container or template not found!');
            return;
        }
        
        // Check if order already exists
        if (document.getElementById('order-' + order.id)) {
            console.log('Order already exists:', order.id);
            return;
        }
        
        const clone = template.content.cloneNode(true);
        const card = clone.querySelector('.order-card');
        
        card.setAttribute('data-order-id', order.id);
        card.id = 'order-' + order.id;
        
        clone.querySelector('.order-number').textContent = order.order_number || 'ORD-' + order.id;
        clone.querySelector('.order-date').textContent = formatDate(order.created_at);
        clone.querySelector('.order-item-count').textContent = order.item_count || 0;
        clone.querySelector('.order-amount').textContent = parseFloat(order.total_amount || 0).toFixed(2);
        
        // Set location
        const locationEl = clone.querySelector('.order-distance');
        if (locationEl && order.shipping_address) {
            const addr = order.shipping_address;
            locationEl.textContent = addr.length > 20 ? addr.substring(0, 20) + '...' : addr;
            locationEl.title = addr;
        }
        
        // Setup buttons
        const acceptBtn = clone.querySelector('.accept-order-btn');
        if (acceptBtn) {
            acceptBtn.onclick = () => acceptOrder(order.id);
        }
        
        const detailsBtn = clone.querySelector('.view-details-btn');
        if (detailsBtn) {
            detailsBtn.onclick = () => viewOrderDetails(order.id);
        }
        
        const mapBtn = clone.querySelector('.view-map-btn');
        if (mapBtn && order.shipping_address) {
            mapBtn.onclick = () => {
                if (typeof showDeliveryLocation === 'function') {
                    showDeliveryLocation(order.shipping_address, order.customer_name || 'Customer');
                }
            };
        }
        
        container.insertBefore(clone, container.firstChild);
        console.log('Added order:', order.id);
    }
    
    /**
     * Accept order
     */
    window.acceptOrder = function(orderId) {
        if (!confirm('Accept this delivery?')) return;
        
        console.log('Accepting order:', orderId);
        
        const card = document.getElementById('order-' + orderId);
        const btn = card?.querySelector('.accept-order-btn');
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> Accepting...';
        }
        
        const formData = new FormData();
        formData.append('order_id', orderId);
        
        fetch('/rider/delivery/accept', {
            method: 'POST',
            body: formData
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                showToast('Success!', 'Delivery accepted successfully', 'success');
                removeOrderCard(orderId);
                setTimeout(() => window.location.reload(), 1000);
            } else {
                showToast('Failed', data.message || 'Could not accept delivery', 'danger');
                if (btn) {
                    btn.disabled = false;
                    btn.innerHTML = '<i class="fas fa-check-circle me-1"></i> Accept';
                }
            }
        })
        .catch(error => {
            console.error('Error:', error);
            showToast('Error', 'Failed to accept delivery', 'danger');
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = '<i class="fas fa-check-circle me-1"></i> Accept';
            }
        });
    };
    
    /**
     * View order details
     */
    window.viewOrderDetails = function(orderId) {
        console.log('Viewing order:', orderId);
        
        const modal = document.getElementById('orderDetailsModal');
        const modalNumber = document.getElementById('modalOrderNumber');
        const modalContent = document.getElementById('orderDetailsContent');
        
        if (!modal || !modalContent) return;
        
        if (modalNumber) modalNumber.textContent = orderId;
        modalContent.innerHTML = '<div class="text-center py-4"><div class="spinner-border"></div><p class="mt-2">Loading...</p></div>';
        
        const bsModal = new bootstrap.Modal(modal);
        bsModal.show();
        
        fetch(`/rider/order/${orderId}/details`)
            .then(response => response.json())
            .then(data => {
                if (data.success && data.html) {
                    modalContent.innerHTML = data.html;
                    
                    const acceptBtn = modal.querySelector('.accept-order-modal-btn');
                    if (acceptBtn) {
                        acceptBtn.onclick = function() {
                            bsModal.hide();
                            acceptOrder(orderId);
                        };
                    }
                } else {
                    modalContent.innerHTML = '<div class="alert alert-danger">Failed to load details</div>';
                }
            })
            .catch(error => {
                console.error('Error:', error);
                modalContent.innerHTML = '<div class="alert alert-danger">Error loading details</div>';
            });
    };
    
    /**
     * Handle new order from WebSocket
     */
    function handleNewOrder(data) {
        console.log('New order received:', data);
        
        const order = data.order || data;
        if (!order || !order.id) return;
        
        const container = document.getElementById('availableOrdersContainer');
        const noOrdersEl = document.getElementById('noOrdersMessage');
        
        if (container) container.style.display = 'block';
        if (noOrdersEl) noOrdersEl.style.display = 'none';
        
        addOrderCard(order);
        showToast('New Order!', `Order ${order.order_number || order.id} is available`, 'info');
    }
    
    /**
     * Handle order taken
     */
    function handleOrderTaken(data) {
        console.log('Order taken:', data);
        removeOrderCard(data.order_id || data.orderId);
    }
    
    function handleOrderAccepted(data) {
        console.log('Order accepted:', data);
        if (data.rider_id != riderId) {
            removeOrderCard(data.order_id);
        }
    }
    
    /**
     * Remove order card
     */
    function removeOrderCard(orderId) {
        const card = document.getElementById('order-' + orderId);
        if (card) {
            card.style.opacity = '0';
            card.style.transition = 'opacity 0.3s';
            setTimeout(() => {
                card.remove();
                
                const container = document.getElementById('availableOrdersContainer');
                const noOrdersEl = document.getElementById('noOrdersMessage');
                if (container && container.children.length === 0) {
                    container.style.display = 'none';
                    if (noOrdersEl) noOrdersEl.style.display = 'block';
                }
            }, 300);
        }
    }
    
    /**
     * Setup event handlers
     */
    function setupEventHandlers() {
        const refreshBtn = document.getElementById('refreshOrdersBtn');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', function() {
                this.disabled = true;
                this.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> Refreshing...';
                loadAvailableOrders();
                setTimeout(() => {
                    this.disabled = false;
                    this.innerHTML = '<i class="fas fa-sync-alt me-1"></i> Refresh';
                }, 1000);
            });
        }
        
        const retryBtn = document.getElementById('retryLoadBtn');
        if (retryBtn) {
            retryBtn.addEventListener('click', loadAvailableOrders);
        }
    }
    
    /**
     * Show toast notification
     */
    function showToast(title, message, type = 'info') {
        const container = document.getElementById('toastContainer') || document.body;
        
        const bgClass = {
            'success': 'bg-success',
            'danger': 'bg-danger',
            'warning': 'bg-warning',
            'info': 'bg-info'
        }[type] || 'bg-info';
        
        const toastId = 'toast-' + Date.now();
        const toastHtml = `
            <div id="${toastId}" class="toast align-items-center text-white ${bgClass} border-0" role="alert">
                <div class="d-flex">
                    <div class="toast-body">
                        <strong>${title}</strong><br>${message}
                    </div>
                    <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
                </div>
            </div>
        `;
        
        container.insertAdjacentHTML('beforeend', toastHtml);
        const toastEl = document.getElementById(toastId);
        const toast = new bootstrap.Toast(toastEl, { delay: 5000 });
        toast.show();
        
        toastEl.addEventListener('hidden.bs.toast', () => toastEl.remove());
    }
    
    /**
     * Format date
     */
    function formatDate(dateString) {
        if (!dateString) return 'N/A';
        try {
            const date = new Date(dateString);
            const now = new Date();
            const diffMs = now - date;
            const diffMins = Math.floor(diffMs / 60000);
            
            if (diffMins < 1) return 'Just now';
            if (diffMins < 60) return diffMins + ' min ago';
            if (diffMins < 1440) return Math.floor(diffMins / 60) + ' hours ago';
            return date.toLocaleDateString() + ' ' + date.toLocaleTimeString();
        } catch (e) {
            return dateString;
        }
    }
    
})();