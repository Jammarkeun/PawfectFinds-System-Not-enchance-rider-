from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify, current_app
from app.utils.decorators import login_required, seller_required
from app.models.user import User
from app.models.product import Product
from app.models.order import Order
# FIXED: Import socketio from app directly
from app import socketio  # ← Use this instead of from app.services.websocket_service
from app.models.seller_request import SellerRequest
from app.services.database import Database
from app.forms import SellerProductForm, OrderStatusForm, SellerApplicationForm
from app.models.delivery import Delivery
from app.models.rider_availability import RiderAvailability
from datetime import datetime, timedelta
import traceback

seller_bp = Blueprint('seller', __name__)

@seller_bp.route('/dashboard')
@login_required
@seller_required
def dashboard():
    seller_id = session['user_id']
    seller = User.get_by_id(seller_id)
    
    # Seller statistics
    db = Database()
    
    # Product stats
    product_stats = db.execute_query("""
        SELECT 
            COUNT(*) as total_products,
            SUM(CASE WHEN status = 'active' THEN 1 ELSE 0 END) as active_products,
            SUM(CASE WHEN stock_quantity = 0 THEN 1 ELSE 0 END) as out_of_stock
        FROM products WHERE seller_id = %s
    """, (seller_id,), fetch=True, fetchone=True)
    
    # Order stats
    order_stats = db.execute_query("""
        SELECT 
            COUNT(*) as total_orders,
            SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending_orders,
            SUM(CASE WHEN status = 'delivered' THEN 1 ELSE 0 END) as delivered_orders,
            SUM(total_amount) as total_revenue
        FROM orders 
        WHERE seller_id = %s
    """, (seller_id,), fetch=True, fetchone=True)
    
    # All products
    products = Product.list(seller_id=seller_id, status=None)
    
    # Recent orders
    recent_orders = Order.list_for_seller(seller_id, limit=10)
    
    # Top selling products
    top_products = db.execute_query("""
        SELECT 
            p.id, 
            p.name, 
            p.price, 
            p.image_url,
            COUNT(oi.id) as orders_count, 
            COALESCE(SUM(oi.quantity), 0) as total_sold,
            COALESCE(SUM(oi.quantity * oi.price_at_time), 0) as total_revenue
        FROM products p
        LEFT JOIN order_items oi ON p.id = oi.product_id
        WHERE p.seller_id = %s
        GROUP BY p.id, p.name, p.price, p.image_url
        ORDER BY total_sold DESC, p.name ASC
        LIMIT 5
    """, (seller_id,), fetch=True)
    
    # Convert Decimal to float for JSON serialization and ensure all values are present
    if top_products:
        for product in top_products:
            product['price'] = float(product.get('price', 0))
            product['total_sold'] = int(product.get('total_sold', 0))
            product['total_revenue'] = float(product.get('total_revenue', 0))
            product['orders_count'] = int(product.get('orders_count', 0))
    
    # Revenue trends (last 12 months) for the chart
    revenue_trends = db.execute_query("""
        SELECT 
            DATE_FORMAT(created_at, '%Y-%m') as month,
            COALESCE(SUM(total_amount), 0) as revenue
        FROM orders 
        WHERE seller_id = %s 
          AND created_at >= DATE_SUB(NOW(), INTERVAL 12 MONTH)
        GROUP BY DATE_FORMAT(created_at, '%Y-%m')
        ORDER BY month ASC
    """, (seller_id,), fetch=True) or []
    
    # Generate labels and amounts for the chart
    import calendar
    from datetime import datetime, timedelta
    
    # Generate last 12 months
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365)
    
    # Create a list of all months in the range
    months = []
    current = start_date
    while current <= end_date:
        months.append(current.strftime('%Y-%m'))
        # Move to first day of next month
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1, day=1)
        else:
            current = current.replace(month=current.month + 1, day=1)
    
    # Create a dictionary of month: revenue for easy lookup
    revenue_dict = {item['month']: float(item['revenue'] or 0) for item in revenue_trends}
    
    # Order status breakdown for the pie chart
    order_status_breakdown = db.execute_query("""
        SELECT 
            status, 
            COUNT(*) as count
        FROM orders
        WHERE seller_id = %s
        GROUP BY status
    """, (seller_id,), fetch=True) or []
    
    # Generate data for all months, using 0 for months with no data
    sales_labels = [datetime.strptime(month, '%Y-%m').strftime('%b %Y') for month in months[-12:]]
    sales_amounts = [float(revenue_dict.get(month, 0)) for month in months[-12:]]
    
    # Get order status breakdown
    order_status_breakdown = db.execute_query("""
        SELECT 
            status, 
            COUNT(*) as count
        FROM orders
        WHERE seller_id = %s
        GROUP BY status
    """, (seller_id,), fetch=True) or [{'status': 'No data', 'count': 1}]
    
    # Format order status data for the chart
    order_status_breakdown = [{
        'status': item['status'] or 'Unknown', 
        'count': int(item['count']) if item['count'] is not None else 0
    } for item in order_status_breakdown]
    
    
    
    # Debug output (temporary)
    print("Sales Labels:", sales_labels)
    print("Sales Amounts:", sales_amounts)
    print("Order Status Breakdown:", order_status_breakdown)
    
    # Top customers
    top_customers = db.execute_query("""
        SELECT 
            u.id,
            u.first_name,
            u.last_name,
            u.email,
            COUNT(o.id) as order_count,
            SUM(o.total_amount) as total_spent
        FROM users u
        JOIN orders o ON u.id = o.user_id
        WHERE o.seller_id = %s
        GROUP BY u.id, u.first_name, u.last_name, u.email
        ORDER BY total_spent DESC
        LIMIT 5
    """, (seller_id,), fetch=True) or []
    
    # Process query results to ensure JSON serialization
    def process_query_result(rows):
        if not rows:
            return []
        result = []
        for row in rows:
            if isinstance(row, dict):
                processed = {}
                for k, v in row.items():
                    if hasattr(v, '__float__'):
                        processed[k] = float(v)
                    else:
                        processed[k] = v
                result.append(processed)
            else:
                # Handle case where rows are tuples
                cols = ['status', 'count'] if len(row) == 2 else ['month', 'revenue']
                result.append(dict(zip(cols, row)))
        return result
    
    # Process the data for the template
    revenue_trends = process_query_result(revenue_trends)
    order_status_breakdown = process_query_result(order_status_breakdown)
    
    # Prepare chart data
    sales_labels = []
    sales_amounts = []
    
    # Default empty data for the chart
    if not revenue_trends:
        # Generate empty data for 12 months if no sales data
        now = datetime.now()
        sales_labels = [(now - timedelta(days=30 * i)).strftime('%b %Y') for i in range(11, -1, -1)]
        sales_amounts = [0] * 12
    else:
        # Use actual sales data
        for trend in revenue_trends:
            month = datetime.strptime(trend['month'], '%Y-%m').strftime('%b %Y')
            sales_labels.append(month)
            sales_amounts.append(float(trend.get('revenue', 0)))
    
    return render_template('seller/dashboard.html', 
                         seller=seller,
                         product_stats=product_stats or {},
                         order_stats=order_stats or {},
                         orders=recent_orders or [],
                         top_products=top_products or [],
                         top_customers=top_customers or [],
                         sales_labels=sales_labels,
                         sales_amounts=sales_amounts,
                         order_status_breakdown=order_status_breakdown,
                         revenue_trends=revenue_trends)

