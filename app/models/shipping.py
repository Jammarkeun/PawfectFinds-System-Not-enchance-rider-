from app import db

class ShippingProvider(db.Model):
    """Shipping provider model for different courier services"""
    __tablename__ = 'shipping_providers'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    base_fee = db.Column(db.Numeric(10, 2), nullable=False)
    fee_per_km = db.Column(db.Numeric(10, 2), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.TIMESTAMP, server_default=db.func.current_timestamp(), nullable=False)
    updated_at = db.Column(db.TIMESTAMP, server_default=db.func.current_timestamp(), 
                          onupdate=db.func.current_timestamp(), nullable=False)
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'base_fee': float(self.base_fee) if self.base_fee else 0.0,
            'fee_per_km': float(self.fee_per_km) if self.fee_per_km else 0.0,
            'is_active': self.is_active
        }

class ShippingCalculator:
    """Helper class to calculate shipping fees"""
    
    @staticmethod
    def calculate_fee(distance_km, provider_id=None):
        """Calculate shipping fee based on distance and provider"""
        if provider_id:
            provider = ShippingProvider.query.get(provider_id)
            if not provider or not provider.is_active:
                return None
            base_fee = float(provider.base_fee)
            per_km = float(provider.fee_per_km)
        else:
            # Default values if no provider specified
            base_fee = 50.00
            per_km = 5.00
            
        # Calculate total fee with minimum of 1km
        distance = max(1, distance_km)
        total_fee = base_fee + (distance * per_km)
        
        return round(total_fee, 2)
