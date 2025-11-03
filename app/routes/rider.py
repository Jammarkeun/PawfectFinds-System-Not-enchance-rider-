from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from sqlalchemy import and_, or_, func, desc, text
from app import db
from app.models.models import Order, OrderItem, User, RiderEarning, RiderPerformance, Notification
from app.utils.auth import role_required, get_current_user
from datetime import datetime, timedelta
from app.services.websocket_service import socketio
import json

rider_bp = Blueprint('rider', __name__)

@rider_bp.route('/dashboard')
@role_required('rider')
def dashboard():
    """Rider dashboard"""
    rider = get_current_user()
    
    # Get current statistics
    pending_deliveries = Order.query.filter_by(
        rider_id=rider.id,
        status='out_for_delivery'
    ).count()
    
    completed_deliveries = Order.query.filter_by(
        rider_id=rider.id,
        status='delivered'
    ).count()
    
    # Earnings this month
    current_month = datetime.now().replace(day=1)
    monthly_earnings = db.session.query(func.sum(RiderEarning.total_earning)).filter(
        RiderEarning.rider_id == rider.id,
        RiderEarning.created_at >= current_month
    ).scalar() or 0
    
    # Average rating
    avg_rating = db.session.query(func.avg(RiderPerformance.rating)).filter(
        RiderPerformance.rider_id == rider.id
    ).scalar() or 0
    
    # Recent deliveries
    recent_deliveries = Order.query.filter_by(rider_id=rider.id).order_by(
        desc(Order.updated_at)
    ).limit(10).all()
    
    # Available orders (orders that are shipped but not assigned to any rider)
    available_orders = Order.query.filter_by(
        status='shipped',
        rider_id=None
    ).order_by(Order.created_at).limit(10).all()
    
    return render_template('rider/dashboard.html',
                         pending_deliveries=pending_deliveries,
                         completed_deliveries=completed_deliveries,
                         monthly_earnings=monthly_earnings,
                         avg_rating=round(avg_rating, 1) if avg_rating else 0,
                         recent_deliveries=recent_deliveries,
                         available_orders=available_orders)

@rider_bp.route('/available-orders')
@role_required('rider')
def available_orders():
    """API endpoint to get available orders for pickup"""
    try:
        rider = get_current_user()
        
        # Mark rider as available
        rider_availability = RiderAvailability.query.filter_by(rider_id=rider.id).first()
        if rider_availability:
            rider_availability.is_available = True
            rider_availability.current_order_id = None
            db.session.commit()
        
        # Get available orders (not assigned to any rider and in a ready state)
        available_orders = Order.query.filter(
            Order.status.in_(['ready_for_pickup', 'confirmed', 'shipped']),
            Order.rider_id.is_(None)
        ).order_by(Order.created_at.asc()).all()  # Oldest orders first
        
        # Convert orders to a list of dictionaries
        orders_list = []
        for order in available_orders:
            orders_list.append({
                'id': order.id,
                'order_number': order.order_number or f'ORD-{order.id:05d}',
                'status': order.status,
                'total_amount': float(order.total_amount) if order.total_amount else 0,
                'item_count': len(order.items) if hasattr(order, 'items') else 0,
                'created_at': order.created_at.isoformat() if order.created_at else None,
                'shipping_address': {
                    'street': order.shipping_address.street_address if hasattr(order.shipping_address, 'street_address') else 'Not specified',
                    'city': order.shipping_address.city if hasattr(order.shipping_address, 'city') else '',
                    'province': order.shipping_address.province if hasattr(order.shipping_address, 'province') else ''
                } if hasattr(order, 'shipping_address') and order.shipping_address else {}
            })
        
        return jsonify({
            'success': True,
            'orders': orders_list
        })
        
    except Exception as e:
        current_app.logger.error(f'Error in available_orders: {str(e)}')
        return jsonify({
            'success': False,
            'message': 'Failed to fetch available orders',
            'error': str(e)
        }), 500