@seller_bp.route('/products')
@login_required
@seller_required
def products():
    seller_id = session['user_id']
    products = Product.list(seller_id=seller_id, status=None)
    db = Database()
    categories = db.execute_query("SELECT * FROM categories WHERE is_active = 1", fetch=True)
    return render_template('seller/products.html', products=products, categories=categories)

@seller_bp.route('/products/add', methods=['POST'])
@login_required
@seller_required
def add_product():
    seller_id = session['user_id']

    # Get categories to populate form choices
    db = Database()
    categories = db.execute_query("SELECT id, name FROM categories WHERE is_active = 1", fetch=True)

    form = SellerProductForm()
    form.category_id.choices = [(cat['id'], cat['name']) for cat in categories]

    if form.validate_on_submit():
        try:
            # Handle image upload
            image_url = None
            if form.image.data and hasattr(form.image.data, 'filename') and form.image.data.filename:
                from werkzeug.utils import secure_filename
                import os
                from flask import current_app
                from PIL import Image

                filename = secure_filename(form.image.data.filename)
                # Create unique filename
                import uuid
                unique_filename = f"{uuid.uuid4().hex}_{filename}"
                upload_path = os.path.join(current_app.root_path, 'static', 'uploads', 'products', unique_filename)

                # Ensure directory exists
                os.makedirs(os.path.dirname(upload_path), exist_ok=True)

                # Process and save the image
                try:
                    image = Image.open(form.image.data)

                    # Convert to RGB if necessary (for JPEG compatibility)
                    if image.mode in ("RGBA", "P"):
                        image = image.convert("RGB")

                    # Save with optimization - handle different formats
                    if filename.lower().endswith(('.jpg', '.jpeg')):
                        image.save(upload_path, 'JPEG', optimize=True, quality=85)
                    elif filename.lower().endswith('.png'):
                        image.save(upload_path, 'PNG', optimize=True)
                    else:
                        # For other formats, convert to JPEG
                        image.save(upload_path, 'JPEG', optimize=True, quality=85)

                    image_url = f"/static/uploads/products/{unique_filename}"
                except Exception as img_error:
                    print(f"Image processing error: {img_error}")
                    flash('Failed to process image. Please try a different image file.', 'error')
                    return redirect(url_for('seller.products'))

            Product.create(
                seller_id=seller_id,
                category_id=form.category_id.data,
                name=form.name.data.strip(),
                description=form.description.data.strip() if form.description.data else None,
                price=form.price.data,
                stock_quantity=form.stock_quantity.data,
                image_url=image_url
            )
            flash('Product created successfully!', 'success')
        except Exception as e:
            print(f"Product creation error: {e}")
            flash('Failed to create product. Please try again.', 'error')
    else:
        flash('Please correct the errors in the form.', 'error')

    return redirect(url_for('seller.products'))

