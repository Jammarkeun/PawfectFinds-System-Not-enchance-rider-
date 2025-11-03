from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from app.models.review import Review
from app.models.product import Product
from app.models.user import User
from app.models.order import Order
from app.utils.decorators import login_required, admin_required
from app.services.database import Database

review_bp = Blueprint('review', __name__)

@review_bp.route('/product/<int:product_id>')
def product_reviews(product_id):
    """Display all reviews for a product"""
    product = Product.get_by_id(product_id)
    if not product:
        flash('Product not found.', 'error')
        return redirect(url_for('public.products'))
    
    # Get all reviews for this product
    reviews = Review.get_for_product(product_id)
    
    # Get rating statistics
    rating_stats = Review.get_product_average_rating(product_id)
    
    # Get rating distribution
    db = Database()
    rating_distribution = db.execute_query("""
        SELECT rating, COUNT(*) as count
        FROM reviews
        WHERE product_id = %s
        GROUP BY rating
        ORDER BY rating DESC
    """, (product_id,), fetch=True)
    
    # Convert to dictionary for easier template usage
    rating_counts = {i: 0 for i in range(1, 6)}
    for item in rating_distribution:
        rating_counts[item['rating']] = item['count']
    
    # Check if current user can leave a review
    can_review = False
    user_review = None
    
    if 'user_id' in session:
        user_id = session['user_id']
        
        # Check if user has purchased this product
        has_purchased = db.execute_query("""
            SELECT COUNT(*) as count
            FROM orders o
            JOIN order_items oi ON o.id = oi.order_id
            WHERE o.user_id = %s AND oi.product_id = %s AND o.status IN ('delivered', 'shipped', 'on_the_way', 'picked_up')
        """, (user_id, product_id), fetch=True, fetchone=True)

        can_review = has_purchased['count'] > 0
        
        # Get existing review by this user
        user_review = Review.get_by_user_product(user_id, product_id)
    
    return render_template('review/product_reviews.html',
                         product=product,
                         reviews=reviews,
                         rating_stats=rating_stats,
                         rating_counts=rating_counts,
                         can_review=can_review,
                         user_review=user_review)

@review_bp.route('/add', methods=['POST'])
@login_required
def add_review():
    """Add a new product review"""
    try:
        product_id = int(request.form.get('product_id'))
        rating = int(request.form.get('rating'))
        comment = request.form.get('comment', '').strip()
        
        if not (1 <= rating <= 5):
            flash('Rating must be between 1 and 5 stars.', 'error')
            return redirect(request.referrer or url_for('public.products'))
        
        user_id = session['user_id']
        
        # Check if product exists
        product = Product.get_by_id(product_id)
        if not product:
            flash('Product not found.', 'error')
            return redirect(url_for('public.products'))
        
        # Check if user has purchased this product
        db = Database()
        has_purchased = db.execute_query("""
            SELECT COUNT(*) as count
            FROM orders o
            JOIN order_items oi ON o.id = oi.order_id
            WHERE o.user_id = %s AND oi.product_id = %s AND o.status IN ('delivered', 'shipped', 'on_the_way', 'picked_up')
        """, (user_id, product_id), fetch=True, fetchone=True)

        if has_purchased['count'] == 0:
            flash('You can only review products you have purchased and received.', 'error')
            return redirect(request.referrer or url_for('public.product_details', product_id=product_id))
        
        # Create or update review
        review = Review.create(user_id, product_id, rating, comment if comment else None)
        
        if review:
            flash('Thank you for your review!', 'success')
        else:
            flash('Failed to save review. Please try again.', 'error')
        
        return redirect(url_for('public.product_detail', product_id=product_id))
        
    except (ValueError, TypeError):
        flash('Invalid input.', 'error')
        return redirect(request.referrer or url_for('public.products'))

@review_bp.route('/edit/<int:review_id>', methods=['GET', 'POST'])
@login_required
def edit_review(review_id):
    """Edit an existing review"""
    review = Review.get_by_id(review_id)
    if not review:
        flash('Review not found.', 'error')
        return redirect(url_for('user.dashboard'))
    
    # Check if user owns this review
    if review['user_id'] != session['user_id']:
        flash('Unauthorized to edit this review.', 'error')
        return redirect(url_for('user.dashboard'))
    
    if request.method == 'POST':
        try:
            rating = int(request.form.get('rating'))
            comment = request.form.get('comment', '').strip()
            
            if not (1 <= rating <= 5):
                flash('Rating must be between 1 and 5 stars.', 'error')
                return render_template('review/edit.html', review=review)
            
            # Update review
            updated_review = Review.update(review_id, rating, comment if comment else None)
            
            if updated_review:
                flash('Review updated successfully!', 'success')
                return redirect(url_for('public.product_detail', product_id=review['product_id']))
            else:
                flash('Failed to update review.', 'error')
                
        except (ValueError, TypeError):
            flash('Invalid input.', 'error')
    
    # Get product info for display
    product = Product.get_by_id(review['product_id'])
    
    return render_template('review/edit.html', review=review, product=product)

