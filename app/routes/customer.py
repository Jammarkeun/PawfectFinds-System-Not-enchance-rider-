from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from sqlalchemy import and_, or_
from app import db
from app.models.models import Product, CartItem, Order, OrderItem, Review, User, Notification, Wishlist
from app.utils.auth import login_required, role_required, get_current_user
from datetime import datetime
import uuid

customer_bp = Blueprint('customer', __name__)

@customer_bp.route('/dashboard')
@role_required('customer')
def dashboard():
    """Customer dashboard"""
    user = get_current_user()
    
    # Get recent orders
    recent_orders = Order.query.filter_by(user_id=user.id).order_by(
        Order.created_at.desc()
    ).limit(5).all()
    
    # Get cart item count
    cart_count = CartItem.query.filter_by(user_id=user.id).count()
    
    # Get unread notifications
    unread_notifications = Notification.query.filter_by(
        user_id=user.id,
        is_read=False
    ).order_by(Notification.created_at.desc()).limit(5).all()
    
    # Get wishlist count
    wishlist_count = Wishlist.query.filter_by(user_id=user.id).count()
    
    return render_template('customer/dashboard.html',
                         recent_orders=recent_orders,
                         cart_count=cart_count,
                         notifications=unread_notifications,
                         wishlist_count=wishlist_count)

@customer_bp.route('/cart')
@role_required('customer')
def cart():
    """Shopping cart"""
    user = get_current_user()
    cart_items = CartItem.query.filter_by(user_id=user.id).all()
    
    total_amount = 0
    for item in cart_items:
        total_amount += item.get_total_price()
    
    return render_template('customer/cart.html',
                         cart_items=cart_items,
                         total_amount=total_amount)

