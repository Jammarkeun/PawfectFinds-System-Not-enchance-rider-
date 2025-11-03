from app.services.database import Database
from datetime import datetime

class SellerRequest:
    """Seller request model for handling seller applications"""
    
    def __init__(self):
        self.db = Database()
    
    @classmethod
    def create(cls, user_id, business_name, business_description, business_address, business_phone, tax_id=None, business_permit=None):
        """Create a new seller request"""
        db = Database()

        # Check if user already has a pending request
        existing = cls.get_by_user_id(user_id)
        if existing and existing['status'] == 'pending':
            return None  # User already has a pending request

        query = '''
            INSERT INTO seller_requests (user_id, business_name, business_description, business_address, business_phone, tax_id, business_permit)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        '''

        request_id = db.execute_query(query, (user_id, business_name, business_description, business_address, business_phone, tax_id, business_permit))
        return cls.get_by_id(request_id)
    
    @classmethod
    def get_by_id(cls, request_id):
        """Get seller request by ID"""
        db = Database()
        query = '''
            SELECT sr.*, u.username, u.email, u.first_name, u.last_name
            FROM seller_requests sr
            JOIN users u ON sr.user_id = u.id
            WHERE sr.id = %s
        '''
        return db.execute_query(query, (request_id,), fetch=True, fetchone=True)
    
    @classmethod
    def get_by_user_id(cls, user_id):
        """Get seller request by user ID"""
        db = Database()
        query = "SELECT * FROM seller_requests WHERE user_id = %s ORDER BY requested_at DESC LIMIT 1"
        return db.execute_query(query, (user_id,), fetch=True, fetchone=True)
    
    @classmethod
    def get_all_requests(cls, status=None, limit=None, offset=0):
        """Get all seller requests with optional filters"""
        db = Database()
        
        query = '''
            SELECT sr.*, u.username, u.email, u.first_name, u.last_name
            FROM seller_requests sr
            JOIN users u ON sr.user_id = u.id
            WHERE 1=1
        '''
        params = []
        
        if status:
            query += " AND sr.status = %s"
            params.append(status)
        
        query += " ORDER BY sr.requested_at DESC"
        
        if limit:
            query += " LIMIT %s OFFSET %s"
            params.extend([limit, offset])
        
        return db.execute_query(query, params, fetch=True)
    
    @classmethod
    def get_pending_requests(cls):
        """Get all pending seller requests"""
        return cls.get_all_requests(status='pending')
    
    @classmethod
    def approve_request(cls, request_id, admin_notes=None):
        """Approve a seller request"""
        db = Database()
        
        # Get the request details
        request = cls.get_by_id(request_id)
        if not request or request['status'] != 'pending':
            return False
        
        # Update the request status
        query = '''
            UPDATE seller_requests 
            SET status = 'approved', admin_notes = %s, reviewed_at = NOW()
            WHERE id = %s
        '''
        db.execute_query(query, (admin_notes, request_id))
        
        # Update the user role to seller
        from app.models.user import User
        User.update_role(request['user_id'], 'seller')
        
        return True
    
    @classmethod
    def reject_request(cls, request_id, admin_notes=None):
        """Reject a seller request"""
        db = Database()
        
        query = '''
            UPDATE seller_requests 
            SET status = 'rejected', admin_notes = %s, reviewed_at = NOW()
            WHERE id = %s
        '''
        db.execute_query(query, (admin_notes, request_id))
        return True
    
    @classmethod
    def get_requests_count(cls, status=None):
        """Get count of seller requests with optional filter"""
        db = Database()
        
        query = "SELECT COUNT(*) as count FROM seller_requests WHERE 1=1"
        params = []
        
        if status:
            query += " AND status = %s"
            params.append(status)
        
        result = db.execute_query(query, params, fetch=True, fetchone=True)
        return result['count'] if result else 0
    
    @classmethod
    def delete(cls, request_id):
        """Delete a seller request"""
        db = Database()
        query = "DELETE FROM seller_requests WHERE id = %s"
        db.execute_query(query, (request_id,))
        return True
