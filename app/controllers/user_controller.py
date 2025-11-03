from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from app.models.user import User
from app.models.cart import Cart
from app.models.order import Order
from app.models.seller_request import SellerRequest
from app.models.review import Review
from app.utils.decorators import login_required
from app.forms import BecomeSellerForm, CheckoutForm, ReviewForm, CartUpdateForm, CartAddForm, ProfileUpdateForm, ChangePasswordForm
from werkzeug.utils import secure_filename
import os
import uuid

user_bp = Blueprint('user', __name__)

@user_bp.route('/dashboard')
@login_required
def dashboard():
    """User dashboard"""
    user = User.get_by_id(session['user_id'])
    if user['role'] != 'user':
        return redirect(url_for('public.landing'))
    
    # Get recent orders
    recent_orders = Order.list_for_user(user['id'], limit=5)
    
    # Get cart items count
    cart_items = Cart.get_user_cart(user['id'])
    cart_count = len(cart_items)
    
    return render_template('user/dashboard.html',
                         user=user,
                         recent_orders=recent_orders,
                         cart_count=cart_count)

@user_bp.route('/cart')
@login_required
def view_cart():
    """View shopping cart"""
    user_id = session['user_id']
    cart_items = Cart.get_user_cart(user_id)
    cart_total = Cart.get_cart_total(user_id)
    
    return render_template('user/cart.html',
                         cart_items=cart_items,
                         cart_total=cart_total,
                         total=cart_total['total'])

@user_bp.route('/cart/add', methods=['POST'])
@login_required
def add_to_cart():
    """Add product to cart"""
    form = CartAddForm()
    if form.validate_on_submit():
        user_id = session['user_id']
        product_id = form.product_id.data
        quantity = form.quantity.data
        
        try:
            Cart.add_item(user_id, product_id, quantity)
            flash('Item added to cart!', 'success')
        except Exception as e:
            flash('Failed to add item to cart.', 'error')
    else:
        flash('Invalid form data.', 'error')
    
    return redirect(request.referrer or url_for('public.browse_products'))

@user_bp.route('/cart/update', methods=['POST'])
@login_required
def update_cart():
    """Update cart item quantity"""
    form = CartUpdateForm()
    if form.validate_on_submit():
        cart_id = form.cart_id.data
        quantity = form.quantity.data
        
        try:
            Cart.update_item(cart_id, quantity)
            if quantity > 0:
                flash('Cart updated!', 'success')
            else:
                flash('Item removed from cart!', 'info')
        except Exception as e:
            flash('Failed to update cart.', 'error')
    else:
        flash('Invalid form data.', 'error')
    
    return redirect(url_for('user.view_cart'))

@user_bp.route('/cart/remove/<int:cart_id>')
@login_required
def remove_from_cart(cart_id):
    """Remove item from cart"""
    try:
        Cart.remove_item_by_id(cart_id)
        flash('Item removed from cart!', 'info')
    except Exception as e:
        flash('Failed to remove item.', 'error')
    
    return redirect(url_for('user.view_cart'))

@user_bp.route('/checkout', methods=['GET', 'POST'])
@login_required
def checkout():
    """Checkout process"""
    user_id = session['user_id']
    user = User.get_by_id(user_id)
    
    # Check if cart is empty
    cart_items = Cart.get_user_cart(user_id)
    if not cart_items:
        flash('Your cart is empty.', 'warning')
        return redirect(url_for('user.view_cart'))
    
    form = CheckoutForm()
    if form.validate_on_submit():
        shipping_address = form.shipping_address.data.strip()
        payment_method = form.payment_method.data
        notes = form.notes.data.strip() if form.notes.data else None
        
        # Create orders
        try:
            order_ids = Order.create_from_cart(user_id, shipping_address, payment_method, notes)
            if order_ids:
                flash(f'Order(s) placed successfully! Order IDs: {", ".join(map(str, order_ids))}', 'success')
                return redirect(url_for('user.orders'))
            else:
                flash('Failed to place order. Please try again.', 'error')
        except Exception as e:
            flash('An error occurred while placing your order.', 'error')
    elif request.method == 'POST':
        flash('Please correct the errors in the form.', 'error')
    
    cart_total = Cart.get_cart_total(user_id)
    return render_template('user/checkout.html',
                         cart_items=cart_items,
                         user=user,
                         cart_total=cart_total,
                         total=cart_total['total'])

