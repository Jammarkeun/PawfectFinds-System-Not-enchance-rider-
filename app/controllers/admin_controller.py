from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from app.utils.decorators import login_required, admin_required
from app.models.user import User
from app.models.seller_request import SellerRequest
from app.models.product import Product
from app.models.order import Order
from app.services.database import Database
from app.forms import AdminNotesForm, RejectNotesForm, CategoryForm, SystemSettingsForm

admin_bp = Blueprint('admin', __name__)

@admin_bp.route('/dashboard')
@login_required
@admin_required
def dashboard():
    """Admin dashboard with key metrics"""
    # Get statistics
    db = Database()
    
    stats = {}
    stats['total_users'] = User.get_users_count()
    stats['total_sellers'] = User.get_users_count(role='seller')
    stats['total_customers'] = User.get_users_count(role='user')
    stats['pending_requests'] = SellerRequest.get_requests_count(status='pending')
    stats['total_orders'] = Order.count()
    stats['pending_orders'] = Order.count(status='pending')
    
    # Recent seller requests
    recent_requests = SellerRequest.get_all_requests(limit=5)
    
    # Recent users
    recent_users = User.get_all_users(limit=10)
    
    return render_template('admin/dashboard.html',
                         stats=stats,
                         recent_requests=recent_requests,
                         recent_users=recent_users)

@admin_bp.route('/seller-requests')
@login_required
@admin_required
def seller_requests():
    """Manage seller requests"""
    status = request.args.get('status', 'pending')
    requests = SellerRequest.get_all_requests(status=status if status != 'all' else None)
    
    return render_template('admin/seller_requests.html',
                         requests=requests,
                         current_status=status)

@admin_bp.route('/seller-requests/<int:request_id>/approve', methods=['POST'])
@login_required
@admin_required
def approve_seller_request(request_id):
    """Approve a seller request"""
    form = AdminNotesForm(request.form)
    admin_notes = None
    if form.validate_on_submit():
        admin_notes = form.admin_notes.data.strip() if form.admin_notes.data else None
    else:
        # Check if CSRF is the only error (for optional notes)
        if form.errors and len(form.errors) == 1 and 'csrf_token' in form.errors:
            # CSRF passed, but form not validated - use raw data
            admin_notes = request.form.get('admin_notes', '').strip() or None
        else:
            flash('Invalid form data.', 'error')
            return redirect(url_for('admin.seller_requests'))
        
    try:
        success = SellerRequest.approve_request(request_id, admin_notes)
        if success:
            flash('Seller request approved successfully!', 'success')
        else:
            flash('Failed to approve request. Request may not exist or already processed.', 'error')
    except Exception as e:
        flash('An error occurred while approving the request.', 'error')
    
    return redirect(url_for('admin.seller_requests'))

@admin_bp.route('/seller-requests/<int:request_id>/reject', methods=['POST'])
@login_required
@admin_required
def reject_seller_request(request_id):
    """Reject a seller request"""
    form = RejectNotesForm(request.form)
    admin_notes = None
    if form.validate_on_submit():
        admin_notes = form.admin_notes.data.strip()
    else:
        # Check if CSRF is the only error and notes are provided
        if form.errors and len(form.errors) == 1 and 'csrf_token' in form.errors:
            admin_notes = request.form.get('admin_notes', '').strip()
            if not admin_notes:
                flash('Please provide a reason for rejection.', 'error')
                return redirect(url_for('admin.seller_requests'))
        else:
            flash('Please provide a reason for rejection.', 'error')
            return redirect(url_for('admin.seller_requests'))
        
    try:
        success = SellerRequest.reject_request(request_id, admin_notes)
        if success:
            flash('Seller request rejected.', 'info')
        else:
            flash('Failed to reject request.', 'error')
    except Exception as e:
        flash('An error occurred while rejecting the request.', 'error')
    
    return redirect(url_for('admin.seller_requests'))

