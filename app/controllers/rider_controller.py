from flask import Blueprint, request, session, jsonify, current_app, render_template, flash, redirect, url_for
from functools import wraps
from app.utils.decorators import login_required
from app.services.database import Database
from datetime import datetime
import traceback

rider_bp = Blueprint('rider', __name__)

def rider_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('user_role') != 'rider':
            return jsonify({
                'success': False,
                'message': 'Access denied. Riders only.',
                'error_type': 'authentication_error'
            }), 403
        return f(*args, **kwargs)
    return decorated_function

@rider_bp.route('/available-orders')
@login_required
@rider_required
def available_orders():
    """API endpoint to get available orders for pickup"""
    try:
        from app.services.database import Database
        from datetime import datetime
        
        db = Database()
        rider_id = session['user_id']
        current_app.logger.info(f'Fetching available orders for rider {rider_id}')
        
        # Mark rider as available
        try:
            # Check if rider exists in availability table
            rider_check = db.execute_query(
                "SELECT id FROM rider_availability WHERE rider_id = %s",
                (rider_id,),
                fetch=True
            )
            
            if rider_check:
                # Update existing rider
                db.execute_query(
                    """
                    UPDATE rider_availability 
                    SET is_online = 1, 
                        is_available = 1, 
                        last_online = %s 
                    WHERE rider_id = %s
                    """,
                    (datetime.utcnow(), rider_id)
                )
            else:
                # Insert new rider
                db.execute_query(
                    """
                    INSERT INTO rider_availability 
                    (rider_id, is_online, is_available, last_online)
                    VALUES (%s, 1, 1, %s)
                    """,
                    (rider_id, datetime.utcnow())
                )
                
        except Exception as e:
            current_app.logger.error(f'Error updating rider availability: {str(e)}')
        
        # Get available orders (not assigned to any rider and in a ready state)
        try:
            # Get available orders using raw SQL
            query = """
                SELECT
                    o.id,
                    o.status,
                    o.seller_id,
                    o.user_id,
                    o.total_amount,
                    o.created_at,
                    o.updated_at,
                    o.shipping_address,
                    u.first_name as seller_first_name,
                    u.last_name as seller_last_name,
                    u.phone as seller_phone,
                    u.address as seller_address,
                    (SELECT COUNT(*) FROM order_items WHERE order_id = o.id) as item_count,
                    (SELECT SUM(quantity * price_at_time) FROM order_items WHERE order_id = o.id) as calculated_total
                FROM orders o
                JOIN users u ON o.seller_id = u.id
                WHERE o.status IN ('confirmed', 'preparing', 'shipped')
                AND o.rider_id IS NULL
                ORDER BY o.created_at ASC
            """
            
            available_orders = db.execute_query(query, fetch=True) or []
            current_app.logger.info(f'Found {len(available_orders)} available orders')
            
            # Process orders
            orders_list = []
            for order in available_orders:
                try:
                    # Generate order number from ID
                    order_number = f'ORD-{order["id"]:05d}'
                    
                    # Get seller information
                    seller_info = {
                        'name': f"{order.get('seller_first_name', '')} {order.get('seller_last_name', '')}".strip() or 'Unknown Seller',
                        'address': order.get('seller_address', 'Not specified'),
                        'phone': order.get('seller_phone', 'Not specified')
                    }
                    
                    # Calculate total amount (use calculated_total if available, otherwise use total_amount)
                    total_amount = 0
                    if 'calculated_total' in order and order['calculated_total'] is not None:
                        try:
                            total_amount = float(order['calculated_total'])
                        except (ValueError, TypeError):
                            total_amount = float(order.get('total_amount', 0))
                    
                    # Format order data
                    order_data = {
                        'id': order['id'],
                        'order_number': order_number,
                        'status': order.get('status', 'unknown'),
                        'total_amount': total_amount,
                        'item_count': order.get('item_count', 0),
                        'created_at': order.get('created_at').isoformat() if order.get('created_at') else None,
                        'seller': seller_info,
                        'shipping_address': {
                            'street': order.get('shipping_address', 'Not specified'),
                            'city': order.get('shipping_city', ''),
                            'province': order.get('shipping_province', '')
                        }
                    }
                    orders_list.append(order_data)
                    
                except Exception as e:
                    current_app.logger.error(f'Error processing order {order.get("id", "unknown")}: {str(e)}')
                    continue
            
            return jsonify({
                'success': True,
                'orders': orders_list
            })
            
        except Exception as e:
            current_app.logger.error(f'Error fetching available orders: {str(e)}', exc_info=True)
            return jsonify({
                'success': False,
                'message': 'Failed to fetch available orders',
                'error': str(e)
            }), 500
            
    except Exception as e:
        current_app.logger.error(f'Unexpected error in available_orders: {str(e)}', exc_info=True)
        return jsonify({
            'success': False,
            'message': 'An unexpected error occurred',
            'error': str(e)
        }), 500