@rider_bp.route('/order/<int:order_id>/accept', methods=['POST'])
@role_required('rider')
def accept_order(order_id):
    """Accept a delivery order"""
    rider = get_current_user()
    
    # Check if rider is available
    rider_availability = RiderAvailability.query.filter_by(rider_id=rider.id).first()
    if not rider_availability or not rider_availability.is_available:
        return jsonify({
            'success': False,
            'message': 'You are not available for new deliveries.'
        }), 400
    
    # Start a database transaction
    try:
        # Use SELECT FOR UPDATE to lock the row
        order = Order.query.filter_by(
            id=order_id,
            status='ready_for_pickup',
            rider_id=None
        ).with_for_update().first()
        
        if not order:
            return jsonify({
                'success': False,
                'message': 'Order is no longer available.'
            }), 400
        
        # Assign order to rider
        order.rider_id = rider.id
        order.status = 'assigned'
        order.assigned_at = datetime.utcnow()
        
        # Update rider availability
        rider_availability.is_available = False
        rider_availability.current_order_id = order.id
        
        # Create notification
        # Create earnings record
        from app.models.models import WebsiteSetting
        base_fee_setting = WebsiteSetting.query.filter_by(setting_key='rider_base_fee').first()
        base_fee = float(base_fee_setting.setting_value) if base_fee_setting else 3.00
        
        earning = RiderEarning(
            rider_id=rider.id,
            order_id=order.id,
            base_fee=base_fee,
            distance_fee=0,  # Can be calculated based on distance
            tip_amount=0,
            total_earning=base_fee,
            status='pending'
        )
        
        # Create notification for customer
        notification = Notification(
            user_id=order.user_id,
            type='delivery_update',
            title='Order Out for Delivery',
            message=f'Your order {order.order_number} is now out for delivery.',
            related_id=order.id
        )
        
        db.session.add(earning)
        db.session.add(notification)
        db.session.commit()
        
        flash('Order accepted successfully!', 'success')
        return redirect(url_for('rider.my_deliveries'))
        
    except Exception as e:
        db.session.rollback()
        flash('Failed to accept order.', 'error')
    
    return redirect(url_for('rider.available_orders'))

@rider_bp.route('/my-deliveries')
@role_required('rider')
def my_deliveries():
    """View assigned deliveries"""
    rider = get_current_user()
    page = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', '')
    
    query = Order.query.filter_by(rider_id=rider.id)
    
    if status_filter:
        query = query.filter_by(status=status_filter)
    
    deliveries_paginated = query.order_by(desc(Order.updated_at)).paginate(
        page=page, per_page=15, error_out=False
    )
    
    return render_template('rider/my_deliveries.html',
                         deliveries=deliveries_paginated.items,
                         pagination=deliveries_paginated,
                         status_filter=status_filter)

@rider_bp.route('/delivery-detail/<int:order_id>')
@role_required('rider')
def delivery_detail(order_id):
    """View delivery details"""
    rider = get_current_user()
    order = Order.query.filter_by(
        id=order_id,
        rider_id=rider.id
    ).first_or_404()
    
    return render_template('rider/delivery_detail.html', order=order)