@seller_bp.route('/products/<int:product_id>/edit', methods=['POST'])
@login_required
@seller_required
def edit_product(product_id):
    seller_id = session['user_id']
    product = Product.get_by_id(product_id)
    if not product or product['seller_id'] != seller_id:
        flash('Product not found or unauthorized.', 'error')
        return redirect(url_for('seller.products'))

    # Get categories to populate form choices
    db = Database()
    categories = db.execute_query("SELECT id, name FROM categories WHERE is_active = 1", fetch=True)

    form = SellerProductForm()
    form.category_id.choices = [(cat['id'], cat['name']) for cat in categories]

    if form.validate_on_submit():
        try:
            # Handle image upload
            image_url = product['image_url']  # Keep existing image by default
            if form.image.data:
                from werkzeug.utils import secure_filename
                import os
                from flask import current_app
                from PIL import Image

                filename = secure_filename(form.image.data.filename)
                # Create unique filename
                import uuid
                unique_filename = f"{uuid.uuid4().hex}_{filename}"
                upload_path = os.path.join(current_app.root_path, 'static', 'uploads', 'products', unique_filename)

                # Ensure directory exists
                os.makedirs(os.path.dirname(upload_path), exist_ok=True)

                # Process and save the image
                image = Image.open(form.image.data)

                # Convert to RGB if necessary (for JPEG compatibility)
                if image.mode in ("RGBA", "P"):
                    image = image.convert("RGB")

                # Save with optimization
                image.save(upload_path, optimize=True, quality=85)
                image_url = f"/static/uploads/products/{unique_filename}"

            Product.update(product_id,
                          name=form.name.data.strip(),
                          category_id=form.category_id.data,
                          description=form.description.data.strip() if form.description.data else None,
                          price=form.price.data,
                          stock_quantity=form.stock_quantity.data,
                          image_url=image_url,
                          status=form.status.data)
            flash('Product updated!', 'success')
        except Exception as e:
            flash('Failed to update product.', 'error')
    else:
        flash('Please correct the errors in the form.', 'error')

    return redirect(url_for('seller.products'))

@seller_bp.route('/products/<int:product_id>/delete', methods=['POST'])
@login_required
@seller_required
def delete_product(product_id):
    seller_id = session['user_id']
    product = Product.get_by_id(product_id)
    if not product or product['seller_id'] != seller_id:
        flash('Product not found or unauthorized.', 'error')
        return redirect(url_for('seller.products'))
    try:
        Product.delete(product_id)
        flash('Product deleted.', 'info')
    except Exception as e:
        # If hard delete fails due to FK constraints (product in orders), soft-delete
        try:
            Product.update(product_id, status='inactive')
            flash('Product archived (inactive) because it has existing orders.', 'warning')
        except Exception:
            flash('Failed to delete product.', 'error')
    return redirect(url_for('seller.products'))