@rider_bp.route('/delivery/accept', methods=['POST'])
@login_required
@rider_required
def accept_delivery():
    """Accept a delivery order - First come first serve (with race condition protection)"""
    try:
        rider_id = session['user_id']
        order_id = request.form.get('order_id')
        
        if not order_id:
            return jsonify({'success': False, 'message': 'Order ID is required'}), 400
        
        db = Database()
        conn = db.connect()
        try:
            cursor = conn.cursor(dictionary=True)

            # 🔒 CRITICAL: Use FOR UPDATE to prevent double-assignment
            cursor.execute("""
                SELECT id FROM orders 
                WHERE id = %s AND status = 'confirmed' AND (rider_id IS NULL OR rider_id = 0)
                FOR UPDATE
            """, (order_id,))
            if not cursor.fetchone():
                conn.rollback()
                return jsonify({
                    'success': False,
                    'message': 'Order not available'
                }), 409

            # Assign rider
            cursor.execute("""
                UPDATE orders 
                SET rider_id = %s, status = 'assigned_to_rider', updated_at = NOW()
                WHERE id = %s
            """, (rider_id, order_id))

            # Create delivery record
            cursor.execute("""
                INSERT INTO deliveries (order_id, rider_id, status, assigned_at)
                VALUES (%s, %s, 'assigned', NOW())
            """, (order_id, rider_id))

            conn.commit()

            # ✅ Notify other riders via GLOBAL socketio
            try:
                from app.services.websocket_service import socketio as ws_socketio
                if ws_socketio and hasattr(ws_socketio, 'emit'):
                    ws_socketio.emit('order_taken', {
                        'order_id': order_id,
                        'rider_id': rider_id
                    }, room='available_orders')
                    current_app.logger.info(f"Emitted order_taken event for order {order_id}")
                else:
                    current_app.logger.warning("SocketIO not available, skipping notification")
            except Exception as e:
                current_app.logger.error(f"Error emitting socketio event: {e}")

            return jsonify({'success': True, 'message': 'Delivery accepted successfully!'})

        except Exception as e:
            conn.rollback()
            current_app.logger.error(f"DB error in accept_delivery: {e}")
            return jsonify({'success': False, 'message': 'Database error'}), 500
        finally:
            conn.close()

    except Exception as e:
        current_app.logger.error(f"Unexpected error in accept_delivery: {e}")
        return jsonify({'success': False, 'message': 'Server error'}), 500