@customer_bp.route('/add-to-cart', methods=['POST'])
@role_required('customer')
def add_to_cart():
    """Add product to cart"""
    user = get_current_user()
    product_id = request.form.get('product_id', type=int)
    quantity = request.form.get('quantity', 1, type=int)
    
    if not product_id:
        flash('Invalid product.', 'error')
        return redirect(request.referrer or url_for('main.products'))
    
    product = Product.query.get(product_id)
    if not product or not product.is_in_stock():
        flash('Product is not available.', 'error')
        return redirect(request.referrer or url_for('main.products'))
    
    if quantity <= 0 or quantity > product.stock_quantity:
        flash('Invalid quantity.', 'error')
        return redirect(request.referrer or url_for('main.products'))
    
    # Check if item already in cart
    existing_item = CartItem.query.filter_by(
        user_id=user.id,
        product_id=product_id
    ).first()
    
    try:
        if existing_item:
            # Update quantity
            new_quantity = existing_item.quantity + quantity
            if new_quantity > product.stock_quantity:
                flash(f'Cannot add more items. Only {product.stock_quantity} available.', 'error')
                return redirect(request.referrer or url_for('main.products'))
            existing_item.quantity = new_quantity
        else:
            # Add new item
            cart_item = CartItem(
                user_id=user.id,
                product_id=product_id,
                quantity=quantity
            )
            db.session.add(cart_item)
        
        db.session.commit()
        flash(f'{product.name} added to cart!', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Failed to add item to cart.', 'error')
    
    return redirect(request.referrer or url_for('main.products'))

@customer_bp.route('/update-cart', methods=['POST'])
@role_required('customer')
def update_cart():
    """Update cart item quantity"""
    user = get_current_user()
    item_id = request.form.get('item_id', type=int)
    quantity = request.form.get('quantity', type=int)
    
    if not item_id or quantity is None:
        return jsonify({'success': False, 'message': 'Invalid data'})
    
    cart_item = CartItem.query.filter_by(
        id=item_id,
        user_id=user.id
    ).first()
    
    if not cart_item:
        return jsonify({'success': False, 'message': 'Item not found'})
    
    try:
        if quantity <= 0:
            # Remove item
            db.session.delete(cart_item)
        else:
            # Update quantity
            if quantity > cart_item.product.stock_quantity:
                return jsonify({
                    'success': False,
                    'message': f'Only {cart_item.product.stock_quantity} items available'
                })
            cart_item.quantity = quantity
        
        db.session.commit()
        
        # Calculate new totals
        cart_items = CartItem.query.filter_by(user_id=user.id).all()
        cart_total = sum(item.get_total_price() for item in cart_items)
        
        return jsonify({
            'success': True,
            'cart_total': cart_total,
            'item_total': cart_item.get_total_price() if quantity > 0 else 0,
            'cart_count': len(cart_items)
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Failed to update cart'})

@customer_bp.route('/remove-from-cart/<int:item_id>')
@role_required('customer')
def remove_from_cart(item_id):
    """Remove item from cart"""
    user = get_current_user()
    cart_item = CartItem.query.filter_by(
        id=item_id,
        user_id=user.id
    ).first_or_404()
    
    try:
        db.session.delete(cart_item)
        db.session.commit()
        flash('Item removed from cart.', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Failed to remove item.', 'error')
    
    return redirect(url_for('customer.cart'))

@customer_bp.route('/checkout')
@role_required('customer')
def checkout():
    """Checkout page"""
    user = get_current_user()
    cart_items = CartItem.query.filter_by(user_id=user.id).all()
    
    if not cart_items:
        flash('Your cart is empty.', 'warning')
        return redirect(url_for('customer.cart'))
    
    total_amount = sum(item.get_total_price() for item in cart_items)
    
    return render_template('customer/checkout.html',
                         cart_items=cart_items,
                         total_amount=total_amount)

@customer_bp.route('/place-order', methods=['POST'])
@role_required('customer')
def place_order():
    """Place an order"""
    user = get_current_user()
    cart_items = CartItem.query.filter_by(user_id=user.id).all()
    
    if not cart_items:
        flash('Your cart is empty.', 'error')
        return redirect(url_for('customer.cart'))
    
    # Get form data
    shipping_address = request.form.get('shipping_address', '').strip()
    billing_address = request.form.get('billing_address', '').strip()
    payment_method = request.form.get('payment_method', 'cash_on_delivery')
    notes = request.form.get('notes', '').strip()
    
    if not shipping_address:
        flash('Shipping address is required.', 'error')
        return redirect(url_for('customer.checkout'))
    
    # Calculate total
    total_amount = sum(item.get_total_price() for item in cart_items)
    
    # Generate order number
    order_number = f'PF-{datetime.now().strftime("%Y%m%d")}-{str(uuid.uuid4())[:8].upper()}'
    
    try:
        # Create order
        order = Order(
            user_id=user.id,
            order_number=order_number,
            total_amount=total_amount,
            shipping_address=shipping_address,
            billing_address=billing_address or shipping_address,
            payment_method=payment_method,
            notes=notes,
            status='pending'
        )
        db.session.add(order)
        db.session.flush()  # Get order ID
        
        # Create order items
        for cart_item in cart_items:
            order_item = OrderItem(
                order_id=order.id,
                product_id=cart_item.product_id,
                seller_id=cart_item.product.seller_id,
                quantity=cart_item.quantity,
                unit_price=cart_item.product.price,
                total_price=cart_item.get_total_price()
            )
            db.session.add(order_item)
            
            # Update product stock
            cart_item.product.stock_quantity -= cart_item.quantity
        
        # Clear cart
        for cart_item in cart_items:
            db.session.delete(cart_item)
        
        # Create notification for customer
        notification = Notification(
            user_id=user.id,
            type='order_status',
            title='Order Placed Successfully',
            message=f'Your order {order_number} has been placed successfully.',
            related_id=order.id
        )
        db.session.add(notification)
        
        db.session.commit()
        
        flash(f'Order placed successfully! Order number: {order_number}', 'success')
        return redirect(url_for('customer.order_detail', order_id=order.id))
    
    except Exception as e:
        db.session.rollback()
        flash('Failed to place order. Please try again.', 'error')
        return redirect(url_for('customer.checkout'))

@customer_bp.route('/orders')
@role_required('customer')
def orders():
    """Customer orders"""
    user = get_current_user()
    page = request.args.get('page', 1, type=int)
    
    orders_paginated = Order.query.filter_by(user_id=user.id).order_by(
        Order.created_at.desc()
    ).paginate(page=page, per_page=10, error_out=False)
    
    return render_template('customer/orders.html',
                         orders=orders_paginated.items,
                         pagination=orders_paginated)

@customer_bp.route('/order/<int:order_id>')
@role_required('customer')
def order_detail(order_id):
    """Order detail"""
    user = get_current_user()
    order = Order.query.filter_by(
        id=order_id,
        user_id=user.id
    ).first_or_404()
    
    return render_template('customer/order_detail.html', order=order)

@customer_bp.route('/profile')
@role_required('customer')
def profile():
    """Customer profile"""
    user = get_current_user()
    return render_template('customer/profile.html', user=user)

@customer_bp.route('/update-profile', methods=['POST'])
@role_required('customer')
def update_profile():
    """Update customer profile"""
    user = get_current_user()
    
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
        return redirect(url_for('customer.profile'))
    
    try:
        # Update user
        user.first_name = first_name
        user.last_name = last_name
        user.phone = phone
        user.address = address
        user.city = city
        user.state = state
        user.zip_code = zip_code
        
        db.session.commit()
        flash('Profile updated successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Failed to update profile.', 'error')
    
    return redirect(url_for('customer.profile'))

@customer_bp.route('/wishlist')
@role_required('customer')
def wishlist():
    """Customer wishlist"""
    user = get_current_user()
    wishlist_items = Wishlist.query.filter_by(user_id=user.id).all()
    
    return render_template('customer/wishlist.html',
                         wishlist_items=wishlist_items)

@customer_bp.route('/add-to-wishlist', methods=['POST'])
@role_required('customer')
def add_to_wishlist():
    """Add product to wishlist"""
    user = get_current_user()
    product_id = request.form.get('product_id', type=int)
    
    if not product_id:
        return jsonify({'success': False, 'message': 'Invalid product'})
    
    product = Product.query.get(product_id)
    if not product:
        return jsonify({'success': False, 'message': 'Product not found'})
    
    # Check if already in wishlist
    existing = Wishlist.query.filter_by(
        user_id=user.id,
        product_id=product_id
    ).first()
    
    if existing:
        return jsonify({'success': False, 'message': 'Already in wishlist'})
    
    try:
        wishlist_item = Wishlist(
            user_id=user.id,
            product_id=product_id
        )
        db.session.add(wishlist_item)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Added to wishlist'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Failed to add to wishlist'})

@customer_bp.route('/remove-from-wishlist/<int:product_id>')
@role_required('customer')
def remove_from_wishlist(product_id):
    """Remove product from wishlist"""
    user = get_current_user()
    wishlist_item = Wishlist.query.filter_by(
        user_id=user.id,
        product_id=product_id
    ).first_or_404()
    
    try:
        db.session.delete(wishlist_item)
        db.session.commit()
        flash('Item removed from wishlist.', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Failed to remove item.', 'error')
    
    return redirect(url_for('customer.wishlist'))

@customer_bp.route('/review/<int:order_item_id>', methods=['GET', 'POST'])
@role_required('customer')
def review_product(order_item_id):
    """Review a product"""
    user = get_current_user()
    
    # Get order item and verify ownership
    order_item = OrderItem.query.join(Order).filter(
        OrderItem.id == order_item_id,
        Order.user_id == user.id,
        OrderItem.status == 'delivered'
    ).first_or_404()
    
    # Check if review already exists
    existing_review = Review.query.filter_by(
        user_id=user.id,
        product_id=order_item.product_id,
        order_item_id=order_item_id
    ).first()
    
    if request.method == 'POST':
        rating = request.form.get('rating', type=int)
        comment = request.form.get('comment', '').strip()
        
        # Validation
        if not rating or rating < 1 or rating > 5:
            flash('Please select a rating between 1 and 5.', 'error')
            return render_template('customer/review.html',
                                 order_item=order_item,
                                 existing_review=existing_review)
        
        try:
            if existing_review:
                # Update existing review
                existing_review.rating = rating
                existing_review.comment = comment
                existing_review.status = 'pending'
            else:
                # Create new review
                review = Review(
                    user_id=user.id,
                    product_id=order_item.product_id,
                    order_item_id=order_item_id,
                    rating=rating,
                    comment=comment,
                    status='pending'
                )
                db.session.add(review)
            
            db.session.commit()
            flash('Review submitted successfully!', 'success')
            return redirect(url_for('customer.orders'))
        except Exception as e:
            db.session.rollback()
            flash('Failed to submit review.', 'error')
    
    return render_template('customer/review.html',
                         order_item=order_item,
                         existing_review=existing_review)