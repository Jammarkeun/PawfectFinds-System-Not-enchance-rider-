from flask import request as flask_request, current_app, jsonify
from flask_socketio import SocketIO, emit, join_room, leave_room, disconnect
from app import db
from app.models.models import RiderAvailability, Order, Notification
from app.models.delivery import Delivery
from datetime import datetime, timedelta
import json
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize SocketIO without app (will be initialized with app later)
socketio = SocketIO(
    cors_allowed_origins="*",
    async_mode='eventlet',
    logger=True,
    engineio_logger=True,
    ping_timeout=60,
    ping_interval=25
)

# Store active rider connections
active_riders = {}

def init_rider_websocket(app):
    """Initialize WebSocket with the Flask app"""
    socketio.init_app(
        app,
        cors_allowed_origins="*",
        async_mode='eventlet',
        logger=True,
        engineio_logger=True,
        ping_timeout=60,
        ping_interval=25,
        message_queue=app.config.get('REDIS_URL')
    )
    
    # Set up error handlers
    @socketio.on_error()
    def error_handler(e):
        logger.error(f"WebSocket error: {str(e)}", exc_info=True)
    
    return socketio

@socketio.on('connect')
def handle_connect():
    """Handle new WebSocket connection"""
    logger.info(f"Client connected: {flask_request.sid}")
    try:
        # Verify the connection by sending a test message
        emit('connection_established', {
            'message': 'Successfully connected to WebSocket server',
            'sid': flask_request.sid,
            'timestamp': datetime.utcnow().isoformat()
        })
    except Exception as e:
        logger.error(f"Error in handle_connect: {str(e)}", exc_info=True)

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    print(f"Client disconnected: {flask_request.sid}")
    # Remove from active riders if they were connected as a rider
    for rider_id, sid in list(active_riders.items()):
        if sid == flask_request.sid:
            del active_riders[rider_id]
            # Update rider availability in database
            try:
                rider = RiderAvailability.query.filter_by(rider_id=rider_id).first()
                if rider:
                    rider.is_online = False
                    rider.last_seen = datetime.utcnow()
                    db.session.commit()
                    print(f"Rider {rider_id} marked as offline")
            except Exception as e:
                db.session.rollback()
                print(f"Error updating rider {rider_id} status on disconnect: {str(e)}")
            break

