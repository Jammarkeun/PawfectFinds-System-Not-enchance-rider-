from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from werkzeug.utils import secure_filename
from sqlalchemy import and_, or_, func, text
from app import db
from app.models.models import Product, ProductImage, OrderItem, Order, Category, Notification, User
from app.utils.auth import role_required, get_current_user
from app.services.websocket_service import socketio
import uuid
import json
from datetime import datetime, timedelta

seller_bp = Blueprint('seller', __name__)

@seller_bp.route('/dashboard')
@role_required('seller')
def dashboard():
    """Seller dashboard with sales analytics"""
    user = get_current_user()
    
    # Get dashboard statistics
    total_products = Product.query.filter_by(seller_id=user.id).count()
    active_products = Product.query.filter_by(seller_id=user.id, status='active').count()
    
    # Get recent orders and orders for the template
    orders = OrderItem.query.filter_by(seller_id=user.id).join(Order).order_by(
        Order.created_at.desc()
    ).limit(10).all()
    
    # Get pending orders
    pending_orders = OrderItem.query.filter_by(
        seller_id=user.id, 
        status='pending'
    ).count()
    
    # Get products for the products section
    products = Product.query.filter_by(seller_id=user.id).order_by(
        Product.created_at.desc()
    ).all()
    
    # Calculate monthly sales
    thirty_days_ago = datetime.now() - timedelta(days=30)
    monthly_sales = db.session.query(func.sum(OrderItem.total_price * 50)).filter(  # Convert to PHP
        OrderItem.seller_id == user.id,
        OrderItem.created_at >= thirty_days_ago
    ).scalar() or 0
    
    # Get sales data for the last 12 months for the graph
    twelve_months_ago = datetime.now() - timedelta(days=365)
    
    # Get monthly sales data
    monthly_sales_data = db.session.query(
        func.date_trunc('month', Order.created_at).label('month'),
        func.sum(OrderItem.total_price * 50).label('total_sales'),  # Convert to PHP
        func.count(OrderItem.id).label('order_count')
    ).join(OrderItem).filter(
        OrderItem.seller_id == user.id,
        Order.created_at >= twelve_months_ago
    ).group_by(
        func.date_trunc('month', Order.created_at)
    ).order_by('month').all()
    
    # Get top selling products
    top_products = db.session.query(
        Product,
        func.sum(OrderItem.quantity).label('total_quantity'),
        func.sum(OrderItem.total_price * 50).label('total_revenue')
    ).join(OrderItem).filter(
        Product.seller_id == user.id,
        OrderItem.created_at >= twelve_months_ago
    ).group_by(Product.id).order_by(
        func.sum(OrderItem.quantity).desc()
    ).limit(5).all()
    
    # Get low stock products
    low_stock_products = Product.query.filter(
        Product.seller_id == user.id,
        Product.stock_quantity <= 5,
        Product.status == 'active'
    ).all()
    
    # Format data for the chart
    sales_labels = []
    sales_amounts = []
    sales_counts = []
    
    # Initialize with zero values for all months
    for i in range(12):
        month = (datetime.now() - timedelta(days=30 * (11 - i))).strftime('%b %Y')
        sales_labels.append(month)
        sales_amounts.append(0)
        sales_counts.append(0)
    
    # Fill in actual data
    for data in monthly_sales_data:
        month_str = data.month.strftime('%b %Y')
        if month_str in sales_labels:
            idx = sales_labels.index(month_str)
            sales_amounts[idx] = float(data.total_sales or 0)
            sales_counts[idx] = data.order_count
    
    # Base query
    query = Product.query.filter_by(seller_id=user.id)
    
    # Apply filters
    if search:
        query = query.filter(
            or_(
                Product.name.ilike(f'%{search}%'),
                Product.description.ilike(f'%{search}%'),
                Product.sku.ilike(f'%{search}%')
            )
        )
    
    if status:
        query = query.filter_by(status=status)
    
    # Paginate
    products_paginated = query.order_by(Product.created_at.desc()).paginate(
        page=page, per_page=12, error_out=False
    )
    
    return render_template('seller/dashboard.html',
                         total_products=total_products,
                         active_products=active_products,
                         orders=orders,
                         products=products,
                         pending_orders=pending_orders,
                         monthly_sales=monthly_sales,
                         low_stock_products=low_stock_products,
                         sales_labels=sales_labels,
                         sales_amounts=sales_amounts,
                         sales_counts=sales_counts,
                         top_products=top_products,
                         seller=user)