@seller_bp.route('/orders')
@login_required
@seller_required
def orders():
    seller_id = session['user_id']
    status = request.args.get('status')
    
    # Get orders with additional details
    orders = Order.list_for_seller(seller_id, status=status)
    
    # Add rider info and delivery status to orders
    db = Database()
    for order in orders:
        # Get delivery info if exists
        delivery = db.execute_query(
            """
            SELECT d.*, 
                   u.first_name as rider_first_name, 
                   u.last_name as rider_last_name,
                   u.phone as rider_phone
            FROM deliveries d
            LEFT JOIN users u ON d.rider_id = u.id
            WHERE d.order_id = %s
            """,
            (order['id'],),
            fetch=True,
            fetchone=True
        )
        
        if delivery:
            order['rider_id'] = delivery['rider_id']
            order['rider_name'] = f"{delivery.get('rider_first_name', '')} {delivery.get('rider_last_name', '')}".strip() or 'Unknown Rider'
            order['rider_phone'] = delivery.get('rider_phone', '')
            order['delivery_status'] = delivery.get('status', 'pending')
            order['assigned_at'] = delivery.get('assigned_at')
            order['picked_up_at'] = delivery.get('picked_up_at')
            order['delivered_at'] = delivery.get('delivered_at')
        else:
            order['rider_name'] = None
            order['rider_phone'] = None
            order['delivery_status'] = None
            
        # Add order items count
        order['item_count'] = len(order.get('items', []))
    
    # Get available statuses for the status filter
    statuses = db.execute_query(
        """
        SELECT DISTINCT status 
        FROM orders 
        WHERE seller_id = %s 
        ORDER BY status
        """,
        (seller_id,),
        fetch=True
    )
    
    return render_template('seller/orders.html', 
                         orders=orders, 
                         status=status,
                         statuses=[s['status'] for s in statuses] if statuses else [])

@seller_bp.route('/available-riders')
@seller_required
@login_required
def get_available_riders():
    """Get list of available riders for order assignment"""
    try:
        # Get available riders using the RiderAvailability model
        available_riders = RiderAvailability.get_available_riders()
        
        # Format the response
        riders_list = []
        for rider in available_riders:
            riders_list.append({
                'id': rider['id'],
                'name': f"{rider.get('first_name', '')} {rider.get('last_name', '')}".strip(),
                'phone': rider.get('phone', ''),
                'current_lat': rider.get('current_lat'),
                'current_lng': rider.get('current_lng'),
                'is_available': True,  # Since we're getting available riders
                'current_deliveries': 0  # You might want to add this to your query if needed
            })
            
        return jsonify(riders_list)
        
    except Exception as e:
        current_app.logger.error(f"Error getting available riders: {e}")
        return jsonify({'error': 'Failed to fetch available riders'}), 500

@seller_bp.route('/assign-rider', methods=['POST'])
@login_required
@seller_required
def assign_rider():
    order_id = request.form.get('order_id')
    rider_id = request.form.get('rider_id')
    delivery_notes = request.form.get('delivery_notes', '')
    
    if not order_id or not rider_id:
        flash('Missing required parameters.', 'error')
        return redirect(url_for('seller.orders'))
        
    try:
        # Check if order exists and belongs to seller
        order = Order.get_by_id(order_id)
        if not order or order['seller_id'] != session['user_id']:
            flash('Order not found or unauthorized.', 'error')
            return redirect(url_for('seller.orders'))

        # Allow re-assignment if rider is already assigned
        if Delivery.assign_rider(order_id, rider_id, delivery_notes):
            # Get rider details for notification
            rider = User.get_by_id(rider_id)
            rider_name = f"{rider['first_name']} {rider['last_name']}" if rider else 'a rider'
            
            if order.get('rider_id'):
                flash(f'Rider changed to {rider_name} successfully. The rider has been notified.', 'success')
            else:
                flash(f'Rider {rider_name} assigned successfully. The rider has been notified.', 'success')
                
            # Update order status to assigned_to_rider if it was ready_for_delivery
            if order.get('status') == 'ready_for_delivery':
                Order.update_status(order_id, 'assigned_to_rider', rider_id=rider_id)
        else:
            flash('Failed to assign rider. Please try again.', 'error')
            
    except Exception as e:
        current_app.logger.error(f"Error in assign_rider: {e}")
        flash('An error occurred while assigning the rider. Please try again.', 'error')
    
    return redirect(url_for('seller.orders'))

