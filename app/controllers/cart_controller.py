from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from app.models.cart import Cart
from app.models.product import Product
from app.models.order import Order
from app.utils.decorators import login_required
import json

cart_bp = Blueprint('cart', __name__)

@cart_bp.route('/')
@login_required
def view_cart():
    """Display user's cart with shipping fees"""
    user_id = session['user_id']
    cart_items = Cart.get_user_cart(user_id)
    
    # Get cart total with shipping fees
    cart_total = Cart.get_cart_total(user_id)
    
    return render_template('user/cart.html', 
                         cart_items=cart_items, 
                         cart_total=cart_total,
                         total=cart_total['total'])

@cart_bp.route('/add', methods=['POST'])
@login_required
def add_to_cart():
    """Add item to cart"""
    try:
        product_id = int(request.form.get('product_id'))
        quantity = int(request.form.get('quantity', 1))
        
        if quantity <= 0:
            flash('Invalid quantity.', 'error')
            return redirect(request.referrer or url_for('public.products'))
        
        # Check if product exists and has sufficient stock
        product = Product.get_by_id(product_id)
        if not product:
            flash('Product not found.', 'error')
            return redirect(request.referrer or url_for('public.products'))
        
        if product['status'] != 'active':
            flash('Product is not available.', 'error')
            return redirect(request.referrer or url_for('public.products'))
        
        if product['stock_quantity'] < quantity:
            flash(f'Only {product["stock_quantity"]} items available.', 'error')
            return redirect(request.referrer or url_for('public.products'))
        
        # Add to cart
        user_id = session['user_id']
        if Cart.add_item(user_id, product_id, quantity):
            flash(f'{product["name"]} added to cart successfully!', 'success')
        else:
            flash('Failed to add item to cart.', 'error')
        
        # Check if request is AJAX
        if request.headers.get('Content-Type') == 'application/json':
            cart_count = len(Cart.get_user_cart(user_id))
            return jsonify({'success': True, 'cart_count': cart_count})
        
        return redirect(request.referrer or url_for('public.products'))
        
    except (ValueError, TypeError) as e:
        flash('Invalid request.', 'error')
        return redirect(request.referrer or url_for('public.products'))

@cart_bp.route('/update', methods=['POST'])
@login_required
def update_cart():
    """Update cart item quantity"""
    try:
        cart_id = int(request.form.get('cart_id'))
        quantity = int(request.form.get('quantity'))
        
        if quantity < 0:
            flash('Invalid quantity.', 'error')
            return redirect(url_for('cart.view_cart'))
        
        # Get cart item to check ownership
        user_id = session['user_id']
        cart_items = Cart.get_user_cart(user_id)
        cart_item = next((item for item in cart_items if item['id'] == cart_id), None)
        
        if not cart_item:
            flash('Cart item not found.', 'error')
            return redirect(url_for('cart.view_cart'))
        
        # Check stock availability
        product = Product.get_by_id(cart_item['product_id'])
        if product and quantity > 0 and product['stock_quantity'] < quantity:
            flash(f'Only {product["stock_quantity"]} items available for {product["name"]}.', 'error')
            return redirect(url_for('cart.view_cart'))
        
        # Update cart
        if Cart.update_item(cart_id, quantity):
            if quantity == 0:
                flash('Item removed from cart.', 'info')
            else:
                flash('Cart updated successfully!', 'success')
        else:
            flash('Failed to update cart.', 'error')
        
        return redirect(url_for('cart.view_cart'))
        
    except (ValueError, TypeError):
        flash('Invalid request.', 'error')
        return redirect(url_for('cart.view_cart'))

@cart_bp.route('/remove', methods=['POST'])
@login_required
def remove_from_cart():
    """Remove item from cart"""
    try:
        cart_id = int(request.form.get('cart_id'))
        
        # Get cart item to check ownership
        user_id = session['user_id']
        cart_items = Cart.get_user_cart(user_id)
        cart_item = next((item for item in cart_items if item['id'] == cart_id), None)
        
        if not cart_item:
            flash('Cart item not found.', 'error')
            return redirect(url_for('cart.view_cart'))
        
        if Cart.remove_item_by_id(cart_id):
            flash('Item removed from cart successfully!', 'success')
        else:
            flash('Failed to remove item from cart.', 'error')
        
        return redirect(url_for('cart.view_cart'))
        
    except (ValueError, TypeError):
        flash('Invalid request.', 'error')
        return redirect(url_for('cart.view_cart'))

@cart_bp.route('/clear', methods=['POST'])
@login_required
def clear_cart():
    """Clear entire cart"""
    user_id = session['user_id']
    
    if Cart.clear_cart(user_id):
        flash('Cart cleared successfully!', 'info')
    else:
        flash('Failed to clear cart.', 'error')
    
    return redirect(url_for('cart.view_cart'))

@cart_bp.route('/checkout', methods=['GET', 'POST'])
@login_required
def checkout():
    """Checkout process"""
    user_id = session['user_id']
    cart_items = Cart.get_user_cart(user_id)
    
    if not cart_items:
        flash('Your cart is empty.', 'error')
        return redirect(url_for('cart.view_cart'))
    
    # Check stock availability for all items
    for item in cart_items:
        product = Product.get_by_id(item['product_id'])
        if not product or product['status'] != 'active':
            flash(f'Product "{item["name"]}" is no longer available.', 'error')
            return redirect(url_for('cart.view_cart'))
        
        if product['stock_quantity'] < item['quantity']:
            flash(f'Insufficient stock for "{item["name"]}". Only {product["stock_quantity"]} available.', 'error')
            return redirect(url_for('cart.view_cart'))
    
    total = Cart.get_total(user_id)
    
    if request.method == 'POST':
        shipping_address = request.form.get('shipping_address', '').strip()
        payment_method = request.form.get('payment_method', 'cod')
        notes = request.form.get('notes', '').strip()
        
        if not shipping_address:
            flash('Shipping address is required.', 'error')
            return render_template('cart/checkout.html', 
                                 cart_items=cart_items, 
                                 total=total)
        
        # Create orders (grouped by seller)
        order_ids = Order.create_from_cart(user_id, shipping_address, payment_method, notes)
        
        if order_ids:
            flash(f'Order(s) placed successfully! Order IDs: {", ".join(map(str, order_ids))}', 'success')
            return redirect(url_for('user.orders'))
        else:
            flash('Failed to place order. Please try again.', 'error')
    
    return render_template('cart/checkout.html', 
                         cart_items=cart_items, 
                         total=total)

@cart_bp.route('/count')
@login_required
def cart_count():
    """Get cart item count (AJAX endpoint)"""
    user_id = session['user_id']
    cart_items = Cart.get_user_cart(user_id)
    return jsonify({'count': len(cart_items)})

@cart_bp.route('/mini-cart')
@login_required
def mini_cart():
    """Get mini cart data for header display"""
    user_id = session['user_id']
    cart_items = Cart.get_user_cart(user_id)
    total = Cart.get_total(user_id)
    
    return jsonify({
        'items': cart_items[:5],  # Show only first 5 items
        'count': len(cart_items),
        'total': total
    })