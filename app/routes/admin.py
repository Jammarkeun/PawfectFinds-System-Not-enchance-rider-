from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from sqlalchemy import and_, or_, func, desc
from app import db
from app.models.models import (User, Product, Order, OrderItem, SellerApplication, 
                               Review, Category, Notification, SystemLog)
from app.utils.auth import role_required, get_current_user
from datetime import datetime, timedelta

admin_bp = Blueprint('admin', __name__)

@admin_bp.route('/dashboard')
@role_required('admin')
def dashboard():
    """Admin dashboard with system overview"""
    # Get system statistics
    total_users = User.query.count()
    total_customers = User.query.filter_by(role='customer').count()
    total_sellers = User.query.filter_by(role='seller').count()
    total_riders = User.query.filter_by(role='rider').count()
    
    total_products = Product.query.count()
    active_products = Product.query.filter_by(status='active').count()
    
    total_orders = Order.query.count()
    pending_orders = Order.query.filter_by(status='pending').count()
    
    # Pending seller applications
    pending_applications = SellerApplication.query.filter_by(status='pending').count()
    
    # Recent activities
    recent_orders = Order.query.order_by(desc(Order.created_at)).limit(5).all()
    recent_users = User.query.filter(User.role != 'admin').order_by(desc(User.created_at)).limit(5).all()
    recent_reviews = Review.query.filter_by(status='pending').order_by(desc(Review.created_at)).limit(5).all()
    
    # Sales analytics (last 30 days)
    thirty_days_ago = datetime.now() - timedelta(days=30)
    monthly_sales = db.session.query(func.sum(Order.total_amount)).filter(
        Order.created_at >= thirty_days_ago,
        Order.status != 'cancelled'
    ).scalar() or 0
    
    # Daily sales data for chart (last 7 days)
    sales_data = []
    for i in range(7):
        date = datetime.now() - timedelta(days=i)
        daily_sales = db.session.query(func.sum(Order.total_amount)).filter(
            func.date(Order.created_at) == date.date(),
            Order.status != 'cancelled'
        ).scalar() or 0
        sales_data.append({
            'date': date.strftime('%Y-%m-%d'),
            'sales': float(daily_sales)
        })
    
    return render_template('admin/dashboard.html',
                         total_users=total_users,
                         total_customers=total_customers,
                         total_sellers=total_sellers,
                         total_riders=total_riders,
                         total_products=total_products,
                         active_products=active_products,
                         total_orders=total_orders,
                         pending_orders=pending_orders,
                         pending_applications=pending_applications,
                         recent_orders=recent_orders,
                         recent_users=recent_users,
                         recent_reviews=recent_reviews,
                         monthly_sales=monthly_sales,
                         sales_data=sales_data)

@admin_bp.route('/seller-applications')
@role_required('admin')
def seller_applications():
    """View and manage seller applications"""
    page = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', '')
    
    query = SellerApplication.query
    
    if status_filter:
        query = query.filter_by(status=status_filter)
    
    applications = query.order_by(desc(SellerApplication.created_at)).paginate(
        page=page, per_page=10, error_out=False
    )
    
    return render_template('admin/seller_applications.html',
                         applications=applications.items,
                         pagination=applications,
                         status_filter=status_filter)