# Add this to your seller_controller.py in the update_order_status function
# Replace the 'confirmed' status handling section

@seller_bp.route('/orders/update-status', methods=['POST'])
@login_required
@seller_required
def update_order_status():
    form = OrderStatusForm()
    if form.validate_on_submit():
        order_id = request.form.get('order_id')
        status = form.status.data
        current_app.logger.info(f"Attempting to update order {order_id} status to {status}")
        
        try:
            # Fetch order to get customer info for notification
            order = Order.get_by_id(order_id)
            if not order:
                current_app.logger.error(f"Order {order_id} not found")
                flash('Order not found.', 'error')
                return redirect(url_for('seller.orders'))
                
            if order['seller_id'] != session['user_id']:
                current_app.logger.warning(f"Unauthorized access attempt to order {order_id} by user {session['user_id']}")
                flash('You are not authorized to update this order.', 'error')
                return redirect(url_for('seller.orders'))

            # Log the status update
            current_app.logger.info(f"Updating order {order_id} from {order.get('status')} to {status}")
            
            # Handle different status updates
            if status == 'confirmed':
                success = Order.update_status(order_id, 'confirmed')
                if success:
                    # Get order details for notification
                    order_details = {
                        'id': order_id,
                        'order_id': order_id,
                        'order_number': order.get('order_number', f"ORD-{str(order_id).zfill(5)}"),
                        'total_amount': float(order.get('total_amount', 0)),
                        'item_count': len(order.get('items', [])),
                        'created_at': order.get('created_at').strftime('%Y-%m-%d %H:%M:%S') if hasattr(order.get('created_at'), 'strftime') else str(order.get('created_at', '')),
                        'shipping_address': order.get('shipping_address', ''),
                        'status': 'confirmed',
                        'seller_id': order['seller_id'],
                        'customer_name': f"{order.get('customer_first_name', '')} {order.get('customer_last_name', '')}".strip() or 'Customer',
                        'customer_phone': order.get('customer_phone', ''),
                        'payment_method': order.get('payment_method', 'COD'),
                        'payment_status': order.get('payment_status', 'pending')
                    }
                    
                    try:
                        # Use socketio imported at the top of the file
                        current_app.logger.info(f"🔔 Emitting WebSocket events for order {order_id}")
                        
                        # Event 1: Legacy event for riders_room
                        socketio.emit('new_order_confirmed', 
                                    {'order': order_details},
                                    room='riders_room')
                        current_app.logger.info(f"✓ Emitted new_order_confirmed to riders_room")
                        
                        # Event 2: New event for available_orders room
                        socketio.emit('new_available_order',
                                      {'order': order_details},
                                      room='available_orders')
                        current_app.logger.info(f"✓ Emitted new_available_order to available_orders")
                        
                        # Event 3: Broadcast as fallback
                        socketio.emit('new_delivery_opportunity', 
                                      {'order': order_details}, 
                                      broadcast=True)
                        current_app.logger.info(f"✓ Broadcasted new_delivery_opportunity")
                        
                        current_app.logger.info(f"✅ Successfully notified riders about order {order_id}")
                    except Exception as e:
                        current_app.logger.error(f"❌ Error notifying riders: {str(e)}\n{traceback.format_exc()}")
                    
                    flash('Order confirmed and riders have been notified.', 'success')
                else:
                    current_app.logger.error(f"Failed to update order {order_id} status to {status}")
                    flash('Failed to update order status. Please try again.', 'error')
                    
            elif status == 'ready_for_delivery':
                success = Order.update_status(order_id, 'ready_for_delivery')
                if success:
                    # Get order details for notification
                    order_details = {
                        'id': order_id,
                        'order_id': order_id,
                        'order_number': order.get('order_number', f"ORD-{str(order_id).zfill(5)}"),
                        'total_amount': float(order.get('total_amount', 0)),
                        'item_count': len(order.get('items', [])),
                        'created_at': order.get('created_at').strftime('%Y-%m-%d %H:%M:%S') if hasattr(order.get('created_at'), 'strftime') else str(order.get('created_at', '')),
                        'shipping_address': order.get('shipping_address', ''),
                        'status': 'ready_for_delivery',
                        'seller_id': order['seller_id']
                    }
                    
                    try:
                        # Use socketio imported at the top of the file
                        current_app.logger.info(f"🔔 Notifying riders about order {order_id} ready for delivery")
                        
                        # Notify riders about ready for delivery order
                        socketio.emit('new_available_order', {'order': order_details}, room='available_orders')
                        socketio.emit('new_delivery_available', {'order': order_details}, broadcast=True)
                        
                        current_app.logger.info(f"✅ Notified riders about order {order_id} ready for delivery")
                        flash('Order marked as ready for delivery. Available riders have been notified.', 'success')
                    except Exception as e:
                        current_app.logger.error(f"❌ Error notifying riders: {str(e)}\n{traceback.format_exc()}")
                        flash('Order status updated, but there was an error notifying riders.', 'warning')
                else:
                    current_app.logger.error(f"Failed to update order {order_id} status to {status}")
                    flash('Failed to update order status. Please try again.', 'error')
                    
            elif status == 'shipped':
                # If order doesn't have a rider assigned yet, try to auto-assign one
                if not order.get('rider_id'):
                    try:
                        all_riders = Delivery.get_all_riders_with_availability()
                        available_riders = [r for r in all_riders if r['current_deliveries'] < 5]
                        
                        if available_riders:
                            first_rider = available_riders[0]
                            if Delivery.create(order_id, first_rider['id'], 'Auto-assigned on ship'):
                                current_app.logger.info(f"Auto-assigned rider {first_rider['id']} to order {order_id}")
                                flash('Order status updated, rider auto-assigned, and customer notified.', 'success')
                            else:
                                current_app.logger.warning(f"Failed to auto-assign rider to order {order_id}")
                                flash('Order status updated but failed to auto-assign rider.', 'warning')
                        else:
                            current_app.logger.warning(f"No available riders for order {order_id}")
                            flash('No available riders. Please assign manually.', 'warning')
                    except Exception as e:
                        current_app.logger.error(f"Error in auto-assigning rider: {str(e)}")
                        flash('Order status updated, but there was an error assigning a rider.', 'warning')
                else:
                    # Just update status if rider is already assigned
                    if Order.update_status(order_id, status):
                        flash('Order status updated and customer notified.', 'success')
                    else:
                        flash('Failed to update order status. Please try again.', 'error')
            else:
                # For other status updates
                if Order.update_status(order_id, status):
                    flash('Order status updated and customer notified.', 'success')
                else:
                    flash('Failed to update order status. Please try again.', 'error')
                
        except Exception as e:
            current_app.logger.error(f"Error in update_order_status: {str(e)}", exc_info=True)
            flash('Failed to update order status. Please try again.', 'error')
    else:
        error_messages = []
        for field, errors in form.errors.items():
            for error in errors:
                error_messages.append(f"{getattr(form, field).label.text}: {error}")
        
        if error_messages:
            flash('Please fix the following errors: ' + ' '.join(error_messages), 'error')
        else:
            flash('Invalid form data. Please check the form and try again.', 'error')

    return redirect(url_for('seller.orders'))