@rider_bp.route('/update-delivery-status', methods=['POST'])
@role_required('rider')
def update_delivery_status():
    """Update delivery status"""
    rider = get_current_user()
    order_id = request.form.get('order_id', type=int)
    new_status = request.form.get('status')
    notes = request.form.get('notes', '')
    
    if not order_id or not new_status:
        flash('Invalid data provided.', 'error')
        return redirect(request.referrer)
    
    order = Order.query.filter_by(
        id=order_id,
        rider_id=rider.id
    ).first_or_404()
    
    valid_statuses = ['out_for_delivery', 'delivered', 'cancelled']
    if new_status not in valid_statuses:
        flash('Invalid status.', 'error')
        return redirect(request.referrer)
    
    try:
        old_status = order.status
        order.status = new_status
        
        if new_status == 'delivered':
            order.delivered_at = datetime.now()
            
            # Update all order items to delivered
            for item in order.order_items:
                item.status = 'delivered'
            
            # Mark earnings as pending for payment
            earning = RiderEarning.query.filter_by(
                rider_id=rider.id,
                order_id=order_id
            ).first()
            if earning:
                earning.status = 'pending'
        
        elif new_status == 'cancelled':
            # If cancelled, make order available again
            order.rider_id = None
            order.status = 'shipped'
            
            # Remove earnings record
            earning = RiderEarning.query.filter_by(
                rider_id=rider.id,
                order_id=order_id
            ).first()
            if earning:
                db.session.delete(earning)
        
        # Create notification for customer
        status_messages = {
            'out_for_delivery': 'Your order is out for delivery.',
            'delivered': 'Your order has been delivered successfully.',
            'cancelled': 'Your delivery has been cancelled. We will reassign it to another rider.'
        }
        
        if new_status in status_messages:
            notification = Notification(
                user_id=order.user_id,
                type='delivery_update',
                title=f'Delivery Status Update - {order.order_number}',
                message=status_messages[new_status] + (f' Note: {notes}' if notes else ''),
                related_id=order.id
            )
            db.session.add(notification)
        
        db.session.commit()
        flash('Delivery status updated successfully!', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash('Failed to update delivery status.', 'error')
    
    return redirect(request.referrer)

@rider_bp.route('/earnings')
@role_required('rider')
def earnings():
    """View earnings and payment history"""
    rider = get_current_user()
    page = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', '')
    
    query = RiderEarning.query.filter_by(rider_id=rider.id)
    
    if status_filter:
        query = query.filter_by(status=status_filter)
    
    earnings_paginated = query.order_by(desc(RiderEarning.created_at)).paginate(
        page=page, per_page=15, error_out=False
    )
    
    # Calculate totals
    total_earnings = db.session.query(func.sum(RiderEarning.total_earning)).filter_by(
        rider_id=rider.id
    ).scalar() or 0
    
    pending_earnings = db.session.query(func.sum(RiderEarning.total_earning)).filter_by(
        rider_id=rider.id,
        status='pending'
    ).scalar() or 0
    
    paid_earnings = db.session.query(func.sum(RiderEarning.total_earning)).filter_by(
        rider_id=rider.id,
        status='paid'
    ).scalar() or 0
    
    return render_template('rider/earnings.html',
                         earnings=earnings_paginated.items,
                         pagination=earnings_paginated,
                         status_filter=status_filter,
                         total_earnings=total_earnings,
                         pending_earnings=pending_earnings,
                         paid_earnings=paid_earnings)

@rider_bp.route('/performance')
@role_required('rider')
def performance():
    """View performance ratings and feedback"""
    rider = get_current_user()
    page = request.args.get('page', 1, type=int)
    
    # Get performance ratings
    ratings_paginated = RiderPerformance.query.filter_by(
        rider_id=rider.id
    ).order_by(desc(RiderPerformance.created_at)).paginate(
        page=page, per_page=15, error_out=False
    )
    
    # Calculate average rating
    avg_rating = db.session.query(func.avg(RiderPerformance.rating)).filter_by(
        rider_id=rider.id
    ).scalar() or 0
    
    total_ratings = RiderPerformance.query.filter_by(rider_id=rider.id).count()
    
    # Rating distribution
    rating_distribution = {}
    for i in range(1, 6):
        count = RiderPerformance.query.filter_by(
            rider_id=rider.id,
            rating=i
        ).count()
        rating_distribution[i] = count
    
    return render_template('rider/performance.html',
                         ratings=ratings_paginated.items,
                         pagination=ratings_paginated,
                         avg_rating=round(avg_rating, 1),
                         total_ratings=total_ratings,
                         rating_distribution=rating_distribution)

@rider_bp.route('/profile')
@role_required('rider')
def profile():
    """Rider profile"""
    rider = get_current_user()
    return render_template('rider/profile.html', user=rider)

@rider_bp.route('/update-profile', methods=['POST'])
@role_required('rider')
def update_profile():
    """Update rider profile"""
    rider = get_current_user()
    
    # Get form data
    first_name = request.form.get('first_name', '').strip()
    last_name = request.form.get('last_name', '').strip()
    phone = request.form.get('phone', '').strip()
    address = request.form.get('address', '').strip()
    city = request.form.get('city', '').strip()
    state = request.form.get('state', '').strip()
    zip_code = request.form.get('zip_code', '').strip()
    
    # Validation
    if not first_name or not last_name:
        flash('First name and last name are required.', 'error')
        return redirect(url_for('rider.profile'))
    
    if not phone:
        flash('Phone number is required for delivery coordination.', 'error')
        return redirect(url_for('rider.profile'))
    
    try:
        # Update user
        rider.first_name = first_name
        rider.last_name = last_name
        rider.phone = phone
        rider.address = address
        rider.city = city
        rider.state = state
        rider.zip_code = zip_code
        
        db.session.commit()
        flash('Profile updated successfully!', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash('Failed to update profile.', 'error')
    
    return redirect(url_for('rider.profile'))

