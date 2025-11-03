from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from app.models.order import Order
from app.models.user import User
from app.models.review import Review
from app.utils.decorators import login_required
from datetime import datetime, timedelta

order_bp = Blueprint('order', __name__)

@order_bp.route('/<int:order_id>')
@login_required
def view_order(order_id):
    """View order details"""
    order = Order.get_by_id(order_id)
    if not order:
        flash('Order not found.', 'error')
        return redirect(url_for('user.orders'))
    
    user_id = session['user_id']
    user = User.get_by_id(user_id)
    
    # Check if user can view this order
    if user['role'] not in ['admin'] and order['user_id'] != user_id and order['seller_id'] != user_id:
        flash('Unauthorized to view this order.', 'error')
        return redirect(url_for('user.dashboard'))
    
    return render_template('order/details.html', order=order)

@order_bp.route('/<int:order_id>/cancel', methods=['POST'])
@login_required
def cancel_order(order_id):
    """Cancel an order (customer only)"""
    order = Order.get_by_id(order_id)
    if not order:
        flash('Order not found.', 'error')
        return redirect(url_for('user.orders'))
    
    user_id = session['user_id']
    
    # Only customer can cancel their own orders
    if order['user_id'] != user_id:
        flash('Unauthorized to cancel this order.', 'error')
        return redirect(url_for('user.orders'))
    
    # Can only cancel pending or confirmed orders
    if order['status'] not in ['pending', 'confirmed']:
        flash('This order cannot be cancelled as it is already being processed.', 'error')
        return redirect(url_for('order.view_order', order_id=order_id))
    
    try:
        Order.update_status(order_id, 'cancelled')
        
        # Restore stock quantities
        from app.services.database import Database
        db = Database()
        for item in order['items']:
            db.execute_query(
                "UPDATE products SET stock_quantity = stock_quantity + %s WHERE id = %s",
                (item['quantity'], item['product_id'])
            )
        
        flash('Order cancelled successfully. Stock quantities have been restored.', 'success')
    except Exception as e:
        flash('Failed to cancel order.', 'error')
    
    return redirect(url_for('user.orders'))

@order_bp.route('/<int:order_id>/confirm-delivery', methods=['POST'])
@login_required
def confirm_delivery(order_id):
    """Confirm delivery of an order (customer only)"""
    order = Order.get_by_id(order_id)
    if not order:
        flash('Order not found.', 'error')
        return redirect(url_for('user.orders'))
    
    user_id = session['user_id']
    
    # Only customer can confirm delivery
    if order['user_id'] != user_id:
        flash('Unauthorized.', 'error')
        return redirect(url_for('user.orders'))
    
    # Can only confirm if status is 'on_the_way'
    if order['status'] != 'on_the_way':
        flash('Order delivery cannot be confirmed at this time.', 'error')
        return redirect(url_for('order.view_order', order_id=order_id))
    
    try:
        Order.update_status(order_id, 'delivered')
        Order.update_payment_status(order_id, 'paid')  # COD payment completed
        flash('Delivery confirmed! Thank you for your purchase.', 'success')
    except Exception as e:
        flash('Failed to confirm delivery.', 'error')
    
    return redirect(url_for('order.view_order', order_id=order_id))

@order_bp.route('/<int:order_id>/track')
@login_required
def track_order(order_id):
    """Track order status with timeline"""
    order = Order.get_by_id(order_id)
    if not order:
        flash('Order not found.', 'error')
        return redirect(url_for('user.orders'))
    
    user_id = session['user_id']
    user = User.get_by_id(user_id)
    
    # Check if user can track this order
    if user['role'] not in ['admin'] and order['user_id'] != user_id and order['seller_id'] != user_id:
        flash('Unauthorized to track this order.', 'error')
        return redirect(url_for('user.dashboard'))
    
    # Order status timeline
    status_timeline = [
        {'status': 'pending', 'title': 'Order Placed', 'description': 'Your order has been received'},
        {'status': 'confirmed', 'title': 'Order Confirmed', 'description': 'Seller has confirmed your order'},
        {'status': 'preparing', 'title': 'Preparing', 'description': 'Your order is being prepared'},
        {'status': 'shipped', 'title': 'Shipped', 'description': 'Your order has been dispatched'},
        {'status': 'on_the_way', 'title': 'Out for Delivery', 'description': 'Your order is on the way'},
        {'status': 'delivered', 'title': 'Delivered', 'description': 'Order successfully delivered'},
    ]
    
    # Mark completed statuses
    status_order = ['pending', 'confirmed', 'preparing', 'shipped', 'on_the_way', 'delivered']
    current_index = status_order.index(order['status']) if order['status'] in status_order else 0
    
    for i, status in enumerate(status_timeline):
        if i <= current_index:
            status['completed'] = True
        if status['status'] == order['status']:
            status['current'] = True
    
    # Check if order is cancelled
    if order['status'] == 'cancelled':
        status_timeline = [
            {'status': 'pending', 'title': 'Order Placed', 'description': 'Your order was received', 'completed': True},
            {'status': 'cancelled', 'title': 'Order Cancelled', 'description': 'Order has been cancelled', 'current': True, 'cancelled': True}
        ]
    
    return render_template('order/track.html', order=order, status_timeline=status_timeline)