@review_bp.route('/delete/<int:review_id>', methods=['POST'])
@login_required
def delete_review(review_id):
    """Delete a review"""
    review = Review.get_by_id(review_id)
    if not review:
        flash('Review not found.', 'error')
        return redirect(request.referrer or url_for('user.dashboard'))
    
    user_id = session['user_id']
    user = User.get_by_id(user_id)
    
    # Check permissions (owner or admin)
    if review['user_id'] != user_id and user['role'] != 'admin':
        flash('Unauthorized to delete this review.', 'error')
        return redirect(request.referrer or url_for('user.dashboard'))
    
    try:
        Review.delete(review_id)
        flash('Review deleted successfully.', 'success')
    except Exception as e:
        flash('Failed to delete review.', 'error')
    
    # Redirect based on user role
    if user['role'] == 'admin':
        return redirect(url_for('review.moderate_reviews'))
    else:
        return redirect(url_for('user.my_reviews'))

@review_bp.route('/my-reviews')
@login_required
def my_reviews():
    """Display current user's reviews"""
    user_id = session['user_id']
    
    # Get user's reviews with product information
    db = Database()
    reviews = db.execute_query("""
        SELECT r.*, p.name as product_name, p.image_url as product_image
        FROM reviews r
        JOIN products p ON r.product_id = p.id
        WHERE r.user_id = %s
        ORDER BY r.created_at DESC
    """, (user_id,), fetch=True)
    
    return render_template('review/my_reviews.html', reviews=reviews)

@review_bp.route('/moderate')
@login_required
@admin_required
def moderate_reviews():
    """Admin review moderation panel"""
    # Get filter parameters
    status_filter = request.args.get('status', 'all')
    rating_filter = request.args.get('rating', 'all')
    page = int(request.args.get('page', 1))
    per_page = 20
    offset = (page - 1) * per_page
    
    db = Database()
    
    # Build query
    query = """
        SELECT r.*, u.username, u.first_name, u.last_name,
               p.name as product_name, p.image_url as product_image
        FROM reviews r
        JOIN users u ON r.user_id = u.id
        JOIN products p ON r.product_id = p.id
        WHERE 1=1
    """
    params = []
    
    # Apply filters
    if rating_filter != 'all':
        try:
            rating_val = int(rating_filter)
            query += " AND r.rating = %s"
            params.append(rating_val)
        except ValueError:
            pass
    
    # For demonstration, we'll assume reviews have a 'status' field for moderation
    # In reality, you might add this field to the reviews table
    
    query += " ORDER BY r.created_at DESC LIMIT %s OFFSET %s"
    params.extend([per_page, offset])
    
    reviews = db.execute_query(query, params, fetch=True)
    
    # Get total count for pagination
    count_query = "SELECT COUNT(*) as total FROM reviews r WHERE 1=1"
    count_params = []
    
    if rating_filter != 'all':
        try:
            rating_val = int(rating_filter)
            count_query += " AND r.rating = %s"
            count_params.append(rating_val)
        except ValueError:
            pass
    
    total_count = db.execute_query(count_query, count_params, fetch=True, fetchone=True)
    total = total_count['total'] if total_count else 0
    
    # Calculate pagination
    total_pages = (total + per_page - 1) // per_page
    has_prev = page > 1
    has_next = page < total_pages
    
    # Get review statistics
    review_stats = db.execute_query("""
        SELECT 
            COUNT(*) as total_reviews,
            AVG(rating) as avg_rating,
            COUNT(CASE WHEN rating = 5 THEN 1 END) as five_star,
            COUNT(CASE WHEN rating = 4 THEN 1 END) as four_star,
            COUNT(CASE WHEN rating = 3 THEN 1 END) as three_star,
            COUNT(CASE WHEN rating = 2 THEN 1 END) as two_star,
            COUNT(CASE WHEN rating = 1 THEN 1 END) as one_star
        FROM reviews
    """, fetch=True, fetchone=True)
    
    return render_template('review/moderate.html',
                         reviews=reviews,
                         review_stats=review_stats,
                         current_rating=rating_filter,
                         page=page,
                         total_pages=total_pages,
                         has_prev=has_prev,
                         has_next=has_next,
                         prev_page=page-1 if has_prev else None,
                         next_page=page+1 if has_next else None,
                         total_reviews=total)