# ... (rest of the code remains the same)
def order_details(order_id):
    order = Order.get_by_id(order_id)
    if not order or order['seller_id'] != session['user_id']:
        return jsonify({'error': 'Order not found or unauthorized.'}), 404
    
    # Add customer details
    user = User.get_by_id(order['user_id'])
    if user:
        order['customer_name'] = f"{user['first_name']} {user['last_name']}"
        order['customer_email'] = user['email']
        order['customer_phone'] = user['phone'] or ''
    else:
        order['customer_name'] = 'Unknown'
        order['customer_email'] = ''
        order['customer_phone'] = ''
    
    order['items_count'] = len(order['items'])
    
    html = render_template('seller/order_detail_modal.html', order=order)
    return jsonify({'html': html})

# Seller application route (for regular users to become sellers)
@seller_bp.route('/apply', methods=['GET', 'POST'])
@login_required
def apply():
    """Apply to become a seller"""
    user = User.get_by_id(session['user_id'])
    
    # Check if user is already a seller
    if user['role'] == 'seller':
        flash('You are already a seller.', 'info')
        return redirect(url_for('seller.dashboard'))
    
    # Check if user has a pending application
    existing_request = SellerRequest.get_by_user_id(session['user_id'])
    if existing_request and existing_request['status'] == 'pending':
        flash('You already have a pending seller application.', 'info')
        return render_template('seller/application_pending.html', request=existing_request)
    
    form = SellerApplicationForm()
    if form.validate_on_submit():
        try:
            SellerRequest.create(
                user_id=session['user_id'],
                business_name=form.business_name.data.strip(),
                business_description=form.business_description.data.strip(),
                business_address=form.business_address.data.strip(),
                business_phone=form.business_phone.data.strip(),
                tax_id=form.tax_id.data.strip() if form.tax_id.data else None
            )
            flash('Your seller application has been submitted! We will review it and get back to you.', 'success')
            return redirect(url_for('user.dashboard'))
        except Exception as e:
            flash('Failed to submit application. Please try again.', 'error')
    
    return render_template('seller/apply.html', form=form)

