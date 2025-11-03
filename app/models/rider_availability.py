from app.services.database import Database
from datetime import datetime, timedelta

class RiderAvailability:
    @staticmethod
    def get_available_riders(max_distance_km=20, min_online_minutes_ago=10):
        """Get list of all online riders (all riders are considered available)"""
        db = Database()
        time_threshold = datetime.utcnow() - timedelta(minutes=min_online_minutes_ago)
        
        return db.execute_query(
            """
            SELECT u.*, ra.current_lat, ra.current_lng, ra.max_distance
            FROM rider_availability ra
            JOIN users u ON ra.rider_id = u.id
            WHERE ra.is_online = 1 
            AND ra.last_online >= %s
            AND u.role = 'rider'
            """,
            (time_threshold,),
            fetch=True
        )
    
    @staticmethod
    def set_availability(rider_id, is_available=True, lat=None, lng=None):
        """Update rider's location (riders are always available)"""
        db = Database()
        
        query = """
        INSERT INTO rider_availability (rider_id, is_online, is_available, current_lat, current_lng, last_online)
        VALUES (%s, 1, 1, %s, %s, NOW())
        ON DUPLICATE KEY UPDATE
            is_online = 1,
            is_available = 1,
            current_lat = COALESCE(VALUES(current_lat), current_lat),
            current_lng = COALESCE(VALUES(current_lng), current_lng),
            last_online = NOW()
        """
        
        return db.execute_query(query, (rider_id, lat, lng))
    
    @staticmethod
    def update_location(rider_id, lat, lng):
        """Update rider's current location"""
        db = Database()
        
        query = """
        INSERT INTO rider_availability (rider_id, current_lat, current_lng, last_online)
        VALUES (%s, %s, %s, NOW())
        ON DUPLICATE KEY UPDATE
            current_lat = VALUES(current_lat),
            current_lng = VALUES(current_lng),
            last_online = NOW()
        """
        
        return db.execute_query(query, (rider_id, lat, lng))
        
    @staticmethod
    def get_by_rider_id(rider_id):
        """Get rider availability by rider ID"""
        db = Database()
        return db.execute_query(
            """
            SELECT ra.*, u.first_name, u.last_name, u.phone
            FROM rider_availability ra
            JOIN users u ON ra.rider_id = u.id
            WHERE ra.rider_id = %s
            """,
            (rider_id,),
            fetch=True,
            fetchone=True
        )