@review_bp.route('/bulk-action', methods=['POST'])
@login_required
@admin_required
def bulk_review_action():
    """Handle bulk actions on reviews (admin only)"""
    action = request.form.get('bulk_action')
    selected_reviews = request.form.getlist('selected_reviews')
    
    if not selected_reviews:
        flash('No reviews selected.', 'error')
        return redirect(url_for('review.moderate_reviews'))
    
    success_count = 0
    
    try:
        review_ids = [int(review_id) for review_id in selected_reviews]
        
        if action == 'delete':
            for review_id in review_ids:
                try:
                    Review.delete(review_id)
                    success_count += 1
                except:
                    pass
            
            flash(f'{success_count} reviews deleted.', 'info')
        
        # You can add more bulk actions here like 'hide', 'approve', etc.
        
    except (ValueError, TypeError):
        flash('Invalid selection.', 'error')
    
    return redirect(url_for('review.moderate_reviews'))

@review_bp.route('/analytics')
@login_required
@admin_required
def review_analytics():
    """Review analytics for admin"""
    db = Database()
    
    # Overall review statistics
    overall_stats = db.execute_query("""
        SELECT 
            COUNT(*) as total_reviews,
            AVG(rating) as avg_rating,
            COUNT(DISTINCT user_id) as unique_reviewers,
            COUNT(DISTINCT product_id) as reviewed_products
        FROM reviews
    """, fetch=True, fetchone=True)
    
    # Rating distribution
    rating_distribution = db.execute_query("""
        SELECT rating, COUNT(*) as count
        FROM reviews
        GROUP BY rating
        ORDER BY rating DESC
    """, fetch=True)
    
    # Most reviewed products
    most_reviewed = db.execute_query("""
        SELECT p.name, p.id, COUNT(r.id) as review_count, AVG(r.rating) as avg_rating
        FROM products p
        JOIN reviews r ON p.id = r.product_id
        GROUP BY p.id
        ORDER BY review_count DESC
        LIMIT 10
    """, fetch=True)
    
    # Top reviewers
    top_reviewers = db.execute_query("""
        SELECT u.username, u.first_name, u.last_name, 
               COUNT(r.id) as review_count, AVG(r.rating) as avg_given_rating
        FROM users u
        JOIN reviews r ON u.id = r.user_id
        GROUP BY u.id
        ORDER BY review_count DESC
        LIMIT 10
    """, fetch=True)
    
    # Review trends (last 12 months)
    review_trends = db.execute_query("""
        SELECT DATE_FORMAT(created_at, '%Y-%m') as month,
               COUNT(*) as review_count,
               AVG(rating) as avg_rating
        FROM reviews
        WHERE created_at >= DATE_SUB(NOW(), INTERVAL 12 MONTH)
        GROUP BY DATE_FORMAT(created_at, '%Y-%m')
        ORDER BY month ASC
    """, fetch=True)
    
    return render_template('review/analytics.html',
                         overall_stats=overall_stats,
                         rating_distribution=rating_distribution,
                         most_reviewed=most_reviewed,
                         top_reviewers=top_reviewers,
                         review_trends=review_trends)

@review_bp.route('/helpful/<int:review_id>', methods=['POST'])
@login_required
def mark_helpful(review_id):
    """Mark a review as helpful (for future enhancement)"""
    # This would require a separate table to track helpful votes
    # For now, just return success
    return jsonify({'success': True, 'message': 'Feature coming soon!'})

@review_bp.route('/report/<int:review_id>', methods=['POST'])
@login_required
def report_review(review_id):
    """Report inappropriate review"""
    reason = request.form.get('reason', '').strip()
    
    if not reason:
        return jsonify({'error': 'Reason is required'}), 400
    
    # In a real application, you would store this report in a database
    # For now, we'll just simulate success
    
    # Log the report (you could create a reports table)
    db = Database()
    try:
        # This is a placeholder - you would create a reports table
        # db.execute_query("""
        #     INSERT INTO review_reports (review_id, reporter_id, reason, created_at)
        #     VALUES (%s, %s, %s, NOW())
        # """, (review_id, session['user_id'], reason))
        
        return jsonify({'success': True, 'message': 'Review reported successfully'})
    except Exception as e:
        return jsonify({'error': 'Failed to submit report'}), 500