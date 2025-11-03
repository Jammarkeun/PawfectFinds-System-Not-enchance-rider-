"""WebSocket event handlers for real-time communication."""
from flask_socketio import emit, join_room, leave_room
from flask import current_app
from datetime import datetime, timedelta

class WebSocketHandlers:
    def __init__(self, socketio, active_riders, order_rooms):
        self.socketio = socketio
        self.active_riders = active_riders
        self.order_rooms = order_rooms

    def handle_connect(self):
        """Handle new WebSocket connection."""
        current_app.logger.debug(f'Client connected: {request.sid}')

    def handle_disconnect(self):
        """Handle WebSocket disconnection."""
        current_app.logger.debug(f'Client disconnected: {request.sid}')
        # Clean up any rider associations
        for rider_id, sockets in list(self.active_riders.items()):
            if request.sid in sockets:
                sockets.remove(request.sid)
                if not sockets:
                    del self.active_riders[rider_id]
                    # Notify all sellers that rider went offline
                    self.socketio.emit('rider_status', 
                                     {'rider_id': rider_id, 'is_online': False}, 
                                     broadcast=True)

    def handle_rider_online(self, data):
        """Handle rider coming online."""
        from app.models.rider_availability import RiderAvailability
        
        rider_id = data.get('rider_id')
        if not rider_id:
            return False
        
        # Add rider to active riders
        if rider_id not in self.active_riders:
            self.active_riders[rider_id] = []
        if request.sid not in self.active_riders[rider_id]:
            self.active_riders[rider_id].append(request.sid)
        
        # Join rider to their personal room and the general riders room
        join_room(f'rider_{rider_id}')
        join_room('riders_room')
        
        # Update rider's last online time
        RiderAvailability.update_last_online(rider_id)
        
        current_app.logger.info(f"Rider {rider_id} joined riders_room")
        
        # Notify all sellers that rider is online
        self.socketio.emit('rider_status', 
                         {'rider_id': rider_id, 'is_online': True}, 
                         broadcast=True)
        return True

    def notify_available_riders(self, order_id, order_details=None):
        """Notify all available riders about a new delivery opportunity."""
        from app.models.order import Order
        from app.models.rider_availability import RiderAvailability
        
        try:
            # Get order details if not provided
            if not order_details:
                order = Order.get_by_id(order_id)
                if not order:
                    current_app.logger.error(f'Order {order_id} not found')
                    return False
                
                order_details = {
                    'order_id': order_id,
                    'order_number': order.get('order_number', f'ORDER-{order_id}'),
                    'total_amount': float(order.get('total_amount', 0)),
                    'item_count': len(order.get('items', [])),
                    'created_at': order.get('created_at', datetime.utcnow()).strftime('%Y-%m-%d %H:%M'),
                    'delivery_address': order.get('shipping_address', {})
                }
            
            # Get all available riders
            available_riders = RiderAvailability.get_available_riders()
            if not available_riders:
                current_app.logger.info('No available riders to notify')
                return False
            
            # Create an order room for tracking acceptances
            self.order_rooms[order_id] = {
                'status': 'available',
                'expires_at': datetime.utcnow() + timedelta(minutes=5),  # 5 minutes to accept
                'riders_notified': [r['id'] for r in available_riders]
            }
            
            # Notify each available rider
            for rider in available_riders:
                self.socketio.emit('new_delivery_available', 
                                 {'order': order_details}, 
                                 room=f'rider_{rider["id"]}')
            
            current_app.logger.info(f'Notified {len(available_riders)} riders about order {order_id}')
            return True
            
        except Exception as e:
            current_app.logger.error(f'Error in notify_available_riders: {e}')
            return False

    def handle_accept_delivery(self, data):
        """Handle rider accepting a delivery."""
        from app.models.order import Order
        from app.models.delivery import Delivery
        from app.models.rider_availability import RiderAvailability
        
        try:
            order_id = data.get('order_id')
            rider_id = data.get('rider_id')
            
            if not order_id or not rider_id:
                current_app.logger.error('Missing order_id or rider_id in accept_delivery')
                return {'success': False, 'message': 'Missing required parameters'}
            
            # Check if rider is still available
            if not RiderAvailability.is_available(rider_id):
                return {
                    'success': False,
                    'message': 'You are no longer available for deliveries.'
                }
            
            # Check if order is still available
            if order_id not in self.order_rooms or self.order_rooms[order_id]['status'] != 'available':
                return {
                    'success': False,
                    'message': 'This delivery is no longer available.'
                }
            
            # Mark order as assigned
            self.order_rooms[order_id].update({
                'status': 'assigned',
                'rider_id': rider_id,
                'assigned_at': datetime.utcnow()
            })
            
            # Create delivery record
            delivery = Delivery.create(order_id, rider_id, 'Accepted via WebSocket')
            if not delivery:
                raise Exception('Failed to create delivery record')
            
            # Update order status
            Order.update_status(order_id, 'assigned_to_rider', rider_id=rider_id)
            
            # Notify all other riders that the order was taken
            self.socketio.emit('delivery_taken', 
                             {'order_id': order_id, 'rider_id': rider_id}, 
                             room='available_riders')
            
            # Notify the seller
            order = Order.get_by_id(order_id)
            if order and 'seller_id' in order:
                self.socketio.emit('delivery_assigned', 
                                 {'order_id': order_id, 
                                  'rider_id': rider_id,
                                  'order_number': order.get('order_number')}, 
                                 room=f'seller_{order["seller_id"]}')
            
            return {
                'success': True,
                'message': 'Delivery accepted successfully!',
                'delivery_id': delivery.get('id')
            }
            
        except Exception as e:
            current_app.logger.error(f'Error in handle_accept_delivery: {e}')
            return {
                'success': False,
                'message': 'An error occurred while accepting the delivery.'
            }

    def handle_location_update(self, data):
        """Update rider's current location."""
        from app.models.rider_availability import RiderAvailability
        
        try:
            rider_id = data.get('rider_id')
            latitude = data.get('latitude')
            longitude = data.get('longitude')
            
            if not all([rider_id, latitude, longitude]):
                current_app.logger.error('Missing required fields in location update')
                return False
            
            # Update rider's location
            updated = RiderAvailability.update_location(
                rider_id=rider_id,
                latitude=float(latitude),
                longitude=float(longitude)
            )
            
            if updated:
                # Broadcast location to all sellers tracking this rider
                self.socketio.emit('rider_location_update', {
                    'rider_id': rider_id,
                    'latitude': latitude,
                    'longitude': longitude,
                    'timestamp': datetime.utcnow().isoformat()
                }, room=f'tracking_{rider_id}')
                
            return updated
            
        except Exception as e:
            current_app.logger.error(f'Error in handle_location_update: {e}')
            return False

    def join_riders_room(self):
        """Join the general riders room."""
        join_room('available_riders')
        return True

    def leave_riders_room(self):
        """Leave the general riders room."""
        leave_room('available_riders')
        return True

    def join_seller_room(self, data):
        """Join a seller's specific room."""
        seller_id = data.get('seller_id')
        if seller_id:
            join_room(f'seller_{seller_id}')
            return True
        return False

    def leave_seller_room(self, data):
        """Leave a seller's specific room."""
        seller_id = data.get('seller_id')
        if seller_id:
            leave_room(f'seller_{seller_id}')
            return True
        return False