@seller_bp.route('/product/add', methods=['GET', 'POST'])
@role_required('seller')
def add_product():
    """Add new product"""
    user = get_current_user()
    
    if request.method == 'POST':
        # Get form data
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        category_id = request.form.get('category_id', type=int)
        price = request.form.get('price', type=float)
        stock_quantity = request.form.get('stock_quantity', type=int)
        sku = request.form.get('sku', '').strip()
        weight = request.form.get('weight', type=float)
        dimensions = request.form.get('dimensions', '').strip()
        brand = request.form.get('brand', '').strip()
        age_group = request.form.get('age_group', 'all_ages')
        pet_type = request.form.get('pet_type')
        
        # Validation
        errors = []
        
        if not name:
            errors.append('Product name is required.')
        
        if not category_id:
            errors.append('Category is required.')
        
        if not price or price <= 0:
            errors.append('Valid price is required.')
        
        if not stock_quantity or stock_quantity < 0:
            errors.append('Valid stock quantity is required.')
        
        if not pet_type:
            errors.append('Pet type is required.')
        
        # Check if SKU already exists
        if sku:
            existing_sku = Product.query.filter_by(sku=sku).first()
            if existing_sku:
                errors.append('SKU already exists.')
        
        if errors:
            for error in errors:
                flash(error, 'error')
            categories = Category.query.filter_by(status='active').all()
            return render_template('seller/add_product.html', categories=categories)
        
        try:
            # Create product
            product = Product(
                seller_id=user.id,
                category_id=category_id,
                name=name,
                description=description,
                price=price,
                stock_quantity=stock_quantity,
                sku=sku or None,
                weight=weight,
                dimensions=dimensions,
                brand=brand,
                age_group=age_group,
                pet_type=pet_type,
                status='active'
            )
            
            db.session.add(product)
            db.session.flush()  # Get product ID
            
            # Handle image uploads
            uploaded_files = request.files.getlist('images')
            if uploaded_files and uploaded_files[0].filename:
                from config.config import Config
                upload_folder = os.path.join(Config.UPLOAD_FOLDER, 'products')
                
                for i, file in enumerate(uploaded_files[:5]):  # Max 5 images
                    if file and file.filename:
                        # Generate unique filename
                        filename = f"{product.id}_{uuid.uuid4().hex[:8]}_{secure_filename(file.filename)}"
                        file_path = os.path.join(upload_folder, filename)
                        
                        file.save(file_path)
                        
                        # Create product image record
                        product_image = ProductImage(
                            product_id=product.id,
                            image_url=f'uploads/products/{filename}',
                            is_primary=(i == 0),  # First image is primary
                            alt_text=f"{name} image"
                        )
                        db.session.add(product_image)
            
            db.session.commit()
            flash('Product added successfully!', 'success')
            return redirect(url_for('seller.products'))
            
        except Exception as e:
            db.session.rollback()
            flash('Failed to add product. Please try again.', 'error')
    
    categories = Category.query.filter_by(status='active').all()
    return render_template('seller/add_product.html', categories=categories)