@seller_bp.route('/analytics')
@login_required
@seller_required
def analytics():
    """Detailed seller analytics"""
    seller_id = session['user_id']
    db = Database()
    
    # Revenue trends (last 12 months)
    revenue_trends = db.execute_query("""
        SELECT DATE_FORMAT(created_at, '%Y-%m') as month,
               COUNT(*) as orders,
               SUM(total_amount) as revenue,
               AVG(total_amount) as avg_order_value
        FROM orders 
        WHERE seller_id = %s 
          AND created_at >= DATE_SUB(NOW(), INTERVAL 12 MONTH)
        GROUP BY DATE_FORMAT(created_at, '%Y-%m')
        ORDER BY month ASC
    """, (seller_id,), fetch=True)
    
    # Product performance
    product_performance = db.execute_query("""
        SELECT p.name, p.price, p.stock_quantity,
               COUNT(oi.id) as times_ordered,
               SUM(oi.quantity) as total_sold,
               SUM(oi.quantity * oi.price_at_time) as total_revenue,
               AVG(r.rating) as avg_rating,
               COUNT(r.id) as review_count
        FROM products p
        LEFT JOIN order_items oi ON p.id = oi.product_id
        LEFT JOIN reviews r ON p.id = r.product_id
        WHERE p.seller_id = %s
        GROUP BY p.id
        ORDER BY total_revenue DESC
    """, (seller_id,), fetch=True)
    
    # Customer insights
    customer_insights = db.execute_query("""
        SELECT u.first_name, u.last_name, u.email,
               COUNT(o.id) as total_orders,
               SUM(o.total_amount) as total_spent,
               MAX(o.created_at) as last_order_date
        FROM users u
        JOIN orders o ON u.id = o.user_id
        WHERE o.seller_id = %s
        GROUP BY u.id
        ORDER BY total_spent DESC
        LIMIT 20
    """, (seller_id,), fetch=True)
    
    # Order status breakdown - ensure we get a list of dicts
    order_status_breakdown = db.execute_query("""
        SELECT status, COUNT(*) as count
        FROM orders
        WHERE seller_id = %s
        GROUP BY status
    """, (seller_id,), fetch=True) or []
    
    # Convert query results to a more manageable format
    def process_query_result(rows):
        if not rows:
            return []
        result = []
        for row in rows:
            if isinstance(row, dict):
                processed = {}
                for k, v in row.items():
                    if hasattr(v, '__float__'):
                        processed[k] = float(v)
                    else:
                        processed[k] = v
                result.append(processed)
            else:
                # Handle case where rows are tuples
                result.append(dict(zip(['status', 'count'], row)))
        return result

    # Process all query results
    revenue_trends = process_query_result(revenue_trends)
    product_performance = process_query_result(product_performance)
    customer_insights = process_query_result(customer_insights)
    order_status_breakdown = process_query_result(order_status_breakdown)
    
    return render_template('seller/analytics.html',
                         revenue_trends=revenue_trends,
                         product_performance=product_performance,
                         customer_insights=customer_insights,
                         order_status_breakdown=order_status_breakdown)