@rider_bp.route('/order/<int:order_id>/details')
@login_required
@rider_required
def order_details(order_id):
    """Get detailed information about an order (for modal)"""
    try:
        current_app.logger.info(f"Fetching details for order ID: {order_id}")
        db = Database()

        # First check if order exists at all
        existence_check = db.execute_query("SELECT id, status, rider_id FROM orders WHERE id = %s", (order_id,), fetchone=True)
        if not existence_check:
            current_app.logger.warning(f"Order {order_id} does not exist in database")
            return jsonify({'success': False, 'message': 'Order not found'}), 404

        current_app.logger.info(f"Order {order_id} exists with status: {existence_check['status']}, rider_id: {existence_check['rider_id']}")

        order_query = """
            SELECT o.*,
                   CONCAT('ORD-', LPAD(o.id, 5, '0')) as order_number,
                   COALESCE(c.first_name, '') as customer_first_name,
                   COALESCE(c.last_name, 'Customer') as customer_last_name,
                   COALESCE(c.phone, 'N/A') as customer_phone,
                   COALESCE(c.email, 'N/A') as customer_email
            FROM orders o
            LEFT JOIN users c ON o.user_id = c.id
            WHERE o.id = %s
        """
        order = db.execute_query(order_query, (order_id,), fetchone=True)

        if not order:
            current_app.logger.error(f"Order {order_id} exists but detailed query returned no results")
            return jsonify({'success': False, 'message': 'Order not found'}), 404
        
        order = dict(order)
        order['customer_name'] = f"{order['customer_first_name']} {order['customer_last_name']}".strip() or 'Customer'
        
        items_query = """
            SELECT oi.*, 
                   oi.price_at_time,
                   p.name, 
                   p.image_url
            FROM order_items oi
            LEFT JOIN products p ON oi.product_id = p.id
            WHERE oi.order_id = %s
        """
        items = db.execute_query(items_query, (order_id,), fetch=True) or []
        
        # Build safe HTML
        html = f"""
        <div class="order-details">
            <div class="row mb-3">
                <div class="col-md-6">
                    <h6>Customer Information</h6>
                    <p><strong>Name:</strong> {order['customer_name']}</p>
                    <p><strong>Phone:</strong> {order['customer_phone']}</p>
                    <p class="shipping-address"><strong>Address:</strong><br>{order.get('shipping_address', 'N/A')}</p>
                </div>
                <div class="col-md-6">
                    <h6>Order Information</h6>
                    <p><strong>Order Number:</strong> {order['order_number']}</p>
                    <p><strong>Total:</strong> ₱{float(order.get('total_amount', 0)):.2f}</p>
                    <p><strong>Payment:</strong> {order.get('payment_method', 'N/A').upper()}</p>
                    <p><strong>Status:</strong> <span class="badge bg-success">{order.get('status', 'N/A').replace('_', ' ').title()}</span></p>
                </div>
            </div>
            <hr>
            <h6>Order Items ({len(items)})</h6>
            <div class="table-responsive">
                <table class="table table-sm">
                    <thead>
                        <tr>
                            <th>Product</th>
                            <th>Quantity</th>
                            <th>Price</th>
                            <th>Subtotal</th>
                        </tr>
                    </thead>
                    <tbody>
        """
        
        for item in items:
            subtotal = item['quantity'] * item['price_at_time']
            html += f"""
                        <tr>
                            <td>{item.get('name', 'Product')}</td>
                            <td>{item['quantity']}</td>
                            <td>₱{float(item['price_at_time']):.2f}</td>
                            <td>₱{float(subtotal):.2f}</td>
                        </tr>
            """
        
        html += """
                    </tbody>
                </table>
            </div>
        </div>
        """
        
        return jsonify({'success': True, 'html': html})
        
    except Exception as e:
        current_app.logger.error(f"Error fetching order details: {e}")
        return jsonify({'success': False, 'message': 'Failed to load order details'}), 500

@rider_bp.route('/dashboard')
@login_required
@rider_required
def dashboard():
    """Rider dashboard page"""
    try:
        db = Database()
        rider_id = session.get('user_id')
        
        deliveries = []
        try:
            deliveries_query = """
                SELECT d.*, o.shipping_address, o.total_amount,
                       CONCAT('ORD-', LPAD(o.id, 5, '0')) as order_number,
                       CONCAT(c.first_name, ' ', c.last_name) as customer_name,
                       c.phone as customer_phone
                FROM deliveries d
                JOIN orders o ON d.order_id = o.id
                JOIN users c ON o.user_id = c.id
                WHERE d.rider_id = %s
                ORDER BY d.assigned_at DESC
                LIMIT 20
            """
            deliveries = db.execute_query(deliveries_query, (rider_id,), fetch=True) or []
        except Exception as e:
            current_app.logger.error(f"Error fetching deliveries: {e}")
        
        stats = {'pending_deliveries': 0, 'completed_deliveries': 0, 'monthly_earnings': 0.00, 'avg_rating': 0.0}
        try:
            stats_query = """
                SELECT 
                    COUNT(CASE WHEN status IN ('assigned', 'picked_up', 'on_the_way') THEN 1 END) as pending_deliveries,
                    COUNT(CASE WHEN status = 'delivered' THEN 1 END) as completed_deliveries
                FROM deliveries 
                WHERE rider_id = %s
            """
            stats_result = db.execute_query(stats_query, (rider_id,), fetchone=True)
            if stats_result:
                stats.update(stats_result)
        except Exception as e:
            current_app.logger.error(f"Error fetching stats: {e}")
        
        return render_template('rider/dashboard.html',
                             rider_id=rider_id,
                             deliveries=deliveries,
                             **stats)
                           
    except Exception as e:
        current_app.logger.error(f"Error in rider dashboard: {e}")
        flash('An error occurred while loading the dashboard.', 'error')
        return render_template('rider/dashboard.html',
                             rider_id=session.get('user_id'),
                             deliveries=[],
                             pending_deliveries=0,
                             completed_deliveries=0,
                             monthly_earnings=0.00,
                             avg_rating=0.0)