from app.services.database import Database
from datetime import datetime
from flask import current_app

class Delivery:
    @staticmethod
    def create(order_id, rider_id, delivery_notes=None):
        """Create a new delivery assignment"""
        db = Database()
        try:
            # Insert delivery with initial status and timestamp
            delivery_id = db.execute_query(
                """
                INSERT INTO deliveries (order_id, rider_id, status, delivery_notes, assigned_at)
                VALUES (%s, %s, 'assigned', %s, NOW())
                ON DUPLICATE KEY UPDATE
                    rider_id = VALUES(rider_id),
                    status = 'assigned',
                    delivery_notes = COALESCE(VALUES(delivery_notes), delivery_notes),
                    assigned_at = NOW()
                """,
                (order_id, rider_id, delivery_notes)
            )
            
            if not delivery_id:
                return False
                
            # Update order with rider_id and status
            db.execute_query(
                """
                UPDATE orders
                SET rider_id = %s, status = 'assigned_to_rider', updated_at = NOW()
                WHERE id = %s
                """,
                (rider_id, order_id)
            )
            
            # Update rider availability
            from app.models.rider_availability import RiderAvailability
            RiderAvailability.set_availability(rider_id, False)
            
            return delivery_id
            
        except Exception as e:
            current_app.logger.error(f"Error creating delivery: {e}")
            return False

    @staticmethod
    def get_by_id(delivery_id):
        """Get delivery by ID"""
        db = Database()
        result = db.execute_query(
            "SELECT * FROM deliveries WHERE id = %s",
            (delivery_id,),
            fetch=True,
            fetchone=True
        )
        if result:
            # Add order and rider details
            order = db.execute_query(
                "SELECT * FROM orders WHERE id = %s",
                (result['order_id'],),
                fetch=True,
                fetchone=True
            )
            if order:
                # Get order items
                items = db.execute_query(
                    "SELECT oi.*, p.name, p.image_url FROM order_items oi JOIN products p ON oi.product_id = p.id WHERE oi.order_id = %s",
                    (order['id'],),
                    fetch=True
                )
                order['items'] = items

                # Get customer details
                customer = db.execute_query(
                    "SELECT first_name, last_name, phone FROM users WHERE id = %s",
                    (order['user_id'],),
                    fetch=True,
                    fetchone=True
                )
                if customer:
                    result['customer_name'] = f"{customer['first_name']} {customer['last_name']}"
                    result['customer_phone'] = customer['phone'] or ''
                else:
                    result['customer_name'] = 'Unknown'
                    result['customer_phone'] = ''

                result['order'] = order

            rider = db.execute_query(
                "SELECT id, first_name, last_name, phone FROM users WHERE id = %s",
                (result['rider_id'],),
                fetch=True,
                fetchone=True
            )
            if rider:
                result['rider'] = rider
        return result

    @staticmethod
    def get_current_delivery(rider_id):
        """Get rider's current active delivery"""
        db = Database()
        return db.execute_query(
            """
            SELECT d.*, o.*, 
                   u.first_name as customer_first_name, 
                   u.last_name as customer_last_name,
                   u.phone as customer_phone,
                   u.email as customer_email,
                   s.business_name as seller_name,
                   s.business_address as seller_address
            FROM deliveries d
            JOIN orders o ON d.order_id = o.id
            JOIN users u ON o.user_id = u.id
            LEFT JOIN seller_requests s ON o.seller_id = s.user_id
            WHERE d.rider_id = %s 
            AND d.status IN ('assigned', 'picked_up', 'on_the_way')
            ORDER BY d.assigned_at DESC
            LIMIT 1
            """,
            (rider_id,),
            fetch=True,
            fetchone=True
        )
        
    @staticmethod
    def get_by_order_id(order_id):
        """Get delivery by order ID to check if assigned"""
        db = Database()
        return db.execute_query(
            """
            SELECT d.*, 
                   u.first_name as rider_first_name, 
                   u.last_name as rider_last_name,
                   u.phone as rider_phone
            FROM deliveries d
            LEFT JOIN users u ON d.rider_id = u.id
            WHERE d.order_id = %s
            """,
            (order_id,),
            fetch=True,
            fetchone=True
        )

    @staticmethod
    def update_status(delivery_id, status, notes=None, rider_id=None):
        """Update delivery status"""
        db = Database()
        try:
            status = status.lower()
            
            # Get current delivery
            delivery = db.execute_query(
                "SELECT * FROM deliveries WHERE id = %s",
                (delivery_id,),
                fetch=True,
                fetchone=True
            )
            
            if not delivery:
                return False
                
            # Update status with appropriate timestamp
            update_fields = ["status = %s"]
            params = [status]
            
            if status == 'picked_up':
                update_fields.append("picked_up_at = NOW()")
            elif status == 'on_the_way':
                update_fields.append("shipped_at = NOW()")
            elif status == 'delivered':
                update_fields.append("delivered_at = NOW()")
                
                # Update order status to delivered
                db.execute_query(
                    "UPDATE orders SET status = 'delivered', updated_at = NOW() WHERE id = %s",
                    (delivery['order_id'],)
                )
                
                # Mark rider as available again
                from app.models.rider_availability import RiderAvailability
                RiderAvailability.set_availability(delivery['rider_id'], True)
            
            if notes:
                update_fields.append("delivery_notes = %s")
                params.append(notes)
                
            params.append(delivery_id)
            
            query = f"UPDATE deliveries SET {', '.join(update_fields)} WHERE id = %s"
            
            success = db.execute_query(query, params)
            
            # Notify customer if status is updated
            if success and status in ['picked_up', 'on_the_way', 'delivered']:
                from app.services.websocket_service import socketio
                socketio.emit('delivery_status_update', {
                    'delivery_id': delivery_id,
                    'status': status,
                    'updated_at': datetime.utcnow().isoformat()
                }, room=f"customer_{delivery['order']['user_id']}" if 'order' in delivery and 'user_id' in delivery['order'] else None)
            
            return success
            
        except Exception as e:
            current_app.logger.error(f"Error updating delivery status: {e}")
            return False
    
    @staticmethod
    def list_for_rider(rider_id, status=None, limit=None, offset=0):
        """List deliveries for a rider with optional status filter"""
        db = Database()
        query = """
            SELECT d.*, 
                   o.id as order_id, o.status as order_status,
                   o.total_amount, 
                   o.shipping_address,
                   o.created_at as order_created_at,
                   CONCAT(u.first_name, ' ', u.last_name) as customer_name,
                   u.phone as customer_phone,
                   s.business_name as seller_name,
                   s.business_address as seller_address,
                   o.payment_method, 
                   o.notes as order_notes
            FROM deliveries d
            JOIN orders o ON d.order_id = o.id
            JOIN users u ON o.user_id = u.id
            LEFT JOIN seller_requests s ON o.seller_id = s.user_id
            WHERE d.rider_id = %s
        """
        params = [rider_id]
        
        if status:
            if isinstance(status, list):
                placeholders = ', '.join(['%s'] * len(status))
                query += f" AND d.status IN ({placeholders})"
                params.extend(status)
            else:
                query += " AND d.status = %s"
                params.append(status)
                
        query += " ORDER BY d.assigned_at DESC"
        
        if limit is not None:
            query += " LIMIT %s"
            params.append(limit)
            if offset:
                query += " OFFSET %s"
                params.append(offset)
                
        # Execute the query
        results = db.execute_query(query, params, fetch=True)
        
        # Process results to ensure consistent data structure
        if not results:
            return []
            
        return [dict(row) for row in results]

    @staticmethod
    def update_status(delivery_id, status, notes=None):
        """Update delivery status (picked_up, on_the_way, delivered, failed)"""
        db = Database()
        try:
            # Update delivery with status and optional notes/timestamp
            timestamp_field = None
            if status == 'picked_up':
                timestamp_field = 'picked_up_at = CURRENT_TIMESTAMP'
            elif status == 'on_the_way':
                timestamp_field = 'on_the_way_at = CURRENT_TIMESTAMP'
            elif status == 'delivered':
                timestamp_field = 'delivered_at = CURRENT_TIMESTAMP'

            if notes:
                if timestamp_field:
                    db.execute_query(
                        f"""
                        UPDATE deliveries
                        SET status = %s, delivery_notes = %s, {timestamp_field}
                        WHERE id = %s
                        """,
                        (status, notes, delivery_id)
                    )
                else:
                    db.execute_query(
                        """
                        UPDATE deliveries
                        SET status = %s, delivery_notes = %s
                        WHERE id = %s
                        """,
                        (status, notes, delivery_id)
                    )
            else:
                if timestamp_field:
                    db.execute_query(
                        f"""
                        UPDATE deliveries
                        SET status = %s, {timestamp_field}
                        WHERE id = %s
                        """,
                        (status, delivery_id)
                    )
                else:
                    db.execute_query(
                        """
                        UPDATE deliveries
                        SET status = %s
                        WHERE id = %s
                        """,
                        (status, delivery_id)
                    )

            # Update order status accordingly
            delivery = db.execute_query(
                "SELECT order_id FROM deliveries WHERE id = %s",
                (delivery_id,),
                fetch=True,
                fetchone=True
            )
            if delivery:
                order_id = delivery['order_id']
                order_status_map = {
                    'picked_up': 'picked_up',
                    'on_the_way': 'on_the_way',
                    'delivered': 'delivered',
                    'failed': 'cancelled'
                }
                new_order_status = order_status_map.get(status, 'shipped')

                # Set order timestamp if applicable
                order_timestamp_field = None
                if status == 'picked_up':
                    order_timestamp_field = 'picked_up_at = CURRENT_TIMESTAMP'
                elif status == 'delivered':
                    order_timestamp_field = 'delivered_at = CURRENT_TIMESTAMP'

                if order_timestamp_field:
                    db.execute_query(
                        f"""
                        UPDATE orders
                        SET status = %s, {order_timestamp_field}
                        WHERE id = %s
                        """,
                        (new_order_status, order_id)
                    )
                else:
                    db.execute_query(
                        """
                        UPDATE orders
                        SET status = %s
                        WHERE id = %s
                        """,
                        (new_order_status, order_id)
                    )

            return True
        except Exception as e:
            print(f"Error updating delivery status: {e}")
            return False

    @staticmethod
    def assign_rider(order_id, rider_id, delivery_notes=None):
        """Assign or change rider for an order"""
        db = Database()
        try:
            # Check if delivery exists
            existing = db.execute_query("SELECT id FROM deliveries WHERE order_id = %s", (order_id,), fetch=True, fetchone=True)
            if existing:
                # Update existing delivery
                db.execute_query(
                    "UPDATE deliveries SET rider_id = %s, delivery_notes = %s WHERE order_id = %s",
                    (rider_id, delivery_notes, order_id)
                )
            else:
                # Create new delivery
                db.execute_query(
                    """
                    INSERT INTO deliveries (order_id, rider_id, status, delivery_notes, assigned_at)
                    VALUES (%s, %s, 'assigned', %s, CURRENT_TIMESTAMP)
                    """,
                    (order_id, rider_id, delivery_notes)
                )

            # Update order with rider_id, set status to shipped if not already shipped or later
            db.execute_query(
                """
                UPDATE orders
                SET rider_id = %s, status = CASE WHEN status NOT IN ('shipped', 'on_the_way', 'delivered') THEN 'shipped' ELSE status END
                WHERE id = %s
                """,
                (rider_id, order_id)
            )
            return True
        except Exception as e:
            print(f"Error assigning rider: {e}")
            return False

    @staticmethod
    def get_all_riders_with_availability():
        """Get all active riders with availability status"""
        db = Database()
        return db.execute_query(
            """
            SELECT u.id, u.first_name, u.last_name, u.phone,
                   COUNT(d.id) as current_deliveries
            FROM users u
            LEFT JOIN deliveries d ON u.id = d.rider_id AND d.status != 'delivered'
            WHERE u.role = 'rider' AND u.status = 'active'
            GROUP BY u.id, u.first_name, u.last_name, u.phone
            ORDER BY current_deliveries ASC
            """,
            fetch=True
        )
