from app.services.database import Database
from werkzeug.security import generate_password_hash, check_password_hash

class User:
    """User model for handling user operations"""
    
    def __init__(self):
        self.db = Database()
    
    @classmethod
    def create(cls, username, email, password, first_name, last_name, phone=None, address=None, country=None, city=None, id_picture=None, profile_image=None, role='user'):
        """Create a new user"""
        db = Database()

        # Check if user already exists
        if cls.get_by_email(email) or cls.get_by_username(username):
            return None

        password_hash = generate_password_hash(password)

        query = '''
            INSERT INTO users (username, email, password_hash, first_name, last_name, phone, address, country, city, id_picture, profile_image, role)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        '''

        user_id = db.execute_query(query, (username, email, password_hash, first_name, last_name, phone, address, country, city, id_picture, profile_image, role))
        return cls.get_by_id(user_id)
    
    @classmethod
    def get_by_id(cls, user_id):
        """Get user by ID"""
        db = Database()
        query = "SELECT * FROM users WHERE id = %s"
        return db.execute_query(query, (user_id,), fetch=True, fetchone=True)
    
    @classmethod
    def get_by_email(cls, email):
        """Get user by email"""
        db = Database()
        query = "SELECT * FROM users WHERE email = %s"
        return db.execute_query(query, (email,), fetch=True, fetchone=True)
    
    @classmethod
    def get_by_username(cls, username):
        """Get user by username"""
        db = Database()
        query = "SELECT * FROM users WHERE username = %s"
        return db.execute_query(query, (username,), fetch=True, fetchone=True)
    
    @classmethod
    def authenticate(cls, email, password):
        """Authenticate user by email and password"""
        user = cls.get_by_email(email)
        if user and check_password_hash(user['password_hash'], password):
            return user
        return None
    
    @classmethod
    def update(cls, user_id, **kwargs):
        """Update user information"""
        db = Database()

        # Build dynamic update query
        allowed_fields = ['username', 'email', 'first_name', 'last_name', 'phone', 'address', 'profile_image']
        update_fields = []
        values = []

        for field, value in kwargs.items():
            if field in allowed_fields:
                update_fields.append(f"{field} = %s")
                values.append(value)

        if not update_fields:
            return False

        values.append(user_id)
        query = f"UPDATE users SET {', '.join(update_fields)} WHERE id = %s"

        db.execute_query(query, values)
        return True
    
    @classmethod
    def update_password(cls, user_id, new_password):
        """Update user password"""
        db = Database()
        password_hash = generate_password_hash(new_password)
        query = "UPDATE users SET password_hash = %s WHERE id = %s"
        db.execute_query(query, (password_hash, user_id))
        return True
    
    @classmethod
    def update_role(cls, user_id, new_role):
        """Update user role (admin function)"""
        db = Database()
        query = "UPDATE users SET role = %s WHERE id = %s"
        db.execute_query(query, (new_role, user_id))
        return True
    
    @classmethod
    def update_status(cls, user_id, status):
        """Update user status (admin function)"""
        db = Database()
        query = "UPDATE users SET status = %s WHERE id = %s"
        db.execute_query(query, (status, user_id))
        return True
    
    @classmethod
    def get_all_users(cls, role=None, status=None, limit=None, offset=0):
        """Get all users with optional filters"""
        db = Database()
        
        query = "SELECT * FROM users WHERE 1=1"
        params = []
        
        if role:
            query += " AND role = %s"
            params.append(role)
        
        if status:
            query += " AND status = %s"
            params.append(status)
        
        query += " ORDER BY created_at DESC"
        
        if limit:
            query += " LIMIT %s OFFSET %s"
            params.extend([limit, offset])
        
        return db.execute_query(query, params, fetch=True)
    
    @classmethod
    def get_users_count(cls, role=None, status=None):
        """Get count of users with optional filters"""
        db = Database()
        
        query = "SELECT COUNT(*) as count FROM users WHERE 1=1"
        params = []
        
        if role:
            query += " AND role = %s"
            params.append(role)
        
        if status:
            query += " AND status = %s"
            params.append(status)
        
        result = db.execute_query(query, params, fetch=True, fetchone=True)
        return result['count'] if result else 0
    
    @classmethod
    def delete(cls, user_id):
        """Delete a user (admin function)"""
        db = Database()
        query = "DELETE FROM users WHERE id = %s"
        db.execute_query(query, (user_id,))
        return True
    
    @classmethod
    def get_sellers(cls):
        """Get all sellers"""
        return cls.get_all_users(role='seller', status='active')
    
    @classmethod
    def get_customers(cls):
        """Get all customers"""
        return cls.get_all_users(role='user', status='active')