@socketio.on('rider_online')
def handle_rider_online(data):
    """Handle when a rider comes online"""
    try:
        rider_id = data.get('rider_id')
        if not rider_id:
            logger.warning("No rider_id provided in rider_online event")
            return
            
        logger.info(f"Rider {rider_id} is now online (SID: {flask_request.sid})")
        
        # Store the socket ID for this rider
        active_riders[rider_id] = flask_request.sid
        
        # Update rider availability in database
        try:
            rider = RiderAvailability.query.filter_by(rider_id=rider_id).first()
            if not rider:
                rider = RiderAvailability(rider_id=rider_id, is_online=True)
                db.session.add(rider)
            else:
                rider.is_online = True
                rider.last_seen = datetime.utcnow()
            
            db.session.commit()
            logger.info(f"Rider {rider_id} marked as online in database")
            
            # Send any pending orders to this rider
            send_pending_orders_to_rider(rider_id)
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating rider {rider_id} status: {str(e)}", exc_info=True)
            # Don't return, continue with WebSocket setup
            
        # Acknowledge the rider is online
        emit('rider_online_ack', {
            'status': 'success',
            'rider_id': rider_id,
            'timestamp': datetime.utcnow().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Error in handle_rider_online: {str(e)}", exc_info=True)
        emit('rider_online_ack', {
            'status': 'error',
            'message': str(e),
            'timestamp': datetime.utcnow().isoformat()
        })
        if not rider_id:
            print("No rider_id provided in rider_online event")
            return {'status': 'error', 'message': 'No rider_id provided'}
            
        print(f"=== Rider {rider_id} is coming online (SID: {flask_request.sid}) ===")
        
        # Store the connection
        active_riders[rider_id] = flask_request.sid
        
        # Join the rider's personal room and the general riders room
        join_room(f'rider_{rider_id}')
        join_room('available_orders')  # Join the room where new orders are broadcast
        join_room('riders')  # General room for all riders
        
        print(f"Rider {rider_id} joined rooms: rider_{rider_id}, available_orders, riders")
        
        # Get the list of rooms this socket is in (for debugging)
        rooms = list(flask_request.rooms)
        print(f"Socket {flask_request.sid} is in rooms: {rooms}")
        
        # Update rider availability in database
        rider = RiderAvailability.query.filter_by(rider_id=rider_id).first()
        if not rider:
            print(f"Creating new rider availability record for rider {rider_id}")
            rider = RiderAvailability(rider_id=rider_id, is_online=True, is_available=True)
            db.session.add(rider)
        else:
            print(f"Updating existing rider {rider_id} to online")
            rider.is_online = True
            rider.is_available = True  # Make sure they're marked as available
            rider.last_seen = datetime.utcnow()
        
        db.session.commit()
        print(f"Rider {rider_id} marked as online and available in database")
        
        # Send any pending orders to the rider
        print(f"Sending pending orders to rider {rider_id}")
        send_pending_orders_to_rider(rider_id)
        
        # Send a confirmation back to the client
        return {
            'status': 'success',
            'message': 'Rider online and ready to receive orders',
            'rider_id': rider_id,
            'rooms': rooms
        }
        
    except Exception as e:
        db.session.rollback()
        error_msg = f"Error in handle_rider_online: {str(e)}\n{traceback.format_exc()}"
        print(error_msg)
        return {'status': 'error', 'message': str(e)}

def send_pending_orders_to_rider(rider_id):
    """Send all pending orders to a specific rider"""
    try:
        if rider_id not in active_riders:
            return
            
        # Get all orders that are confirmed or ready for pickup and not assigned
        pending_orders = Order.query.filter(
            Order.status.in_(['confirmed', 'ready_for_pickup']),
            Order.rider_id.is_(None)
        ).order_by(Order.created_at.desc()).all()  # Newest orders first
        
        for order in pending_orders:
            order_data = {
                'order_id': order.id,
                'order_number': order.order_number,
                'total_amount': float(order.total_amount) if order.total_amount else 0,
                'pickup_address': {
                    'name': order.seller.business_name or 'Store',
                    'address': f"{order.seller.address or 'Pickup Location'}, {order.seller.city or ''}, {order.seller.province or ''}",
                    'contact': order.seller.phone or ''
                },
                'delivery_address': {
                    'name': order.shipping_address.recipient_name,
                    'address': f"{order.shipping_address.street_address}, {order.shipping_address.city}, {order.shipping_address.province}",
                    'contact': order.shipping_address.contact_number
                },
                'items': [{
                    'product_name': item.product.name if item.product else 'Unknown Product',
                    'name': item.product.name if item.product else 'Unknown Product',
                    'quantity': item.quantity,
                    'price': float(item.price) if item.price else 0
                } for item in order.items],
                'items_count': len(order.items),
                'created_at': order.created_at.isoformat() if order.created_at else datetime.utcnow().isoformat()
            }
            
            emit('new_delivery_opportunity', {
                'order': order_data,
                'message': 'New delivery opportunity available! Click to accept.'
            }, room=active_riders[rider_id])
            
    except Exception as e:
        print(f"Error in send_pending_orders_to_rider: {str(e)}")

def notify_riders_new_order(order_data):
    """Notify all online riders about a new order (first-come, first-served)"""
    print("\n=== Starting notify_riders_new_order ===")
    print(f"Order data: {json.dumps(order_data, indent=2, default=str)}")
    
    try:
        # Get all online riders (all are considered available)
        from app.models.rider_availability import RiderAvailability
        online_riders = RiderAvailability.get_available_riders()
        
        print(f"Found {len(online_riders)} online riders to notify about order {order_data.get('id')}")
        
        # Get order details from database to ensure we have the latest data
        order_id = order_data.get('id')
        order = Order.query.get(order_id)
        
        if not order:
            print(f"Error: Order {order_id} not found in database")
            return
            
        # Skip if order is already assigned
        if order.rider_id is not None:
            print(f"Order {order_id} is already assigned to rider {order.rider_id}, skipping notification")
            return
            
        # Prepare order data for the client
        order_info = {
            'id': order.id,
            'order_id': order.id,  # For backward compatibility
            'order_number': order.order_number or f"ORDER-{order.id}",
            'user_id': order.user_id,
            'total_amount': float(order.total_amount) if order.total_amount else 0,
            'status': order.status,
            'created_at': order.created_at.isoformat() if order.created_at else datetime.utcnow().isoformat(),
            'shipping_address': {
                'recipient_name': order.shipping_address.recipient_name if order.shipping_address else 'Customer',
                'street_address': order.shipping_address.street_address if order.shipping_address else 'Address not provided',
                'city': order.shipping_address.city if order.shipping_address else '',
                'province': order.shipping_address.province if order.shipping_address else ''
            },
            'items': [{
                'product_name': item.product.name if item.product else 'Unknown Product',
                'name': item.product.name if item.product else 'Unknown Product',  # For backward compatibility
                'quantity': item.quantity,
                'price': float(item.price) if item.price else 0,
                'total_price': float(item.quantity * (float(item.price) if item.price else 0))
            } for item in order.items],
            'items_count': len(order.items)
        }
        
        print(f"Prepared order info: {json.dumps(order_info, indent=2, default=str)}")
        
        # Notify each online rider
        for rider in online_riders:
            rider_id = rider.rider_id
            print(f"Sending notification to rider {rider_id}")
            emit('new_delivery_opportunity', {
                'order': order_info,
                'message': 'New delivery opportunity available! Click to accept.'
            }, room=f'rider_{rider.rider_id}')
            
        print(f"Notified {len(online_riders)} riders about order {order_data.get('id')}")
        
    except Exception as e:
        print(f"Error in notify_riders_new_order: {str(e)}")
        import traceback
        traceback.print_exc()

def notify_order_taken(order_id, rider_id):
    """Notify all riders that an order has been taken"""
    try:
        print(f"Notifying all riders that order {order_id} was taken by rider {rider_id}")
        
        # Notify the rider who took the order
        if rider_id in active_riders:
            emit('order_accepted', {
                'order_id': order_id,
                'message': 'You have accepted this order.'
            }, room=active_riders[rider_id])
        
        # Notify all other riders that the order is no longer available
        socketio.emit('order_taken', {
            'order_id': order_id,
            'rider_id': rider_id,
            'message': 'This order has been accepted by another rider.'
        }, room='riders')
        
    except Exception as e:
        print(f"Error in notify_order_taken: {str(e)}")

@socketio.on('accept_order')
def handle_accept_order(data):
    """Handle when a rider accepts an order (first-come, first-served)"""
    try:
        order_id = data.get('order_id')
        rider_id = data.get('rider_id')
        
        if not order_id or not rider_id:
            emit('accept_order_error', {'message': 'Missing order_id or rider_id'})
            return
            
        print(f"Rider {rider_id} is attempting to accept order {order_id}")
        
        # Start a database transaction
        with db.session.begin_nested():
            # Check if the rider is still online and available
            rider = RiderAvailability.query.filter_by(
                rider_id=rider_id,
                is_online=True,
                is_available=True
            ).with_for_update().first()  # Lock the row for update
            
            if not rider:
                emit('accept_order_error', {
                    'order_id': order_id,
                    'message': 'You are not available to accept orders.'
                }, room=f'rider_{rider_id}')
                return
                
            # Get the order and check if it's still available
            # Use FOR UPDATE to lock the row and prevent race conditions
            order = Order.query.filter_by(
                id=order_id,
                status='confirmed',
                rider_id=None  # Ensure order isn't already taken
            ).with_for_update().first()
            
            if not order:
                emit('accept_order_error', {
                    'order_id': order_id,
                    'message': 'This order is no longer available.'
                }, room=f'rider_{rider_id}')
                return
                
            # Assign the order to the rider
            order.rider_id = rider_id
            # Keep status as 'confirmed' - we'll change it when picked up
            
            # Create delivery record using the Delivery model
            delivery = Delivery.create(
                order_id=order_id,
                rider_id=rider_id,
                delivery_notes='Order accepted via WebSocket'
            )
            
            if not delivery:
                logger.error(f"Failed to create delivery record for order {order_id}")
                return False
                
            logger.info(f"Order {order_id} assigned to rider {rider_id}")
            
            # Get order details for notification
            order = Order.query.get(order_id)
            if not order:
                logger.error(f"Order {order_id} not found after delivery creation")
                return False
                
            # Get addresses for notification
            try:
                pickup_address = order.seller.address if order.seller and hasattr(order.seller, 'address') else 'Pickup Address'
                delivery_address = order.shipping_address
                
                # Mark rider as busy
                rider = RiderAvailability.query.filter_by(rider_id=rider_id).first()
                if rider:
                    rider.is_available = False
                    rider.current_order_id = order_id
                    db.session.commit()
                
                return True
                
            except Exception as e:
                logger.error(f"Error in post-delivery processing: {str(e)}")
                db.session.rollback()
                return False
        
        # Notify the rider that they've successfully accepted the order
        emit('order_accepted', {
            'order_id': order_id,
            'message': 'You have successfully accepted the order! Please proceed to pickup.',
            'order': {
                'id': order.id,
                'status': order.status,
                'total_amount': float(order.total_amount),
                'shipping_address': order.shipping_address,
                'items': [{
                    'product_name': item.product.name,
                    'quantity': item.quantity,
                    'price': float(item.price)
                } for item in order.items]
            }
        }, room=f'rider_{rider_id}')
        
        # Notify all other riders that the order is no longer available
        notify_order_taken(order_id, rider_id)
        
        # Notify the seller that the order has been accepted by a rider
        if order.seller:
            emit('rider_assigned', {
                'order_id': order_id,
                'rider_id': rider_id,
                'message': f'Order {order_id} has been assigned to a rider.'
            }, room=f'seller_{order.seller_id}')
        
        # Notify the buyer that their order is on the way
        emit('order_status_updated', {
            'order_id': order_id,
            'status': 'assigned',
            'message': 'A rider has been assigned to your order and will pick it up soon.'
        }, room=f'user_{order.user_id}')
        
        print(f"Order {order_id} successfully assigned to rider {rider_id}")
        
    except Exception as e:
        db.session.rollback()
        error_msg = f"Error accepting order: {str(e)}"
        print(error_msg)
        import traceback
        traceback.print_exc()
        
        emit('accept_order_error', {
            'order_id': order_id,
            'message': 'An error occurred while accepting the order. Please try again.'
        }, room=f'rider_{rider_id}')