@user_bp.route('/orders')
@login_required
def orders():
    """View user orders"""
    user_id = session['user_id']
    page = int(request.args.get('page', 1))
    per_page = 10
    offset = (page - 1) * per_page
    
    user_orders = Order.list_for_user(user_id, limit=per_page, offset=offset)
    
    return render_template('user/orders.html',
                         orders=user_orders)

@user_bp.route('/order/<int:order_id>')
@login_required
def order_detail(order_id):
    """View order details"""
    user_id = session['user_id']
    order = Order.get_by_id(order_id)
    
    # Check if order belongs to current user
    if not order or order['user_id'] != user_id:
        flash('Order not found.', 'error')
        return redirect(url_for('user.orders'))
    
    return render_template('user/order_detail.html', order=order)

@user_bp.route('/review/add', methods=['POST'])
@login_required
def add_review():
    """Add a product review"""
    form = ReviewForm()
    if form.validate_on_submit():
        user_id = session['user_id']
        product_id = int(form.product_id.data)
        rating = int(form.rating.data)
        comment = form.comment.data.strip() if form.comment.data else None
        
        try:
            Review.create(user_id, product_id, rating, comment)
            flash('Review added successfully!', 'success')
        except Exception as e:
            flash('Failed to add review.', 'error')
        
        return redirect(request.referrer or url_for('public.product_detail', product_id=product_id))
    else:
        flash('Invalid review data.', 'error')
        return redirect(request.referrer or url_for('public.browse_products'))

@user_bp.route('/become-seller', methods=['GET', 'POST'])
@login_required
def become_seller():
    """Apply to become a seller"""
    user_id = session['user_id']
    user = User.get_by_id(user_id)

    # Check if user is already a seller or admin
    if user['role'] != 'user':
        flash('You already have seller/admin privileges.', 'info')
        return redirect(url_for('user.dashboard'))

    # Check if user already has a pending request
    existing_request = SellerRequest.get_by_user_id(user_id)
    if existing_request and existing_request['status'] == 'pending':
        flash('You already have a pending seller request.', 'info')
        return render_template('user/seller_request_status.html', request=existing_request)

    form = BecomeSellerForm()
    if form.validate_on_submit():
        # Handle file upload for business permit (required)
        business_permit_filename = None
        if form.business_permit.data and hasattr(form.business_permit.data, 'filename') and form.business_permit.data.filename:
            from PIL import Image
            import uuid

            # Create uploads directory if it doesn't exist
            uploads_dir = os.path.join('static', 'uploads', 'business_permits')
            os.makedirs(uploads_dir, exist_ok=True)

            # Generate unique filename
            file_ext = os.path.splitext(form.business_permit.data.filename)[1].lower()
            if file_ext not in ['.jpg', '.jpeg', '.png', '.gif', '.pdf']:
                file_ext = '.jpg'  # Default to jpg if unknown extension
            unique_filename = f"{uuid.uuid4().hex}_{user['username']}{file_ext}"
            business_permit_path = os.path.join(uploads_dir, unique_filename)

            # Check if it's an image file
            if file_ext in ['.jpg', '.jpeg', '.png', '.gif']:
                try:
                    # Open and process the image
                    image = Image.open(form.business_permit.data)

                    # Convert to RGB if necessary (for PNG with transparency)
                    if image.mode in ('RGBA', 'LA', 'P'):
                        image = image.convert('RGB')

                    # Resize to a reasonable size (max 1200x1200 for documents, maintain aspect ratio)
                    max_size = (1200, 1200)
                    image.thumbnail(max_size, Image.Resampling.LANCZOS)

                    # Save as JPEG with good quality
                    image.save(business_permit_path, 'JPEG', quality=85, optimize=True)
                    business_permit_filename = f"uploads/business_permits/{unique_filename}"

                except Exception as e:
                    # Fallback to original upload if processing fails
                    secure_filename_str = secure_filename(f"{user['username']}_{form.business_permit.data.filename}")
                    fallback_path = os.path.join(uploads_dir, secure_filename_str)
                    form.business_permit.data.save(fallback_path)
                    business_permit_filename = f"uploads/business_permits/{secure_filename_str}"
            else:
                # For non-image files (like PDF), save as-is
                form.business_permit.data.save(business_permit_path)
                business_permit_filename = f"uploads/business_permits/{unique_filename}"

        try:
            seller_request = SellerRequest.create(
                user_id=user_id,
                business_name=form.business_name.data.strip(),
                business_description=form.business_description.data.strip(),
                business_address=form.business_address.data.strip(),
                business_phone=form.business_phone.data.strip(),
                tax_id=form.tax_id.data.strip() if form.tax_id.data else None,
                business_permit=business_permit_filename
            )

            if seller_request:
                flash('Seller request submitted successfully! Please wait for admin approval.', 'success')
                return render_template('user/seller_request_status.html', request=seller_request)
            else:
                flash('Failed to submit seller request. Please try again.', 'error')
        except Exception as e:
            flash('An error occurred while submitting your request.', 'error')
    elif request.method == 'POST':
        if not business_permit_filename:
            flash('Business permit is required.', 'error')
        else:
            flash('Please correct the errors in the form.', 'error')

    return render_template('user/become_seller.html', form=form)