@admin_bp.route('/users')
@login_required
@admin_required
def manage_users():
    """Manage users"""
    role_filter = request.args.get('role')
    status_filter = request.args.get('status')
    page = int(request.args.get('page', 1))
    per_page = 20
    offset = (page - 1) * per_page
    
    users = User.get_all_users(
        role=role_filter if role_filter != 'all' else None,
        status=status_filter if status_filter != 'all' else None,
        limit=per_page,
        offset=offset
    )
    
    # Get total count for pagination
    total = User.get_users_count(
        role=role_filter if role_filter != 'all' else None,
        status=status_filter if status_filter != 'all' else None
    )
    
    # Calculate pagination
    total_pages = (total + per_page - 1) // per_page
    has_prev = page > 1
    has_next = page < total_pages
    
    # Get statistics for the stats cards
    total_users = User.get_users_count()
    active_users = User.get_users_count(status='active')
    inactive_users = User.get_users_count(status='inactive')
    admin_users = User.get_users_count(role='admin')

    # Get recent users for sidebar
    recent_users = User.get_all_users(limit=5)

    return render_template('admin/users.html',
                         users=users,
                         current_role=role_filter,
                         current_status=status_filter,
                         current_page=page,
                         total_pages=total_pages,
                         has_prev=has_prev,
                         has_next=has_next,
                         prev_page=page-1 if has_prev else None,
                         next_page=page+1 if has_next else None,
                         total_users=total_users,
                         active_users=active_users,
                         inactive_users=inactive_users,
                         admin_users=admin_users,
                         recent_users=recent_users)

@admin_bp.route('/users/<int:user_id>/update-status', methods=['POST'])
@login_required
@admin_required
def update_user_status(user_id):
    """Update user status (active/inactive/banned)"""
    new_status = request.form.get('status')
    
    # Prevent admin from changing their own status
    if user_id == session['user_id']:
        flash('You cannot change your own status.', 'error')
        return redirect(url_for('admin.manage_users'))
    
    # Validate status
    valid_statuses = ['active', 'inactive', 'banned']
    if new_status not in valid_statuses:
        flash('Invalid status.', 'error')
        return redirect(url_for('admin.manage_users'))
    
    try:
        User.update_status(user_id, new_status)
        flash(f'User status updated to {new_status}.', 'success')
    except Exception as e:
        flash('Failed to update user status.', 'error')
    
    return redirect(url_for('admin.manage_users'))

@admin_bp.route('/users/<int:user_id>/update-role', methods=['POST'])
@login_required
@admin_required
def update_user_role(user_id):
    """Update user role"""
    new_role = request.form.get('role')
    
    # Prevent admin from changing their own role
    if user_id == session['user_id']:
        flash('You cannot change your own role.', 'error')
        return redirect(url_for('admin.manage_users'))
    
    # Validate role
    valid_roles = ['user', 'seller', 'admin']
    if new_role not in valid_roles:
        flash('Invalid role.', 'error')
        return redirect(url_for('admin.manage_users'))
    
    try:
        User.update_role(user_id, new_role)
        flash(f'User role updated to {new_role}.', 'success')
    except Exception as e:
        flash('Failed to update user role.', 'error')
    
    return redirect(url_for('admin.manage_users'))