@seller_bp.route('/product/edit/<int:product_id>', methods=['GET', 'POST'])
@role_required('seller')
def edit_product(product_id):
    """Edit product"""
    user = get_current_user()
    product = Product.query.filter_by(
        id=product_id,
        seller_id=user.id
    ).first_or_404()
    
    if request.method == 'POST':
        # Get form data
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        category_id = request.form.get('category_id', type=int)
        price = request.form.get('price', type=float)
        stock_quantity = request.form.get('stock_quantity', type=int)
        sku = request.form.get('sku', '').strip()
        weight = request.form.get('weight', type=float)
        dimensions = request.form.get('dimensions', '').strip()
        brand = request.form.get('brand', '').strip()
        age_group = request.form.get('age_group', 'all_ages')
        pet_type = request.form.get('pet_type')
        status = request.form.get('status', 'active')
        
        # Validation
        errors = []
        
        if not name:
            errors.append('Product name is required.')
        
        if not category_id:
            errors.append('Category is required.')
        
        if not price or price <= 0:
            errors.append('Valid price is required.')
        
        if not stock_quantity or stock_quantity < 0:
            errors.append('Valid stock quantity is required.')
        
        if not pet_type:
            errors.append('Pet type is required.')
        
        # Check if SKU already exists (exclude current product)
        if sku:
            existing_sku = Product.query.filter(
                Product.sku == sku,
                Product.id != product_id
            ).first()
            if existing_sku:
                errors.append('SKU already exists.')
        
        if errors:
            for error in errors:
                flash(error, 'error')
            categories = Category.query.filter_by(status='active').all()
            return render_template('seller/edit_product.html', 
                                 product=product, categories=categories)
        
        try:
            # Update product
            product.name = name
            product.description = description
            product.category_id = category_id
            product.price = price
            product.stock_quantity = stock_quantity
            product.sku = sku or None
            product.weight = weight
            product.dimensions = dimensions
            product.brand = brand
            product.age_group = age_group
            product.pet_type = pet_type
            product.status = status
            
            # Handle new image uploads
            uploaded_files = request.files.getlist('new_images')
            if uploaded_files and uploaded_files[0].filename:
                from config.config import Config
                import os
                from werkzeug.utils import secure_filename
                
                upload_folder = os.path.join(Config.UPLOAD_FOLDER, 'products')
                os.makedirs(upload_folder, exist_ok=True)
                
                for file in uploaded_files[:5]:  # Max 5 additional images
                    if file.filename == '':
                        continue
                    
                    filename = secure_filename(file.filename)
                    unique_filename = f"{uuid.uuid4().hex}_{filename}"
                    filepath = os.path.join(upload_folder, unique_filename)
                    
                    try:
                        file.save(filepath)
                        # Create new product image record
                        product_image = ProductImage(
                            product_id=product.id,
                            image_url=os.path.join('uploads/products', unique_filename).replace('\\', '/')
                        )
                        db.session.add(product_image)
                    except Exception as e:
                        flash(f'Failed to upload image: {str(e)}', 'error')
                        continue
            
            db.session.commit()
            flash('Product updated successfully!', 'success')
            return redirect(url_for('seller.products'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Failed to update product: {str(e)}', 'error')
    
    categories = Category.query.filter_by(status='active').all()
    return render_template('seller/edit_product.html', 
                         product=product, categories=categories)

@seller_bp.route('/product/delete/<int:product_id>', methods=['POST'])
@role_required('seller')
def delete_product(product_id):
    """Delete product"""
    user = get_current_user()
    product = Product.query.filter_by(
        id=product_id,
        seller_id=user.id
    ).first_or_404()
    
    # Check if product has orders
    has_orders = OrderItem.query.filter_by(product_id=product_id).first()
    
    try:
        if has_orders:
            # Soft delete - just mark as inactive
            product.status = 'inactive'
            flash('Product marked as inactive (has existing orders).', 'warning')
        else:
            # Hard delete
            db.session.delete(product)
            flash('Product deleted successfully!', 'success')
        
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        flash('Failed to delete product.', 'error')
    
@role_required('seller')
def orders():
    """View all orders for the seller with real-time updates"""
    user = get_current_user()
    status = request.args.get('status')
    
    # Base query
    query = db.session.query(
        Order,
        User.first_name.label('customer_first_name'),
        User.last_name.label('customer_last_name'),
        User.phone.label('customer_phone')
    ).join(
        User, Order.user_id == User.id
    ).filter(
        Order.seller_id == user.id
    )
    
    if status and status in ['pending', 'confirmed', 'shipped', 'delivered', 'cancelled']:
        query = query.filter(Order.status == status)
    
    # Get pagination parameters
    page = request.args.get('page', 1, type=int)
    per_page = 15
    
    # Execute paginated query
    orders_paginated = query.order_by(
        Order.created_at.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)
    
    # Get counts for status tabs
    status_counts = db.session.query(
        Order.status,
        func.count(Order.id)
    ).filter(
        Order.seller_id == user.id
    ).group_by(Order.status).all()
    
    status_counts = {status: count for status, count in status_counts}
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        # Return JSON for AJAX requests
        orders_data = [{
            'id': order.id,
            'order_number': order.order_number,
            'status': order.status,
            'status_display': order.status.replace('_', ' ').title(),
            'total_amount': float(order.total_amount) if order.total_amount else 0,
            'created_at': order.created_at.isoformat(),
            'updated_at': order.updated_at.isoformat() if order.updated_at else None,
            'customer_name': f"{customer_first_name} {customer_last_name}",
            'customer_phone': customer_phone,
            'item_count': len(order.items)
        } for order, customer_first_name, customer_last_name, customer_phone in orders_paginated.items]
        
        return jsonify({
            'success': True,
            'orders': orders_data,
            'has_next': orders_paginated.has_next,
            'has_prev': orders_paginated.has_prev,
            'page': orders_paginated.page,
            'pages': orders_paginated.pages,
            'per_page': orders_paginated.per_page,
            'total': orders_paginated.total,
            'status_counts': status_counts
        })
    
    return render_template('seller/orders.html', 
                         orders=orders_paginated.items,
                         pagination=orders_paginated,
                         status_counts=status_counts,
                         current_status=status,
                         current_page=page)

@seller_bp.route('/order/<int:order_id>/update-status', methods=['POST'])
@role_required('seller')
def update_order_status(order_id):
    """Update order status with real-time notifications"""
    user = get_current_user()
    order = Order.query.get_or_404(order_id)
    
    # Verify the order belongs to this seller
    if order.seller_id != user.id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    status = request.form.get('status')
    if not status or status not in ['pending', 'confirmed', 'ready_for_pickup', 'shipped', 'delivered', 'cancelled']:
        return jsonify({'success': False, 'message': 'Invalid status'}), 400
    
    try:
        previous_status = order.status
        order.status = status
        order.updated_at = datetime.utcnow()
        
        # If order is confirmed or ready for pickup, notify available riders
        if (status in ['confirmed', 'ready_for_pickup']) and (previous_status not in ['confirmed', 'ready_for_pickup']):
            # Get order details for notification
            order_data = {
                'id': order.id,
                'order_number': order.order_number,
                'total_amount': float(order.total_amount) if order.total_amount else 0,
                'pickup_address': {
                    'name': user.business_name or 'Store',
                    'address': f"{user.address or 'Pickup Location'}, {user.city or ''}, {user.province or ''}",
                    'contact': user.phone or ''
                },
                'delivery_address': {
                    'name': order.shipping_address.recipient_name,
                    'address': f"{order.shipping_address.street_address}, {order.shipping_address.city}, {order.shipping_address.province}",
                    'contact': order.shipping_address.contact_number
                },
                'items': [{
                    'name': item.product.name,
                    'quantity': item.quantity,
                    'price': float(item.price) if item.price else 0
                } for item in order.items],
                'items_count': len(order.items),
                'created_at': order.created_at.isoformat() if order.created_at else datetime.utcnow().isoformat(),
                'status': status  # Include status in the notification
            }
            
            # Notify all available riders
            from app.services.rider_websocket import notify_riders_new_order
            try:
                notify_riders_new_order(order_data)
                current_app.logger.info(f'Notified riders about order {order.id} status: {status}')
            except Exception as e:
                current_app.logger.error(f'Error notifying riders: {str(e)}')
        
        db.session.commit()
        
        # Create notification for customer
        notification = Notification(
            user_id=order.user_id,
            title=f'Order #{order.id} Updated',
            message=f'Your order status has been updated to: {status.replace("_", " ").title()}',
            notification_type='order_status_update',
            reference_id=order.id
        )
        db.session.add(notification)
        db.session.commit()
        
        # Emit socket event for real-time update
        socketio.emit('order_status_updated', {
            'order_id': order.id,
            'status': status,
            'status_display': status.replace("_", " ").title(),
            'updated_at': order.updated_at.isoformat()
        }, room=f'seller_{user.id}')
        
        return jsonify({
            'success': True, 
            'message': 'Order status updated successfully',
            'status': status,
            'status_display': status.replace("_", " ").title()
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Error updating order status: {str(e)}')
        return jsonify({'success': False, 'message': 'Failed to update order status'}), 500

@seller_bp.route('/update-profile', methods=['POST'])
@role_required('seller')
def update_profile():
    """Update seller profile"""
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
        return redirect(url_for('seller.profile'))
    
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
    
    return redirect(url_for('seller.profile'))

@seller_bp.route('/analytics')
@role_required('seller')
def analytics():
    """Seller analytics"""
    user = get_current_user()
    
    # Get date range from query params
    days = request.args.get('days', 30, type=int)
    start_date = datetime.now() - timedelta(days=days)
    
    # Sales analytics
    sales_data = db.session.query(
        func.date(OrderItem.created_at).label('date'),
        func.sum(OrderItem.total_price).label('total_sales'),
        func.count(OrderItem.id).label('order_count')
    ).filter(
        OrderItem.seller_id == user.id,
        OrderItem.created_at >= start_date
    ).group_by(func.date(OrderItem.created_at)).all()
    
    # Top products
    top_products = db.session.query(
        Product.name,
        func.sum(OrderItem.quantity).label('total_sold'),
        func.sum(OrderItem.total_price).label('total_revenue')
    ).join(OrderItem).filter(
        Product.seller_id == user.id,
        OrderItem.created_at >= start_date
    ).group_by(Product.id, Product.name).order_by(
        func.sum(OrderItem.total_price).desc()
    ).limit(10).all()
    
    # Order status distribution
    order_status = db.session.query(
        OrderItem.status,
        func.count(OrderItem.id).label('count')
    ).filter(
        OrderItem.seller_id == user.id,
        OrderItem.created_at >= start_date
    ).group_by(OrderItem.status).all()
    
    return render_template('seller/analytics.html',
                         sales_data=sales_data,
                         top_products=top_products,
                         order_status=order_status,
                         days=days)