from app.services.database import Database

class Product:
    """Product model for product operations"""
    
    @classmethod
    def create(cls, seller_id, category_id, name, description, price, stock_quantity, image_url=None):
        db = Database()
        query = '''
            INSERT INTO products (seller_id, category_id, name, description, price, stock_quantity, image_url)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        '''
        product_id = db.execute_query(query, (seller_id, category_id, name, description, price, stock_quantity, image_url))
        return cls.get_by_id(product_id)
    
    @classmethod
    def get_by_id(cls, product_id):
        db = Database()
        query = '''
            SELECT p.*, c.name as category_name, u.username as seller_username
            FROM products p
            JOIN categories c ON p.category_id = c.id
            JOIN users u ON p.seller_id = u.id
            WHERE p.id = %s
        '''
        return db.execute_query(query, (product_id,), fetch=True, fetchone=True)
    
    @classmethod
    def update(cls, product_id, **kwargs):
        db = Database()
        allowed = ['category_id', 'name', 'description', 'price', 'stock_quantity', 'image_url', 'status']
        fields = []
        values = []
        for k, v in kwargs.items():
            if k in allowed:
                fields.append(f"{k}=%s")
                values.append(v)
        if not fields:
            return False
        values.append(product_id)
        query = f"UPDATE products SET {', '.join(fields)} WHERE id = %s"
        db.execute_query(query, values)
        return True
    
    @classmethod
    def delete(cls, product_id):
        db = Database()
        query = "DELETE FROM products WHERE id = %s"
        db.execute_query(query, (product_id,))
        return True
    
    @classmethod
    def list(cls, category_id=None, search=None, seller_id=None, status='active', limit=None, offset=0):
        db = Database()
        query = '''
            SELECT p.*, c.name as category_name, u.username as seller_username
            FROM products p
            JOIN categories c ON p.category_id = c.id
            JOIN users u ON p.seller_id = u.id
            WHERE 1=1
        '''
        params = []
        if status:
            query += " AND p.status = %s"
            params.append(status)
        if category_id:
            query += " AND p.category_id = %s"
            params.append(category_id)
        if seller_id:
            query += " AND p.seller_id = %s"
            params.append(seller_id)
        if search:
            query += " AND (p.name LIKE %s OR p.description LIKE %s)"
            like = f"%{search}%"
            params.extend([like, like])
        query += " ORDER BY p.created_at DESC"
        if limit:
            query += " LIMIT %s OFFSET %s"
            params.extend([limit, offset])
        return db.execute_query(query, params, fetch=True)
    
    @classmethod
    def count(cls, category_id=None, search=None, seller_id=None, status='active'):
        db = Database()
        query = "SELECT COUNT(*) as count FROM products p WHERE 1=1"
        params = []
        if status:
            query += " AND p.status = %s"
            params.append(status)
        if category_id:
            query += " AND p.category_id = %s"
            params.append(category_id)
        if seller_id:
            query += " AND p.seller_id = %s"
            params.append(seller_id)
        if search:
            query += " AND (p.name LIKE %s OR p.description LIKE %s)"
            like = f"%{search}%"
            params.extend([like, like])
        result = db.execute_query(query, params, fetch=True, fetchone=True)
        return result['count'] if result else 0

