from flask import Blueprint, render_template, request, session, flash
import secrets
from app.models.product import Product
from app.services.database import Database
from config.config import Config

public_bp = Blueprint('public', __name__)

@public_bp.route('/')
def landing():
    """Landing page with featured products"""
    # Get featured products (newest ones)
    featured_products = Product.list(limit=8, offset=0)
    
    # Get categories
    db = Database()
    categories = db.execute_query("SELECT * FROM categories WHERE is_active = 1", fetch=True)
    
    return render_template('public/landing.html', 
                         featured_products=featured_products,
                         categories=categories)

@public_bp.route('/products')
def browse_products():
    """Browse all products with filtering and pagination"""
    page = int(request.args.get('page', 1))
    category_id = request.args.get('category')
    search = request.args.get('search', '').strip()
    per_page = Config.PRODUCTS_PER_PAGE
    offset = (page - 1) * per_page
    
    # Get products
    products = Product.list(
        category_id=int(category_id) if category_id else None,
        search=search if search else None,
        limit=per_page,
        offset=offset
    )
    
    # Get total count for pagination
    total = Product.count(
        category_id=int(category_id) if category_id else None,
        search=search if search else None
    )
    
    # Calculate pagination info
    total_pages = (total + per_page - 1) // per_page
    has_prev = page > 1
    has_next = page < total_pages
    
    # Get categories for filter
    db = Database()
    categories = db.execute_query("SELECT * FROM categories WHERE is_active = 1", fetch=True)
    
    return render_template('public/products.html',
                         products=products,
                         categories=categories,
                         current_page=page,
                         total_pages=total_pages,
                         has_prev=has_prev,
                         has_next=has_next,
                         prev_page=page-1 if has_prev else None,
                         next_page=page+1 if has_next else None,
                         category_id=int(category_id) if category_id else None,
                         search=search,
                         total_products=total)

@public_bp.route('/product/<int:product_id>')
def product_detail(product_id):
    """Product detail page with reviews"""
    product = Product.get_by_id(product_id)
    if not product:
        return render_template('public/404.html'), 404
    
    # Get reviews for this product
    from app.models.review import Review
    reviews = Review.get_for_product(product_id)
    rating_info = Review.get_product_average_rating(product_id)
    
    # Check if current user has reviewed this product
    user_review = None
    if 'user_id' in session:
        user_review = Review.get_by_user_product(session['user_id'], product_id)
    
    return render_template('public/product_detail.html',
                         product=product,
                         reviews=reviews,
                         rating_info=rating_info,
                         user_review=user_review)

@public_bp.route('/category/<int:category_id>')
def category_products(category_id):
    """Products in a specific category"""
    page = int(request.args.get('page', 1))
    search = request.args.get('search', '').strip()
    per_page = Config.PRODUCTS_PER_PAGE
    offset = (page - 1) * per_page
    
    # Get category info
    db = Database()
    category = db.execute_query("SELECT * FROM categories WHERE id = %s", 
                               (category_id,), fetch=True, fetchone=True)
    if not category:
        return render_template('public/404.html'), 404
    
    # Get products in this category
    products = Product.list(
        category_id=category_id,
        search=search if search else None,
        limit=per_page,
        offset=offset
    )
    
    # Get total count for pagination
    total = Product.count(
        category_id=category_id,
        search=search if search else None
    )
    
    # Calculate pagination info
    total_pages = (total + per_page - 1) // per_page
    has_prev = page > 1
    has_next = page < total_pages
    
    return render_template('public/category_products.html',
                         products=products,
                         category=category,
                         current_page=page,
                         total_pages=total_pages,
                         has_prev=has_prev,
                         has_next=has_next,
                         prev_page=page-1 if has_prev else None,
                         next_page=page+1 if has_next else None,
                         search=search,
                         total_products=total)

@public_bp.route('/about')
def about():
    """About us page"""
    return render_template('about.html')

@public_bp.route('/contact', methods=['GET', 'POST'])
def contact():
    """Contact page"""
    if request.method == 'POST':
        # Process form data (CSRF handled by global CSRFProtect)
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()
        subject = request.form.get('subject', '').strip()
        message = request.form.get('message', '').strip()
        newsletter = 'newsletter' in request.form
        
        # Basic validation
        if not all([first_name, last_name, email, subject, message]):
            flash('Please fill in all required fields.', 'error')
            return render_template('contact.html')
        
        # For now, log the contact info (in production, send email)
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"Contact form submitted: {first_name} {last_name} ({email}) - Subject: {subject} - Message: {message[:100]}...")
        
        # If newsletter signup
        if newsletter:
            # Add to newsletter list (placeholder)
            logger.info(f"Newsletter signup: {email}")
        
        flash('Thank you for your message! We will get back to you within 24 hours.', 'success')
        return redirect(url_for('public.contact'))
    
    return render_template('contact.html')