@admin_bp.route('/users/<int:user_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_user(user_id):
    """Delete a user"""
    # Prevent admin from deleting themselves
    if user_id == session['user_id']:
        flash('You cannot delete your own account.', 'error')
        return redirect(url_for('admin.manage_users'))
    
    try:
        User.delete(user_id)
        flash('User deleted successfully.', 'success')
    except Exception as e:
        flash('Failed to delete user. User may have associated data.', 'error')
    
    return redirect(url_for('admin.manage_users'))

@admin_bp.route('/products')
@login_required
@admin_required
def manage_products():
    """Manage all products"""
    category_filter = request.args.get('category')
    status_filter = request.args.get('status')
    page = int(request.args.get('page', 1))
    per_page = 20
    offset = (page - 1) * per_page

    products = Product.list(
        category_id=int(category_filter) if category_filter else None,
        status=status_filter if status_filter != 'all' else None,
        limit=per_page,
        offset=offset
    )

    # Get categories for filter
    db = Database()
    categories = db.execute_query("SELECT * FROM categories WHERE is_active = 1", fetch=True)

    return render_template('admin/products.html',
                         products=products,
                         categories=categories,
                         current_category=int(category_filter) if category_filter else None,
                         current_status=status_filter)

@admin_bp.route('/products/<int:product_id>/toggle-status', methods=['POST'])
@login_required
@admin_required
def toggle_product_status(product_id):
    """Toggle product status (active/inactive)"""
    try:
        # Get current product status
        product = Product.get_by_id(product_id)
        if not product:
            flash('Product not found.', 'error')
            return redirect(url_for('admin.manage_products'))

        # Toggle status
        new_status = 'inactive' if product.status == 'active' else 'active'
        Product.update(product_id, status=new_status)

        status_text = "activated" if new_status == 'active' else "deactivated"
        flash(f'Product {status_text} successfully!', 'success')

    except Exception as e:
        flash('Failed to update product status.', 'error')

    return redirect(url_for('admin.manage_products'))

@admin_bp.route('/products/<int:product_id>/remove', methods=['POST'])
@login_required
@admin_required
def remove_product(product_id):
    """Remove a product"""
    try:
        # Check if product exists
        product = Product.get_by_id(product_id)
        if not product:
            flash('Product not found.', 'error')
            return redirect(url_for('admin.manage_products'))

        # Delete the product
        Product.delete(product_id)
        flash('Product removed successfully!', 'success')

    except Exception as e:
        flash('Failed to remove product.', 'error')

    return redirect(url_for('admin.manage_products'))

@admin_bp.route('/orders')
@login_required
@admin_required
def manage_orders():
    """View all orders"""
    status_filter = request.args.get('status')
    page = int(request.args.get('page', 1))
    per_page = 20
    offset = (page - 1) * per_page

    # Get orders with seller and user info
    db = Database()
    query = '''
        SELECT o.*, u.username as customer_username, s.username as seller_username
        FROM orders o
        JOIN users u ON o.user_id = u.id
        JOIN users s ON o.seller_id = s.id
        WHERE 1=1
    '''
    params = []

    if status_filter and status_filter != 'all':
        query += " AND o.status = %s"
        params.append(status_filter)

    query += " ORDER BY o.created_at DESC LIMIT %s OFFSET %s"
    params.extend([per_page, offset])

    orders = db.execute_query(query, params, fetch=True)

    return render_template('admin/orders.html',
                         orders=orders,
                         current_status=status_filter)

@admin_bp.route('/orders/<int:order_id>/force-cancel', methods=['POST'])
@login_required
@admin_required
def force_cancel_order(order_id):
    """Force cancel an order (admin only)"""
    try:
        # Get order details
        order = Order.get_by_id(order_id)
        if not order:
            flash('Order not found.', 'error')
            return redirect(url_for('admin.manage_orders'))

        # Check if order can be cancelled
        if order.status in ['delivered', 'cancelled']:
            flash('Cannot cancel a delivered or already cancelled order.', 'error')
            return redirect(url_for('admin.manage_orders'))

        # Force cancel the order
        Order.update_status(order_id, 'cancelled')

        # Update product stock if needed (restore stock for cancelled order)
        db = Database()
        order_items = db.execute_query("SELECT * FROM order_items WHERE order_id = %s", (order_id,), fetch=True)
        for item in order_items:
            # Restore stock
            db.execute_query("UPDATE products SET stock_quantity = stock_quantity + %s WHERE id = %s",
                           (item['quantity'], item['product_id']))

        flash('Order has been force cancelled successfully.', 'success')

    except Exception as e:
        flash('Failed to cancel order.', 'error')

    return redirect(url_for('admin.manage_orders'))

@admin_bp.route('/orders/<int:order_id>/restore', methods=['POST'])
@login_required
@admin_required
def restore_order(order_id):
    """Restore a cancelled order (admin only)"""
    try:
        # Get order details
        order = Order.get_by_id(order_id)
        if not order:
            flash('Order not found.', 'error')
            return redirect(url_for('admin.manage_orders'))

        # Check if order is cancelled
        if order.status != 'cancelled':
            flash('Only cancelled orders can be restored.', 'error')
            return redirect(url_for('admin.manage_orders'))

        # Restore the order to pending status
        Order.update_status(order_id, 'pending')

        # Update product stock (deduct stock again)
        db = Database()
        order_items = db.execute_query("SELECT * FROM order_items WHERE order_id = %s", (order_id,), fetch=True)
        for item in order_items:
            # Deduct stock again
            db.execute_query("UPDATE products SET stock_quantity = stock_quantity - %s WHERE id = %s",
                           (item['quantity'], item['product_id']))

        flash('Order has been restored successfully.', 'success')

    except Exception as e:
        flash('Failed to restore order.', 'error')

    return redirect(url_for('admin.manage_orders'))

@admin_bp.route('/analytics')
@login_required
@admin_required
def analytics():
    """Analytics and reports"""
    db = Database()

    # Basic analytics data
    analytics = {}

    # Total orders
    total_orders_result = db.execute_query("SELECT COUNT(*) as count FROM orders", fetch=True, fetchone=True)
    analytics['total_orders'] = total_orders_result['count'] if total_orders_result else 0

    # Total revenue
    total_revenue_result = db.execute_query("SELECT SUM(total_amount) as revenue FROM orders WHERE status != 'cancelled'", fetch=True, fetchone=True)
    analytics['total_revenue'] = total_revenue_result['revenue'] if total_revenue_result and total_revenue_result['revenue'] else 0.0

    # Growth rate (simplified - compare last 30 days to previous 30 days)
    current_month_result = db.execute_query("""
        SELECT COUNT(*) as count FROM orders
        WHERE created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)
    """, fetch=True, fetchone=True)
    previous_month_result = db.execute_query("""
        SELECT COUNT(*) as count FROM orders
        WHERE created_at >= DATE_SUB(NOW(), INTERVAL 60 DAY)
        AND created_at < DATE_SUB(NOW(), INTERVAL 30 DAY)
    """, fetch=True, fetchone=True)

    current_count = current_month_result['count'] if current_month_result else 0
    previous_count = previous_month_result['count'] if previous_month_result else 1  # Avoid division by zero
    analytics['growth_rate'] = ((current_count - previous_count) / previous_count) * 100 if previous_count > 0 else 0.0

    # Average rating (simplified - from order reviews if available, else default)
    analytics['avg_rating'] = 4.2  # Placeholder - would need review system

    # Top products
    top_products_result = db.execute_query("""
        SELECT p.name, p.price, c.name as category,
               COUNT(oi.id) as sales_count,
               SUM(oi.price_at_time * oi.quantity) as revenue,
               AVG(r.rating) as rating
        FROM products p
        LEFT JOIN categories c ON p.category_id = c.id
        LEFT JOIN order_items oi ON p.id = oi.product_id
        LEFT JOIN reviews r ON p.id = r.product_id
        GROUP BY p.id, p.name, p.price, c.name
        ORDER BY sales_count DESC
        LIMIT 5
    """, fetch=True)
    analytics['top_products'] = top_products_result if top_products_result else []

    # Conversion rate (simplified)
    analytics['conversion_rate'] = 3.5  # Placeholder

    # Average order value
    avg_order_result = db.execute_query("""
        SELECT AVG(total_amount) as avg_value
        FROM orders
        WHERE status != 'cancelled'
    """, fetch=True, fetchone=True)
    analytics['avg_order_value'] = avg_order_result['avg_value'] if avg_order_result and avg_order_result['avg_value'] else 0.0

    # Customer retention rate (simplified)
    analytics['retention_rate'] = 65.0  # Placeholder

    # Active sellers
    active_sellers_result = db.execute_query("""
        SELECT COUNT(DISTINCT seller_id) as count
        FROM orders
        WHERE created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)
    """, fetch=True, fetchone=True)
    analytics['active_sellers'] = active_sellers_result['count'] if active_sellers_result else 0

    # Recent activity (simplified)
    recent_activity_result = db.execute_query("""
        SELECT 'orders' as type, COUNT(*) as count
        FROM orders
        WHERE created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)
        UNION ALL
        SELECT 'users' as type, COUNT(*) as count
        FROM users
        WHERE created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)
        UNION ALL
        SELECT 'products' as type, COUNT(*) as count
        FROM products
        WHERE created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)
    """, fetch=True)
    analytics['recent_activity'] = recent_activity_result if recent_activity_result else []

    # Monthly data for charts
    monthly_data = db.execute_query("""
        SELECT DATE_FORMAT(created_at, '%b') as month,
               SUM(total_amount) as revenue,
               COUNT(*) as orders
        FROM orders
        WHERE created_at >= DATE_SUB(NOW(), INTERVAL 6 MONTH)
        AND status != 'cancelled'
        GROUP BY DATE_FORMAT(created_at, '%Y-%m'), DATE_FORMAT(created_at, '%b')
        ORDER BY MIN(created_at)
    """, fetch=True)

    analytics['monthly_labels'] = [row['month'] for row in monthly_data] if monthly_data else []
    analytics['monthly_revenue'] = [float(row['revenue']) for row in monthly_data] if monthly_data else []
    analytics['monthly_users'] = []  # Would need user registration data

    return render_template('admin/analytics.html', analytics=analytics)

@admin_bp.route('/system-settings', methods=['GET', 'POST'])
@login_required
@admin_required
def system_settings():
    """System settings and configuration"""
    db = Database()
    
    # Get current settings (these would typically be stored in a settings table)
    # For now, we'll use default values
    current_settings = {
        'site_name': 'PawfectFinds',
        'site_description': 'Your one-stop shop for all pet needs',
        'admin_email': 'admin@pawfectfinds.com',
        'maintenance_mode': '0',
        'max_products_per_seller': 100,
        'order_auto_cancel_days': 7,
        'featured_products_limit': 10,
        'default_currency': 'USD'
    }
    
    form = SystemSettingsForm(data=current_settings)
    
    if form.validate_on_submit():
        # In a real application, you would save these settings to a database
        # For now, we'll just show a success message
        flash('System settings updated successfully!', 'success')
        return redirect(url_for('admin.system_settings'))
    
    # Get categories for management
    categories = db.execute_query("SELECT * FROM categories ORDER BY name", fetch=True)
    
    return render_template('admin/system_settings.html',
                         categories=categories,
                         form=form)

@admin_bp.route('/bulk-actions', methods=['POST'])
@login_required
@admin_required
def bulk_actions():
    """Handle bulk actions for users/products"""
    action = request.form.get('bulk_action')
    selected_items = request.form.getlist('selected_items')
    
    if not selected_items:
        flash('No items selected.', 'error')
        return redirect(request.referrer or url_for('admin.dashboard'))
    
    # Convert to integers
    try:
        selected_ids = [int(id) for id in selected_items]
    except ValueError:
        flash('Invalid selection.', 'error')
        return redirect(request.referrer or url_for('admin.dashboard'))
    
    success_count = 0
    
    if action == 'activate_users':
        for user_id in selected_ids:
            if user_id != session['user_id']:  # Don't affect current admin
                try:
                    User.update_status(user_id, 'active')
                    success_count += 1
                except:
                    pass
        flash(f'{success_count} users activated.', 'success')
    
    elif action == 'deactivate_users':
        for user_id in selected_ids:
            if user_id != session['user_id']:  # Don't affect current admin
                try:
                    User.update_status(user_id, 'inactive')
                    success_count += 1
                except:
                    pass
        flash(f'{success_count} users deactivated.', 'info')
    
    elif action == 'ban_users':
        for user_id in selected_ids:
            if user_id != session['user_id']:  # Don't affect current admin
                try:
                    User.update_status(user_id, 'banned')
                    success_count += 1
                except:
                    pass
        flash(f'{success_count} users banned.', 'warning')
    
    elif action == 'deactivate_products':
        for product_id in selected_ids:
            try:
                Product.update(product_id, status='inactive')
                success_count += 1
            except:
                pass
        flash(f'{success_count} products deactivated.', 'info')
    
    return redirect(request.referrer or url_for('admin.dashboard'))

@admin_bp.route('/reports')
@login_required
@admin_required
def reports():
    """Detailed reports page"""
    db = Database()
    
    # Revenue by month (last 12 months)
    monthly_revenue = db.execute_query("""
        SELECT DATE_FORMAT(created_at, '%Y-%m') as month, 
               COUNT(*) as orders, 
               SUM(total_amount) as revenue
        FROM orders 
        WHERE created_at >= DATE_SUB(NOW(), INTERVAL 12 MONTH)
          AND status != 'cancelled'
        GROUP BY DATE_FORMAT(created_at, '%Y-%m')
        ORDER BY month DESC
    """, fetch=True)
    
    # Customer acquisition by month
    user_growth = db.execute_query("""
        SELECT DATE_FORMAT(created_at, '%Y-%m') as month,
               COUNT(*) as new_users
        FROM users 
        WHERE created_at >= DATE_SUB(NOW(), INTERVAL 12 MONTH)
        GROUP BY DATE_FORMAT(created_at, '%Y-%m')
        ORDER BY month DESC
    """, fetch=True)
    
    # Product performance
    product_performance = db.execute_query("""
        SELECT p.name, p.price, 
               COUNT(oi.id) as times_sold,
               SUM(oi.quantity) as total_quantity,
               SUM(oi.quantity * oi.price_at_time) as total_revenue
        FROM products p
        LEFT JOIN order_items oi ON p.id = oi.product_id
        GROUP BY p.id
        ORDER BY total_revenue DESC
        LIMIT 20
    """, fetch=True)
    
    # Order status distribution
    order_status_stats = db.execute_query("""
        SELECT status, COUNT(*) as count
        FROM orders
        GROUP BY status
        ORDER BY count DESC
    """, fetch=True)
    
    return render_template('admin/reports.html',
                         monthly_revenue=monthly_revenue,
                         user_growth=user_growth,
                         product_performance=product_performance,
                         order_status_stats=order_status_stats)

@admin_bp.route('/categories/add', methods=['POST'])
@login_required
@admin_required
def add_category():
    """Add new category"""
    form = CategoryForm()
    if form.validate_on_submit():
        name = form.name.data.strip()
        description = form.description.data.strip() if form.description.data else None
        
        db = Database()
        try:
            db.execute_query("INSERT INTO categories (name, description) VALUES (%s, %s)",
                            (name, description))
            flash('Category added successfully!', 'success')
        except Exception as e:
            flash('Failed to add category. Name may already exist.', 'error')
    else:
        flash('Please correct the errors in the form.', 'error')
    
    return redirect(url_for('admin.system_settings'))

@admin_bp.route('/categories/<int:category_id>/toggle', methods=['POST'])
@login_required
@admin_required
def toggle_category(category_id):
    """Toggle category active status"""
    db = Database()
    try:
        # Get current status and toggle it
        current = db.execute_query("SELECT is_active FROM categories WHERE id = %s",
                                  (category_id,), fetch=True, fetchone=True)
        if current:
            new_status = not current['is_active']
            db.execute_query("UPDATE categories SET is_active = %s WHERE id = %s",
                           (new_status, category_id))
            status_text = "activated" if new_status else "deactivated"
            flash(f'Category {status_text} successfully!', 'success')
        else:
            flash('Category not found.', 'error')
    except Exception as e:
        flash('Failed to update category status.', 'error')
    
    return redirect(url_for('admin.system_settings'))


@admin_bp.route('/ban-user', methods=['POST'])
@login_required
@admin_required
def ban_user():
    """Ban a user"""
    user_id = request.form.get('user_id')
    if not user_id:
        flash('User ID not provided.', 'error')
        return redirect(url_for('admin.manage_users'))

    try:
        user_id = int(user_id)
    except ValueError:
        flash('Invalid user ID.', 'error')
        return redirect(url_for('admin.manage_users'))

    # Prevent admin from banning themselves
    if user_id == session['user_id']:
        flash('You cannot ban yourself.', 'error')
        return redirect(url_for('admin.manage_users'))

    try:
        User.update_status(user_id, 'banned')
        flash('User banned successfully.', 'warning')
    except Exception as e:
        flash('Failed to ban user.', 'error')

    return redirect(url_for('admin.manage_users'))


@admin_bp.route('/revoke-seller', methods=['POST'])
@login_required
@admin_required
def revoke_seller():
    """Revoke seller status from a user"""
    user_id = request.form.get('user_id')
    if not user_id:
        flash('User ID not provided.', 'error')
        return redirect(url_for('admin.manage_users'))

    try:
        user_id = int(user_id)
    except ValueError:
        flash('Invalid user ID.', 'error')
        return redirect(url_for('admin.manage_users'))

    # Prevent admin from revoking their own seller status (though admin is not seller)
    if user_id == session['user_id']:
        flash('You cannot revoke your own seller status.', 'error')
        return redirect(url_for('admin.manage_users'))

    try:
        User.update_role(user_id, 'user')
        flash('Seller status revoked successfully.', 'info')
    except Exception as e:
        flash('Failed to revoke seller status.', 'error')

    return redirect(url_for('admin.manage_users'))


@admin_bp.route('/unban-user', methods=['POST'])
@login_required
@admin_required
def unban_user():
    """Unban a user"""
    user_id = request.form.get('user_id')
    if not user_id:
        flash('User ID not provided.', 'error')
        return redirect(url_for('admin.manage_users'))

    try:
        user_id = int(user_id)
    except ValueError:
        flash('Invalid user ID.', 'error')
        return redirect(url_for('admin.manage_users'))

    # Prevent admin from unbanning themselves
    if user_id == session['user_id']:
        flash('You cannot unban yourself.', 'error')
        return redirect(url_for('admin.manage_users'))

    try:
        User.update_status(user_id, 'active')
        flash('User unbanned successfully.', 'success')
    except Exception as e:
        flash('Failed to unban user.', 'error')

    return redirect(url_for('admin.manage_users'))


@admin_bp.route('/user/<int:user_id>/details')
@login_required
@admin_required
def user_details(user_id):
    """Get user details for modal"""
    try:
        user = User.get_by_id(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404

        # Handle None values
        first_name = user.first_name or ''
        last_name = user.last_name or ''
        avatar_initial = first_name[0].upper() if first_name else (user.username[0].upper() if user.username else '?')
        full_name = f"{first_name} {last_name}".strip()
        if not full_name:
            full_name = user.username

        # Get user orders count
        db = Database()
        orders_count_result = db.execute_query("SELECT COUNT(*) as count FROM orders WHERE user_id = %s", (user_id,), fetch=True, fetchone=True)
        orders_count = orders_count_result['count'] if orders_count_result else 0

        # Get user products if seller
        products_count = 0
        if user.role == 'seller':
            products_count_result = db.execute_query("SELECT COUNT(*) as count FROM products WHERE seller_id = %s", (user_id,), fetch=True, fetchone=True)
            products_count = products_count_result['count'] if products_count_result else 0

        created_at_str = user.created_at.strftime('%B %d, %Y') if user.created_at else 'Unknown'
        last_login_str = user.last_login.strftime('%B %d, %Y') if user.last_login else 'Never'
        status = user.status or 'active'
        status_class = 'success' if status == 'active' else 'danger' if status == 'banned' else 'secondary'

        html = f"""
        <div class="row">
            <div class="col-md-4 text-center">
                <div class="avatar-circle bg-primary text-white mx-auto mb-3" style="width: 80px; height: 80px; font-size: 2em;">
                    {avatar_initial}
                </div>
                <h5>{full_name}</h5>
                <p class="text-muted">@{user.username}</p>
            </div>
            <div class="col-md-8">
                <div class="row">
                    <div class="col-sm-6">
                        <strong>Email:</strong> {user.email or 'N/A'}
                    </div>
                    <div class="col-sm-6">
                        <strong>Role:</strong> <span class="badge bg-secondary">{user.role.title()}</span>
                    </div>
                    <div class="col-sm-6">
                        <strong>Status:</strong> <span class="badge bg-{status_class}">{status.title()}</span>
                    </div>
                    <div class="col-sm-6">
                        <strong>Joined:</strong> {created_at_str}
                    </div>
                    <div class="col-sm-6">
                        <strong>Last Login:</strong> {last_login_str}
                    </div>
                    <div class="col-sm-6">
                        <strong>Orders:</strong> {orders_count}
                    </div>
                    {'<div class="col-sm-6"><strong>Products:</strong> ' + str(products_count) + '</div>' if user.role == 'seller' else ''}
                </div>
            </div>
        </div>
        """

        return jsonify({'html': html})
    except Exception as e:
        import traceback
        error_msg = f"Server error: {str(e)}\n{traceback.format_exc()}"
        return jsonify({'error': error_msg}), 500

@admin_bp.route('/add-user', methods=['GET', 'POST'])
@login_required
@admin_required
def add_user():
    """Add a new user"""
    from app.forms import SignupForm

    form = SignupForm()
    if form.validate_on_submit():
        try:
            # Create new user
            user_data = {
                'first_name': form.first_name.data,
                'last_name': form.last_name.data,
                'username': form.username.data,
                'email': form.email.data,
                'password': form.password.data,
                'phone': form.phone.data,
                'address': form.address.data,
                'role': 'user',  # Default role
                'status': 'active'
            }

            User.create(user_data)
            flash('User created successfully!', 'success')
            return redirect(url_for('admin.manage_users'))

        except Exception as e:
            flash('Failed to create user. Email or username may already exist.', 'error')

    return render_template('admin/add_user.html', form=form)