@user_bp.route('/seller-request-status')
@login_required
def seller_request_status():
    """Check seller request status"""
    user_id = session['user_id']
    seller_request = SellerRequest.get_by_user_id(user_id)
    
    if not seller_request:
        flash('No seller request found.', 'info')
        return redirect(url_for('user.become_seller'))
    
    return render_template('user/seller_request_status.html', request=seller_request)

@user_bp.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    """User account settings"""
    user_id = session['user_id']
    user = User.get_by_id(user_id)
    
    profile_form = ProfileUpdateForm()
    password_form = ChangePasswordForm()
    
    if profile_form.validate_on_submit():
        # Check if username/email already exists (excluding current user)
        if profile_form.username.data != user['username']:
            existing_user = User.get_by_username(profile_form.username.data)
            if existing_user and existing_user['id'] != user_id:
                flash('Username already taken.', 'error')
                return render_template('user/settings.html', user=user, profile_form=profile_form, password_form=password_form)
        
        if profile_form.email.data != user['email']:
            existing_email = User.get_by_email(profile_form.email.data)
            if existing_email and existing_email['id'] != user_id:
                flash('Email already in use.', 'error')
                return render_template('user/settings.html', user=user, profile_form=profile_form, password_form=password_form)
        
        # Handle profile image upload
        profile_image_path = user.get('profile_image', None)
        if profile_form.profile_image.data:
            from PIL import Image
            import uuid

            # Generate unique filename
            file_ext = os.path.splitext(profile_form.profile_image.data.filename)[1].lower()
            if file_ext not in ['.jpg', '.jpeg', '.png', '.gif']:
                file_ext = '.jpg'  # Default to jpg if unknown extension
            unique_filename = f"{uuid.uuid4().hex}_{user_id}{file_ext}"
            upload_path = os.path.join('static', 'uploads', 'profiles', unique_filename)
            os.makedirs(os.path.dirname(upload_path), exist_ok=True)

            try:
                # Open and process the image
                image = Image.open(profile_form.profile_image.data)

                # Convert to RGB if necessary (for PNG with transparency)
                if image.mode in ('RGBA', 'LA', 'P'):
                    image = image.convert('RGB')

                # Resize to a reasonable size (max 400x400 for profile images, maintain aspect ratio)
                max_size = (400, 400)
                image.thumbnail(max_size, Image.Resampling.LANCZOS)

                # Save as JPEG with good quality
                image.save(upload_path, 'JPEG', quality=85, optimize=True)
                profile_image_path = f"uploads/profiles/{unique_filename}"

            except Exception as e:
                # Fallback to original upload if processing fails
                filename = secure_filename(profile_form.profile_image.data.filename)
                if filename:
                    fallback_filename = f"{uuid.uuid4().hex}_{filename}"
                    fallback_path = os.path.join('static', 'uploads', 'profiles', fallback_filename)
                    profile_form.profile_image.data.save(fallback_path)
                    profile_image_path = f"uploads/profiles/{fallback_filename}"
        
        # Update profile
        try:
            User.update(user_id,
                      username=profile_form.username.data,
                      email=profile_form.email.data,
                      first_name=profile_form.first_name.data,
                      last_name=profile_form.last_name.data,
                      phone=profile_form.phone.data,
                      address=profile_form.address.data,
                      profile_image=profile_image_path)
            flash('Profile updated successfully!', 'success')
            user = User.get_by_id(user_id)  # Refresh user data
        except Exception as e:
            flash('Failed to update profile.', 'error')
    
    if password_form.validate_on_submit():
        # Validate current password
        if not User.authenticate(user['email'], password_form.current_password.data):
            flash('Current password is incorrect.', 'error')
            return render_template('user/settings.html', user=user, profile_form=profile_form, password_form=password_form)
        
        # Update password
        try:
            User.update_password(user_id, password_form.new_password.data)
            flash('Password changed successfully!', 'success')
        except Exception as e:
            flash('Failed to change password.', 'error')
    
    return render_template('user/settings.html', user=user, profile_form=profile_form, password_form=password_form)