@seller_bp.route('/inventory')
@login_required
@seller_required
def inventory():
    """Inventory management"""
    seller_id = session['user_id']
    
    # Get products with low stock alert
    low_stock_threshold = 5
    products = Product.list(seller_id=seller_id, status=None)
    
    low_stock_products = [p for p in products if p['stock_quantity'] <= low_stock_threshold]
    out_of_stock_products = [p for p in products if p['stock_quantity'] == 0]
    
    return render_template('seller/inventory.html',
                         products=products,
                         low_stock_products=low_stock_products,
                         out_of_stock_products=out_of_stock_products,
                         low_stock_threshold=low_stock_threshold)

@seller_bp.route('/inventory/update-stock', methods=['POST'])
@login_required
@seller_required
def update_stock():
    """Update product stock quantity"""
    try:
        product_id = int(request.form.get('product_id'))
        new_stock = int(request.form.get('stock_quantity'))
        
        if new_stock < 0:
            flash('Stock quantity cannot be negative.', 'error')
            return redirect(url_for('seller.inventory'))
        
        # Verify product belongs to current seller
        seller_id = session['user_id']
        product = Product.get_by_id(product_id)
        
        if not product or product['seller_id'] != seller_id:
            flash('Product not found or unauthorized.', 'error')
            return redirect(url_for('seller.inventory'))
        
        # Update stock
        Product.update(product_id, stock_quantity=new_stock)
        flash(f'Stock updated for "{product["name"]}"', 'success')
        
    except (ValueError, TypeError):
        flash('Invalid input.', 'error')
    except Exception as e:
        flash('Failed to update stock.', 'error')
    
    return redirect(url_for('seller.inventory'))

@seller_bp.route('/bulk-stock-update', methods=['POST'])
@login_required
@seller_required
def bulk_stock_update():
    """Bulk update stock quantities"""
    seller_id = session['user_id']
    
    try:
        updates = request.get_json()
        if not updates:
            return jsonify({'error': 'No updates provided'}), 400
        
        success_count = 0
        for update in updates:
            product_id = int(update['product_id'])
            new_stock = int(update['stock_quantity'])
            
            # Verify ownership
            product = Product.get_by_id(product_id)
            if product and product['seller_id'] == seller_id and new_stock >= 0:
                Product.update(product_id, stock_quantity=new_stock)
                success_count += 1
        
        return jsonify({
            'success': True,
            'message': f'{success_count} products updated successfully'
        })
        
    except Exception as e:
        return jsonify({'error': 'Failed to update stock quantities'}), 500

@seller_bp.route('/reports')
@login_required
@seller_required
def reports():
    """Sales reports for seller"""
    seller_id = session['user_id']
    db = Database()
    
    # Date range from request
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    # Default to last 30 days if no range provided
    if not start_date or not end_date:
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    
    # Sales summary for the period
    sales_summary = db.execute_query("""
        SELECT 
            COUNT(*) as total_orders,
            SUM(total_amount) as total_revenue,
            AVG(total_amount) as avg_order_value,
            MIN(total_amount) as min_order,
            MAX(total_amount) as max_order
        FROM orders
        WHERE seller_id = %s 
          AND DATE(created_at) BETWEEN %s AND %s
    """, (seller_id, start_date, end_date), fetch=True, fetchone=True)
    
    # Daily sales breakdown
    daily_sales = db.execute_query("""
        SELECT DATE(created_at) as date,
               COUNT(*) as orders,
               SUM(total_amount) as revenue
        FROM orders
        WHERE seller_id = %s 
          AND DATE(created_at) BETWEEN %s AND %s
        GROUP BY DATE(created_at)
        ORDER BY date ASC
    """, (seller_id, start_date, end_date), fetch=True)
    
    # Product sales in period
    product_sales = db.execute_query("""
        SELECT p.name, 
               COUNT(oi.id) as times_ordered,
               SUM(oi.quantity) as quantity_sold,
               SUM(oi.quantity * oi.price_at_time) as revenue
        FROM products p
        JOIN order_items oi ON p.id = oi.product_id
        JOIN orders o ON oi.order_id = o.id
        WHERE p.seller_id = %s 
          AND DATE(o.created_at) BETWEEN %s AND %s
        GROUP BY p.id
        ORDER BY revenue DESC
    """, (seller_id, start_date, end_date), fetch=True)
    
    return render_template('seller/reports.html',
                         sales_summary=sales_summary,
                         daily_sales=daily_sales,
                         product_sales=product_sales,
                         start_date=start_date,
                         end_date=end_date)

