from app.services.database import Database
from app.models.cart import Cart
from app.models.shipping import ShippingCalculator
from datetime import datetime
from app.services.websocket_service import socketio
from flask import current_app, jsonify
import math

class Order:
    """Order model to handle order creation and management"""

    @classmethod
    def get_available_deliveries(cls, limit=50):
        """Get orders that are ready for delivery but not yet assigned to any rider"""
        db = Database()
        try:
            print("\n=== Fetching available deliveries ===")
            
            # Get all possible statuses for debugging
            statuses = db.execute_query(
                "SELECT DISTINCT status, COUNT(*) as count FROM orders GROUP BY status",
                fetch=True
            )
            print("Order status distribution:", statuses)
            
            # First, try with the original query
            query = """
                SELECT o.*, 
                       u.first_name as customer_first_name,
                       u.last_name as customer_last_name,
                       u.phone as customer_phone,
                       u.email as customer_email,
                       u.address as customer_address,
                       CONCAT(s.first_name, ' ', s.last_name) as seller_name,
                       s.phone as seller_phone,
                       s.address as seller_address,
                       (SELECT COUNT(*) FROM order_items WHERE order_id = o.id) as item_count,
                       (SELECT SUM(oi.quantity * oi.price_at_time) FROM order_items oi WHERE oi.order_id = o.id) as total_amount
                FROM orders o
                JOIN users u ON o.user_id = u.id
                JOIN users s ON o.seller_id = s.id
                WHERE o.status IN ('confirmed', 'processing', 'ready_for_delivery', 'paid', 'awaiting_shipment', 'pending')
                ORDER BY o.created_at DESC
                LIMIT %s
            """
            
            results = db.execute_query(query, (limit,), fetch=True)
            
            # If no results, try a more permissive query
            if not results:
                print("No results with original query, trying more permissive query...")
                query = """
                    SELECT o.*, 
                           u.first_name as customer_first_name,
                           u.last_name as customer_last_name,
                           u.phone as customer_phone,
                           u.email as customer_email,
                           u.address as customer_address,
                           CONCAT(s.first_name, ' ', s.last_name) as seller_name,
                           s.phone as seller_phone,
                           s.address as seller_address,
                           (SELECT COUNT(*) FROM order_items WHERE order_id = o.id) as item_count,
                           (SELECT SUM(oi.quantity * oi.price_at_time) FROM order_items oi WHERE oi.order_id = o.id) as total_amount
                    FROM orders o
                    JOIN users u ON o.user_id = u.id
                    JOIN users s ON o.seller_id = s.id
                    WHERE o.status IN ('confirmed', 'processing', 'ready_for_delivery', 'paid', 'awaiting_shipment', 'pending')
                    ORDER BY o.created_at DESC
                    LIMIT %s
                """
                results = db.execute_query(query, (limit,), fetch=True)
                
                if results:
                    print(f"Found {len(results)} orders with permissive query")
            
            print(f"Found {len(results) if results else 0} available orders")
            
            # Convert SQL results to a list of dictionaries and handle datetime serialization
            orders = []
            if results:
                for row in results:
                    order_dict = {}
                    for key, value in row.items():
                        # Convert datetime to string
                        if hasattr(value, 'isoformat'):
                            order_dict[key] = value.isoformat()
                        # Convert Decimal to float for JSON serialization
                        elif hasattr(value, 'to_eng_string'):
                            order_dict[key] = float(value)
                        else:
                            order_dict[key] = value
                    orders.append(order_dict)
                    
                    # Log order details for debugging
                    print(f"Available order - ID: {order_dict.get('id')}, "
                          f"Status: {order_dict.get('status')}, "
                          f"Rider ID: {order_dict.get('rider_id')}, "
                          f"Items: {order_dict.get('item_count')}")
            
            return orders
            
        except Exception as e:
            import traceback
            error_msg = f"Error in get_available_deliveries: {str(e)}\n{traceback.format_exc()}"
            print(error_msg)
            return []

    @classmethod
    def create_from_cart(cls, user_id, shipping_address, payment_method='cod', notes=None, shipping_provider_id=None):
        db = Database()
        items = Cart.get_user_cart(user_id)
        if not items:
            return None
            
        # Get user's location (in a real app, this would come from user's profile or address)
        user_location = (14.5995, 120.9842)  # Default to Manila coordinates
        
        # Group by seller - create one order per seller like Shopee
        orders_created = []
        items_by_seller = {}
        
        for item in items:
            items_by_seller.setdefault((item['seller_id'], item.get('seller_location')), []).append(item)
            
        for (seller_id, seller_location), s_items in items_by_seller.items():
            # Calculate subtotal
            subtotal = sum(float(i['price']) * i['quantity'] for i in s_items)
            
            # Calculate shipping fee
            shipping_fee = cls.calculate_shipping_fee(user_location, seller_location, shipping_provider_id)
            
            # Calculate total amount (subtotal + shipping fee)
            total_amount = subtotal + shipping_fee
            
            # Create order with shipping fee
            order_id = db.execute_query(
                """
                INSERT INTO orders (
                    user_id, seller_id, total_amount, shipping_fee, 
                    shipping_provider, shipping_address, payment_method, notes
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    user_id, seller_id, total_amount, shipping_fee,
                    'J&T Express' if not shipping_provider_id else 'Custom Provider',
                    shipping_address, payment_method, notes
                ),
            )
            
            # Add order items
            for item in s_items:
                db.execute_query(
                    """
                    INSERT INTO order_items (order_id, product_id, quantity, price_at_time)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (order_id, item['product_id'], item['quantity'], item['price']),
                )
                # Reduce stock
                db.execute_query(
                    "UPDATE products SET stock_quantity = stock_quantity - %s WHERE id = %s",
                    (item['quantity'], item['product_id']),
                )
                
            orders_created.append(order_id)
            
        # Clear cart after successful order creation
        Cart.clear_cart(user_id)
        return orders_created
        
    @classmethod
    def calculate_shipping_fee(cls, user_location, seller_location, provider_id=None):
        """
        Calculate shipping fee based on distance between user and seller
        
        Args:
            user_location: Tuple of (lat, lng) for user's location
            seller_location: Tuple of (lat, lng) for seller's location
            provider_id: Optional shipping provider ID
            
        Returns:
            float: Calculated shipping fee
        """
        # In a real app, you would use a proper distance calculation
        # For this example, we'll use a simplified version
        if not seller_location or not all(seller_location):
            # Default shipping fee if seller location is not available
            return 50.00
            
        try:
            # Calculate distance (simplified - in a real app, use a proper distance API)
            lat1, lon1 = user_location
            lat2, lon2 = seller_location
            
            # Haversine formula to calculate distance in kilometers
            R = 6371.0  # Earth radius in kilometers
            
            lat1_rad = math.radians(lat1)
            lon1_rad = math.radians(lon1)
            lat2_rad = math.radians(lat2)
            lon2_rad = math.radians(lon2)
            
            dlon = lon2_rad - lon1_rad
            dlat = lat2_rad - lat1_rad
            
            a = math.sin(dlat / 2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2)**2
            c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
            
            distance_km = R * c
            
            # Calculate shipping fee based on distance and provider
            return ShippingCalculator.calculate_fee(distance_km, provider_id)
            
        except Exception as e:
            current_app.logger.error(f"Error calculating shipping fee: {str(e)}")
            return 50.00  # Default shipping fee if calculation fails

    @classmethod
    def get_by_id(cls, order_id):
        """Get order by ID with related information"""
        db = Database()
        order = db.execute_query(
            """
            SELECT o.*, 
                   u.first_name as customer_first_name, 
                   u.last_name as customer_last_name,
                   u.phone as customer_phone,
                   s.business_name as seller_name,
                   s.business_address as seller_address,
                   r.first_name as rider_first_name,
                   r.last_name as rider_last_name,
                   r.phone as rider_phone
            FROM orders o
            LEFT JOIN users u ON o.user_id = u.id
            LEFT JOIN seller_requests s ON o.seller_id = s.user_id
            LEFT JOIN users r ON o.rider_id = r.id
            WHERE o.id = %s
            """, 
            (order_id,), 
            fetch=True, 
            fetchone=True
        )
        
        if not order:
            return None
            
        # Get order items
        items = db.execute_query(
            """
            SELECT oi.id, oi.order_id, oi.product_id, oi.quantity, oi.price_at_time,
                   p.name, p.image_url, p.seller_id
            FROM order_items oi
            JOIN products p ON oi.product_id = p.id
            WHERE oi.order_id = %s
            """,
            (order_id,),
            fetch=True,
        )
        
        # Get delivery information if exists
        delivery = db.execute_query(
            "SELECT * FROM deliveries WHERE order_id = %s",
            (order_id,),
            fetch=True,
            fetchone=True
        )
        
        order['items'] = items
        order['delivery'] = delivery
        
        return order

    @classmethod
    def list_for_user(cls, user_id, limit=None, offset=0):
        db = Database()
        query = "SELECT * FROM orders WHERE user_id = %s ORDER BY created_at DESC"
        if limit:
            query += " LIMIT %s OFFSET %s"
            return db.execute_query(query, (user_id, limit, offset), fetch=True)
        return db.execute_query(query, (user_id,), fetch=True)

    @classmethod
    def update_status(cls, order_id, status, rider_id=None):
        """Update order status and handle delivery assignments"""
        db = Database()
        current_order = cls.get_by_id(order_id)
        
        if not current_order:
            return False
            
        with db.get_connection() as conn:
            try:
                # Update order status
                if status == 'ready_for_delivery':
                    # When order is ready for delivery, notify available riders
                    from app.models.rider_availability import RiderAvailability
                    from app.services.websocket_service import notify_available_riders
                    
                    # Get available riders
                    available_riders = RiderAvailability.get_available_riders()
                    
                    if available_riders:
                        # Notify available riders
                        notify_available_riders(order_id)
                    
                    # Update order status
                    db.execute_query(
                        "UPDATE orders SET status = %s, updated_at = NOW() WHERE id = %s",
                        (status, order_id)
                    )
                    
                    return True
                    
                elif status == 'assigned_to_rider' and rider_id:
                    # When a rider accepts the delivery
                    # Create delivery record
                    delivery_id = db.execute_query(
                        """
                        INSERT INTO deliveries (order_id, rider_id, status, assigned_at)
                        VALUES (%s, %s, 'assigned', NOW())
                        ON DUPLICATE KEY UPDATE
                            rider_id = VALUES(rider_id),
                            status = 'assigned',
                            assigned_at = NOW()
                        """,
                        (order_id, rider_id)
                    )
                    
                    if not delivery_id:
                        return False
                    
                    # Update rider availability
                    from app.models.rider_availability import RiderAvailability
                    RiderAvailability.set_availability(rider_id, False)
                    
                    # Update order with rider ID and status
                    db.execute_query(
                        "UPDATE orders SET rider_id = %s, status = 'assigned_to_rider', updated_at = NOW() WHERE id = %s",
                        (rider_id, order_id)
                    )
                    
                    # Notify the seller
                    seller_id = current_order['seller_id']
                    socketio.emit('rider_assigned', 
                                {'order_id': order_id, 'rider_id': rider_id},
                                room=f'seller_{seller_id}')
                    
                    return True
                
                else:
                    # For other status updates
                    result = db.execute_query(
                        "UPDATE orders SET status = %s, updated_at = NOW() WHERE id = %s",
                        (status, order_id),
                        commit=True  # Ensure the update is committed
                    )
                    
                    # If order is delivered, mark rider as available again
                    if status == 'delivered' and current_order.get('rider_id'):
                        from app.models.rider_availability import RiderAvailability
                        RiderAvailability.set_availability(current_order['rider_id'], True)
                    
                    # Log the status update for debugging
                    current_app.logger.info(f"Order {order_id} status updated to {status}")
                    return True if result is not None else False
                    
            except Exception as e:
                current_app.logger.error(f"Error updating order status: {e}")
                return False
    
    @classmethod
    def get_seller_id(cls, order_id):
        """Get seller ID for an order"""
        db = Database()
        result = db.execute_query(
            "SELECT seller_id FROM orders WHERE id = %s",
            (order_id,),
            fetch=True,
            fetchone=True
        )
        return result['seller_id'] if result else None
        
    @classmethod
    def get_order_status(cls, order_id):
        """Get current status of an order"""
        db = Database()
        result = db.execute_query(
            "SELECT status FROM orders WHERE id = %s",
            (order_id,),
            fetch=True,
            fetchone=True
        )
        return result['status'] if result else None
    
    @classmethod
    def list_for_seller(cls, seller_id, status=None, limit=None, offset=0):
        """List orders for a seller with optional status filter"""
        db = Database()
        query = """
            SELECT o.*, 
                   CONCAT(u.first_name, ' ', u.last_name) as customer_name, 
                   u.email as customer_email, 
                   u.phone as customer_phone,
                   CONCAT(r.first_name, ' ', r.last_name) as rider_name, 
                   r.phone as rider_phone,
                   COUNT(oi.id) as items_count,
                   d.status as delivery_status,
                   d.assigned_at,
                   d.picked_up_at,
                   d.delivered_at
            FROM orders o
            LEFT JOIN users u ON o.user_id = u.id
            LEFT JOIN deliveries d ON o.id = d.order_id
            LEFT JOIN users r ON d.rider_id = r.id
            LEFT JOIN order_items oi ON o.id = oi.order_id
            WHERE o.seller_id = %s
        """
        params = [seller_id]
        if status:
            query += " AND o.status = %s"
            params.append(status)
            
        query += " GROUP BY o.id, d.id ORDER BY o.created_at DESC"
        
        if limit is not None:
            query += " LIMIT %s OFFSET %s"
            params.extend([limit, offset])
            
        orders = db.execute_query(query, params, fetch=True)
        
        # Add items for each order
        for order in orders:
            items = db.execute_query(
                """
                SELECT oi.id, oi.order_id, oi.product_id, oi.quantity, oi.price_at_time,
                       p.name, p.image_url FROM order_items oi
                JOIN products p ON oi.product_id = p.id
                WHERE oi.order_id = %s
                """,
                (order['id'],),
                fetch=True,
            )
            order['items'] = items
        return orders

    @classmethod
    def update_status(cls, order_id, status):
        db = Database()
        db.execute_query("UPDATE orders SET status = %s WHERE id = %s", (status, order_id))
        return True

    @classmethod
    def update_payment_status(cls, order_id, payment_status):
        db = Database()
        db.execute_query("UPDATE orders SET payment_status = %s WHERE id = %s", (payment_status, order_id))
        return True

    @classmethod
    def count(cls, status=None):
        db = Database()
        query = "SELECT COUNT(*) as count FROM orders WHERE 1=1"
        params = []
        if status:
            query += " AND status = %s"
            params.append(status)
        res = db.execute_query(query, params, fetch=True, fetchone=True)
        return res['count'] if res else 0