@admin_bp.route('/approve-seller/<int:application_id>', methods=['POST'])
@role_required('admin')
def approve_seller(application_id):
    """Approve a seller application"""
    admin = get_current_user()
    application = SellerApplication.query.get_or_404(application_id)
    
    try:
        # Update application status
        application.status = 'approved'
        application.reviewed_by = admin.id
        application.reviewed_at = datetime.now()
        
        # Update user role to seller
        user = User.query.get(application.user_id)
        user.role = 'seller'
        
        # Create notification for user
        notification = Notification(
            user_id=user.id,
            type='seller_application',
            title='Seller Application Approved',
            message='Congratulations! Your seller application has been approved. You can now start selling on Pawfect Finds.',
            related_id=application.id
        )
        
        db.session.add(notification)
        db.session.commit()
        
        flash('Seller application approved successfully!', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash('Failed to approve seller application.', 'error')
    
    return redirect(url_for('admin.seller_applications'))

@admin_bp.route('/reject-seller/<int:application_id>', methods=['POST'])
@role_required('admin')
def reject_seller(application_id):
    """Reject a seller application"""
    admin = get_current_user()
    application = SellerApplication.query.get_or_404(application_id)
    admin_notes = request.form.get('admin_notes', '')
    
    try:
        # Update application status
        application.status = 'rejected'
        application.reviewed_by = admin.id
        application.reviewed_at = datetime.now()
        application.admin_notes = admin_notes
        
        # Create notification for user
        notification = Notification(
            user_id=application.user_id,
            type='seller_application',
            title='Seller Application Rejected',
            message=f'Your seller application has been rejected. {admin_notes if admin_notes else "Please contact support for more information."}',
            related_id=application.id
        )
        
        db.session.add(notification)
        db.session.commit()
        
        flash('Seller application rejected.', 'info')
        
    except Exception as e:
        db.session.rollback()
        flash('Failed to reject seller application.', 'error')
    
    return redirect(url_for('admin.seller_applications'))

@admin_bp.route('/users')
@role_required('admin')
def users():
    """Manage all users"""
    page = request.args.get('page', 1, type=int)
    role_filter = request.args.get('role', '')
    status_filter = request.args.get('status', '')
    search = request.args.get('search', '')
    
    query = User.query.filter(User.role != 'admin')
    
    if role_filter:
        query = query.filter_by(role=role_filter)
    
    if status_filter:
        query = query.filter_by(status=status_filter)
    
    if search:
        query = query.filter(
            or_(
                User.username.ilike(f'%{search}%'),
                User.email.ilike(f'%{search}%'),
                User.first_name.ilike(f'%{search}%'),
                User.last_name.ilike(f'%{search}%')
            )
        )
    
    users_paginated = query.order_by(desc(User.created_at)).paginate(
        page=page, per_page=20, error_out=False
    )
    
    return render_template('admin/users.html',
                         users=users_paginated.items,
                         pagination=users_paginated,
                         role_filter=role_filter,
                         status_filter=status_filter,
                         search=search)

@admin_bp.route('/user/<int:user_id>')
@role_required('admin')
def user_detail(user_id):
    """View user details"""
    user = User.query.get_or_404(user_id)
    
    # Get user statistics
    if user.role == 'customer':
        order_count = Order.query.filter_by(user_id=user.id).count()
        total_spent = db.session.query(func.sum(Order.total_amount)).filter_by(user_id=user.id).scalar() or 0
        stats = {'orders': order_count, 'total_spent': total_spent}
    elif user.role == 'seller':
        product_count = Product.query.filter_by(seller_id=user.id).count()
        total_sales = db.session.query(func.sum(OrderItem.total_price)).filter_by(seller_id=user.id).scalar() or 0
        stats = {'products': product_count, 'total_sales': total_sales}
    else:
        stats = {}
    
    return render_template('admin/user_detail.html', user=user, stats=stats)

@admin_bp.route('/update-user-status', methods=['POST'])
@role_required('admin')
def update_user_status():
    """Update user status"""
    user_id = request.form.get('user_id', type=int)
    new_status = request.form.get('status')
    
    if not user_id or not new_status:
        flash('Invalid data provided.', 'error')
        return redirect(request.referrer)
    
    user = User.query.get_or_404(user_id)
    
    if user.role == 'admin':
        flash('Cannot modify admin user status.', 'error')
        return redirect(request.referrer)
    
    try:
        user.status = new_status
        db.session.commit()
        
        flash(f'User status updated to {new_status}.', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash('Failed to update user status.', 'error')
    
    return redirect(request.referrer)

@admin_bp.route('/products')
@role_required('admin')
def products():
    """Manage all products"""
    page = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', '')
    search = request.args.get('search', '')
    
    query = Product.query
    
    if status_filter:
        query = query.filter_by(status=status_filter)
    
    if search:
        query = query.filter(
            or_(
                Product.name.ilike(f'%{search}%'),
                Product.description.ilike(f'%{search}%'),
                Product.sku.ilike(f'%{search}%')
            )
        )
    
    products_paginated = query.order_by(desc(Product.created_at)).paginate(
        page=page, per_page=20, error_out=False
    )
    
    return render_template('admin/products.html',
                         products=products_paginated.items,
                         pagination=products_paginated,
                         status_filter=status_filter,
                         search=search)

@admin_bp.route('/orders')
@role_required('admin')
def orders():
    """View all orders"""
    page = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', '')
    
    query = Order.query
    
    if status_filter:
        query = query.filter_by(status=status_filter)
    
    orders_paginated = query.order_by(desc(Order.created_at)).paginate(
        page=page, per_page=20, error_out=False
    )
    
    return render_template('admin/orders.html',
                         orders=orders_paginated.items,
                         pagination=orders_paginated,
                         status_filter=status_filter)

@admin_bp.route('/reviews')
@role_required('admin')
def reviews():
    """Moderate product reviews"""
    page = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', 'pending')
    
    query = Review.query
    
    if status_filter:
        query = query.filter_by(status=status_filter)
    
    reviews_paginated = query.order_by(desc(Review.created_at)).paginate(
        page=page, per_page=15, error_out=False
    )
    
    return render_template('admin/reviews.html',
                         reviews=reviews_paginated.items,
                         pagination=reviews_paginated,
                         status_filter=status_filter)

@admin_bp.route('/approve-review/<int:review_id>', methods=['POST'])
@role_required('admin')
def approve_review(review_id):
    """Approve a product review"""
    review = Review.query.get_or_404(review_id)
    
    try:
        review.status = 'approved'
        db.session.commit()
        flash('Review approved successfully!', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash('Failed to approve review.', 'error')
    
    return redirect(url_for('admin.reviews'))

@admin_bp.route('/reject-review/<int:review_id>', methods=['POST'])
@role_required('admin')
def reject_review(review_id):
    """Reject a product review"""
    review = Review.query.get_or_404(review_id)
    
    try:
        review.status = 'rejected'
        db.session.commit()
        flash('Review rejected.', 'info')
        
    except Exception as e:
        db.session.rollback()
        flash('Failed to reject review.', 'error')
    
    return redirect(url_for('admin.reviews'))

@admin_bp.route('/analytics')
@role_required('admin')
def analytics():
    """System analytics and reporting"""
    days = request.args.get('days', 30, type=int)
    start_date = datetime.now() - timedelta(days=days)
    
    # Sales analytics
    sales_data = db.session.query(
        func.date(Order.created_at).label('date'),
        func.sum(Order.total_amount).label('total_sales'),
        func.count(Order.id).label('order_count')
    ).filter(
        Order.created_at >= start_date,
        Order.status != 'cancelled'
    ).group_by(func.date(Order.created_at)).all()
    
    # Top selling products
    top_products = db.session.query(
        Product.name,
        func.sum(OrderItem.quantity).label('total_sold'),
        func.sum(OrderItem.total_price).label('total_revenue')
    ).join(OrderItem).filter(
        OrderItem.created_at >= start_date
    ).group_by(Product.id, Product.name).order_by(
        func.sum(OrderItem.total_price).desc()
    ).limit(10).all()
    
    # User registration trends
    user_data = db.session.query(
        func.date(User.created_at).label('date'),
        func.count(User.id).label('new_users')
    ).filter(
        User.created_at >= start_date,
        User.role != 'admin'
    ).group_by(func.date(User.created_at)).all()
    
    return render_template('admin/analytics.html',
                         sales_data=sales_data,
                         top_products=top_products,
                         user_data=user_data,
                         days=days)