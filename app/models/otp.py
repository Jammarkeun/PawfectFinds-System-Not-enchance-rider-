import random
import string
from datetime import datetime, timedelta
from app.services.database import Database

class OTP:
    """OTP model for handling one-time passwords"""
    
    def __init__(self):
        self.db = Database()
        self.otp_length = 6
        self.otp_expiry_minutes = 10
    
    def generate_otp(self, email):
        """Generate and store a new OTP for the given email"""
        # Generate a random 6-digit OTP
        otp_code = ''.join(random.choices(string.digits, k=self.otp_length))
        
        # Set expiry time
        created_at = datetime.utcnow()
        expires_at = created_at + timedelta(minutes=self.otp_expiry_minutes)
        
        # Store in database
        query = """
            INSERT INTO otp_codes (email, otp_code, created_at, expires_at, is_used)
            VALUES (%s, %s, %s, %s, FALSE)
            RETURNING id
        """
        
        try:
            self.db.execute_query(
                """
                DELETE FROM otp_codes 
                WHERE email = %s OR expires_at < NOW()
                """, 
                (email,)
            )
            
            result = self.db.execute_query(
                query, 
                (email, otp_code, created_at, expires_at),
                fetch=True,
                fetchone=True
            )
            
            if result:
                return otp_code
            return None
            
        except Exception as e:
            print(f"Error generating OTP: {str(e)}")
            return None
    
    def verify_otp(self, email, otp_code):
        """Verify if the provided OTP is valid for the given email"""
        query = """
            SELECT id FROM otp_codes 
            WHERE email = %s 
            AND otp_code = %s 
            AND is_used = FALSE 
            AND expires_at > NOW()
            LIMIT 1
        """
        
        try:
            result = self.db.execute_query(
                query, 
                (email, otp_code),
                fetch=True,
                fetchone=True
            )
            
            if result:
                # Mark OTP as used
                self.db.execute_query(
                    "UPDATE otp_codes SET is_used = TRUE WHERE id = %s",
                    (result[0],)
                )
                return True
            return False
            
        except Exception as e:
            print(f"Error verifying OTP: {str(e)}")
            return False