@order_bp.route('/<int:order_id>/review-products')
@login_required
def review_products(order_id):
    """Review products from delivered order"""
    order = Order.get_by_id(order_id)
    if not order:
        flash('Order not found.', 'error')
        return redirect(url_for('user.orders'))
    
    user_id = session['user_id']
    
    # Only customer can review their orders
    if order['user_id'] != user_id:
        flash('Unauthorized.', 'error')
        return redirect(url_for('user.orders'))
    
    # Can only review delivered orders
    if order['status'] != 'delivered':
        flash('You can only review products from delivered orders.', 'error')
        return redirect(url_for('order.view_order', order_id=order_id))
    
    # Get existing reviews for this order's products
    existing_reviews = {}
    for item in order['items']:
        review = Review.get_by_user_product(user_id, item['product_id'])
        if review:
            existing_reviews[item['product_id']] = review
    
    return render_template('order/review_products.html', 
                         order=order, 
                         existing_reviews=existing_reviews)

@order_bp.route('/<int:order_id>/submit-reviews', methods=['POST'])
@login_required
def submit_reviews(order_id):
    """Submit product reviews for an order"""
    order = Order.get_by_id(order_id)
    if not order or order['user_id'] != session['user_id'] or order['status'] != 'delivered':
        flash('Invalid request.', 'error')
        return redirect(url_for('user.orders'))
    
    user_id = session['user_id']
    success_count = 0
    
    for item in order['items']:
        product_id = item['product_id']
        rating = request.form.get(f'rating_{product_id}')
        comment = request.form.get(f'comment_{product_id}', '').strip()
        
        if rating and 1 <= int(rating) <= 5:
            try:
                Review.create(user_id, product_id, int(rating), comment if comment else None)
                success_count += 1
            except Exception as e:
                pass  # Continue with other reviews
    
    if success_count > 0:
        flash(f'{success_count} product review(s) submitted successfully!', 'success')
    else:
        flash('No reviews were submitted.', 'error')
    
    return redirect(url_for('order.view_order', order_id=order_id))

@order_bp.route('/bulk-action', methods=['POST'])
@login_required
def bulk_order_action():
    """Handle bulk actions on orders (for sellers/admins)"""
    user_id = session['user_id']
    user = User.get_by_id(user_id)
    
    if user['role'] not in ['seller', 'admin']:
        flash('Unauthorized.', 'error')
        return redirect(url_for('user.dashboard'))
    
    action = request.form.get('bulk_action')
    selected_orders = request.form.getlist('selected_orders')
    
    if not selected_orders:
        flash('No orders selected.', 'error')
        return redirect(request.referrer or url_for('seller.orders'))
    
    success_count = 0
    
    try:
        order_ids = [int(order_id) for order_id in selected_orders]
        
        for order_id in order_ids:
            order = Order.get_by_id(order_id)
            if not order:
                continue
            
            # Verify authorization
            if user['role'] == 'seller' and order['seller_id'] != user_id:
                continue
            
            # Apply bulk action
            if action == 'confirm' and order['status'] == 'pending':
                Order.update_status(order_id, 'confirmed')
                success_count += 1
            elif action == 'prepare' and order['status'] == 'confirmed':
                Order.update_status(order_id, 'preparing')
                success_count += 1
            elif action == 'ship' and order['status'] == 'preparing':
                Order.update_status(order_id, 'shipped')
                success_count += 1
            elif action == 'out_for_delivery' and order['status'] == 'shipped':
                Order.update_status(order_id, 'on_the_way')
                success_count += 1
    
    except (ValueError, TypeError):
        flash('Invalid selection.', 'error')
        return redirect(request.referrer)
    
    if success_count > 0:
        flash(f'{success_count} orders updated successfully.', 'success')
    else:
        flash('No orders were updated.', 'info')
    
    return redirect(request.referrer or url_for('seller.orders'))

@order_bp.route('/analytics')
@login_required 
def order_analytics():
    """Order analytics (admin only)"""
    user = User.get_by_id(session['user_id'])
    if user['role'] != 'admin':
        flash('Unauthorized.', 'error')
        return redirect(url_for('user.dashboard'))
    
    from app.services.database import Database
    db = Database()
    
    # Order statistics by status
    status_stats = db.execute_query("""
        SELECT status, COUNT(*) as count, SUM(total_amount) as total_value
        FROM orders
        GROUP BY status
        ORDER BY count DESC
    """, fetch=True)
    
    # Orders by payment method
    payment_stats = db.execute_query("""
        SELECT payment_method, COUNT(*) as count, SUM(total_amount) as total_value
        FROM orders
        GROUP BY payment_method
    """, fetch=True)
    
    # Average order processing time (from pending to delivered)
    processing_time_stats = db.execute_query("""
        SELECT AVG(DATEDIFF(updated_at, created_at)) as avg_processing_days,
               MIN(DATEDIFF(updated_at, created_at)) as min_processing_days,
               MAX(DATEDIFF(updated_at, created_at)) as max_processing_days
        FROM orders 
        WHERE status = 'delivered'
    """, fetch=True, fetchone=True)
    
    # Monthly order trends
    monthly_trends = db.execute_query("""
        SELECT DATE_FORMAT(created_at, '%Y-%m') as month,
               COUNT(*) as order_count,
               SUM(total_amount) as revenue,
               AVG(total_amount) as avg_order_value
        FROM orders
        WHERE created_at >= DATE_SUB(NOW(), INTERVAL 12 MONTH)
        GROUP BY DATE_FORMAT(created_at, '%Y-%m')
        ORDER BY month ASC
    """, fetch=True)
    
    return render_template('order/analytics.html',
                         status_stats=status_stats,
                         payment_stats=payment_stats,
                         processing_time_stats=processing_time_stats,
                         monthly_trends=monthly_trends)