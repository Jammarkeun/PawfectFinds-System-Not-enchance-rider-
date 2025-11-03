from app.services.database import Database
# Import moved to function level to avoid circular imports

class Cart:
    """Cart model to manage user's cart items"""

    @classmethod
    def add_item(cls, user_id, product_id, quantity=1):
        db = Database()
        # Upsert: if exists, update quantity
        existing = cls.get_item(user_id, product_id)
        if existing:
            new_qty = existing['quantity'] + quantity
            query = "UPDATE cart SET quantity = %s WHERE id = %s"
            db.execute_query(query, (new_qty, existing['id']))
            return True
        query = "INSERT INTO cart (user_id, product_id, quantity) VALUES (%s, %s, %s)"
        db.execute_query(query, (user_id, product_id, quantity))
        return True

    @classmethod
    def update_item(cls, cart_id, quantity):
        db = Database()
        if quantity <= 0:
            return cls.remove_item_by_id(cart_id)
        query = "UPDATE cart SET quantity = %s WHERE id = %s"
        db.execute_query(query, (quantity, cart_id))
        return True

    @classmethod
    def remove_item(cls, user_id, product_id):
        db = Database()
        query = "DELETE FROM cart WHERE user_id = %s AND product_id = %s"
        db.execute_query(query, (user_id, product_id))
        return True

    @classmethod
    def remove_item_by_id(cls, cart_id):
        db = Database()
        query = "DELETE FROM cart WHERE id = %s"
        db.execute_query(query, (cart_id,))
        return True

    @classmethod
    def clear_cart(cls, user_id):
        db = Database()
        query = "DELETE FROM cart WHERE user_id = %s"
        db.execute_query(query, (user_id,))
        return True

    @classmethod
    def get_item(cls, user_id, product_id):
        db = Database()
        query = "SELECT * FROM cart WHERE user_id = %s AND product_id = %s"
        result = db.execute_query(query, (user_id, product_id), fetch=True)
        
        if not result:
            return None
            
        # Handle case where execute_query returns a list
        if isinstance(result, list):
            if not result:
                return None
            # If it's a list of rows, take the first one
            row = result[0]
            if isinstance(row, dict):
                return row
            # If it's a tuple, convert to dict with column names
            columns = ['id', 'user_id', 'product_id', 'quantity', 'added_at']
            return dict(zip(columns, row))
            
        # If it's a cursor-like object with fetchone
        if hasattr(result, 'fetchone'):
            row = result.fetchone()
            if not row:
                return None
            return dict(zip([column[0] for column in result.description], row))
            
        return None

    @classmethod
    def get_user_cart(cls, user_id):
        """Get all cart items for a user with product and seller details"""
        db = Database()
        query = """
            SELECT 
                c.id, 
                c.quantity, 
                p.id as product_id, 
                p.name, 
                p.price, 
                p.image_url, 
                p.stock_quantity, 
                p.seller_id, 
                u.username as seller_username,
                u.latitude as seller_latitude,
                u.longitude as seller_longitude
            FROM cart c
            JOIN products p ON c.product_id = p.id
            JOIN users u ON p.seller_id = u.id
            WHERE c.user_id = %s
            ORDER BY c.added_at DESC
        """
        # Handle case where execute_query returns a list directly
        result = db.execute_query(query, (user_id,), fetch=True)
        
        if not result:
            return []
            
        # If result is a list of rows, convert to list of dicts
        if isinstance(result, list):
            # If it's a list of tuples, convert to list of dicts
            if result and isinstance(result[0], tuple):
                columns = [
                    'id', 'quantity', 'product_id', 'name', 'price', 
                    'image_url', 'stock_quantity', 'seller_id', 'seller_username',
                    'seller_latitude', 'seller_longitude'
                ]
                return [
                    {
                        **dict(zip(columns, row)),
                        'seller_location': (
                            (float(row[9]), float(row[10])) 
                            if row[9] is not None and row[10] is not None 
                            else None
                        )
                    }
                    for row in result
                ]
            # If it's already a list of dicts, just add seller_location
            elif result and isinstance(result[0], dict):
                for item in result:
                    if item.get('seller_latitude') is not None and item.get('seller_longitude') is not None:
                        item['seller_location'] = (
                            float(item['seller_latitude']), 
                            float(item['seller_longitude'])
                        )
                    else:
                        item['seller_location'] = None
                return result
        
        return []

    @classmethod
    def get_total(cls, user_id):
        """
        Get the total cart amount (for backward compatibility)
        
        Args:
            user_id: ID of the user
            
        Returns:
            float: Total cart amount including shipping fees
        """
        cart_total = cls.get_cart_total(user_id)
        return cart_total['total']
        
    @classmethod
    def get_cart_total(cls, user_id, include_shipping=True):
        """
        Calculate total amount of items in cart with optional shipping fees
        
        Args:
            user_id: ID of the user
            include_shipping: Whether to include shipping fees in the total
            
        Returns:
            dict: {
                'subtotal': float,  # Sum of all items
                'shipping_fees': {seller_id: float},  # Shipping fee per seller
                'total': float  # Subtotal + sum of all shipping fees
            }
        """
        # Import here to avoid circular import
        from app.models.order import Order
        
        items = cls.get_user_cart(user_id)
        if not items:
            return {
                'subtotal': 0.0,
                'shipping_fees': {},
                'total': 0.0
            }
            
        subtotal = sum(float(item.get('price', 0)) * item.get('quantity', 0) for item in items)
        
        if not include_shipping:
            return {
                'subtotal': subtotal,
                'shipping_fees': {},
                'total': subtotal
            }
        
        # Group items by seller and calculate shipping per seller
        seller_items = {}
        for item in items:
            seller_id = item['seller_id']
            if seller_id not in seller_items:
                seller_items[seller_id] = {
                    'items': [],
                    'seller_location': item.get('seller_location')
                }
            seller_items[seller_id]['items'].append(item)
        
        # Calculate shipping fee for each seller
        shipping_fees = {}
        user_location = (14.5995, 120.9842)  # Default to Manila coordinates
        
        for seller_id, data in seller_items.items():
            if data['seller_location']:  # Only calculate if seller location is available
                shipping_fee = Order.calculate_shipping_fee(
                    user_location,
                    data['seller_location']
                )
                shipping_fees[seller_id] = shipping_fee
        
        total = subtotal + sum(shipping_fees.values())
        
        return {
            'subtotal': subtotal,
            'shipping_fees': shipping_fees,
            'total': total
        }
