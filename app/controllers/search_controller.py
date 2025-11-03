from flask import Blueprint, render_template, request, jsonify
from app.models.product import Product
from app.models.review import Review
from app.services.database import Database
import math

search_bp = Blueprint('search', __name__)

@search_bp.route('/')
def search_products():
    """Advanced product search with filters"""
    # Get search parameters
    query = request.args.get('q', '').strip()
    category_id = request.args.get('category')
    min_price = request.args.get('min_price')
    max_price = request.args.get('max_price')
    min_rating = request.args.get('min_rating')
    sort_by = request.args.get('sort', 'relevance')
    page = int(request.args.get('page', 1))
    per_page = 20
    
    # Calculate offset for pagination
    offset = (page - 1) * per_page
    
    # Build search query
    db = Database()
    
    search_query = """
        SELECT DISTINCT p.*, c.name as category_name, u.username as seller_username,
               AVG(r.rating) as avg_rating, COUNT(r.id) as review_count,
               CASE 
                 WHEN p.name LIKE %s THEN 3
                 WHEN p.description LIKE %s THEN 2
                 WHEN c.name LIKE %s THEN 1
                 ELSE 0
               END as relevance_score
        FROM products p
        JOIN categories c ON p.category_id = c.id
        JOIN users u ON p.seller_id = u.id
        LEFT JOIN reviews r ON p.id = r.product_id
        WHERE p.status = 'active'
    """
    
    params = []
    
    # Text search
    if query:
        like_query = f"%{query}%"
        params.extend([like_query, like_query, like_query])
    else:
        # If no query, set relevance parameters to empty
        params.extend(['', '', ''])
        search_query += " AND 1=1"  # Keep the query structure
    
    # Category filter
    if category_id and category_id != 'all':
        try:
            cat_id = int(category_id)
            search_query += " AND p.category_id = %s"
            params.append(cat_id)
        except ValueError:
            pass
    
    # Price filters
    if min_price:
        try:
            min_p = float(min_price)
            search_query += " AND p.price >= %s"
            params.append(min_p)
        except ValueError:
            pass
    
    if max_price:
        try:
            max_p = float(max_price)
            search_query += " AND p.price <= %s"
            params.append(max_p)
        except ValueError:
            pass
    
    # Group by for aggregation
    search_query += " GROUP BY p.id"
    
    # Rating filter (applied after grouping)
    if min_rating:
        try:
            min_r = float(min_rating)
            search_query += " HAVING AVG(r.rating) >= %s"
            params.append(min_r)
        except ValueError:
            pass
    
    # Sorting
    if sort_by == 'price_low':
        search_query += " ORDER BY p.price ASC"
    elif sort_by == 'price_high':
        search_query += " ORDER BY p.price DESC"
    elif sort_by == 'rating':
        search_query += " ORDER BY avg_rating DESC, review_count DESC"
    elif sort_by == 'newest':
        search_query += " ORDER BY p.created_at DESC"
    elif sort_by == 'name':
        search_query += " ORDER BY p.name ASC"
    else:  # relevance (default)
        search_query += " ORDER BY relevance_score DESC, p.created_at DESC"
    
    # Add pagination
    search_query += " LIMIT %s OFFSET %s"
    params.extend([per_page, offset])
    
    # Execute search
    products = db.execute_query(search_query, params, fetch=True)
    
    # Get total count for pagination (without LIMIT)
    count_query = """
        SELECT COUNT(DISTINCT p.id) as total
        FROM products p
        JOIN categories c ON p.category_id = c.id
        LEFT JOIN reviews r ON p.id = r.product_id
        WHERE p.status = 'active'
    """
    
    count_params = []
    
    # Apply same filters for count
    if query:
        count_query += " AND (p.name LIKE %s OR p.description LIKE %s OR c.name LIKE %s)"
        like_query = f"%{query}%"
        count_params.extend([like_query, like_query, like_query])
    
    if category_id and category_id != 'all':
        try:
            cat_id = int(category_id)
            count_query += " AND p.category_id = %s"
            count_params.append(cat_id)
        except ValueError:
            pass
    
    if min_price:
        try:
            min_p = float(min_price)
            count_query += " AND p.price >= %s"
            count_params.append(min_p)
        except ValueError:
            pass
    
    if max_price:
        try:
            max_p = float(max_price)
            count_query += " AND p.price <= %s"
            count_params.append(max_p)
        except ValueError:
            pass
    
    # For rating filter in count query, we need a subquery
    if min_rating:
        try:
            min_r = float(min_rating)
            count_query = f"""
                SELECT COUNT(*) as total FROM ({count_query}
                GROUP BY p.id
                HAVING AVG(r.rating) >= %s) as filtered_products
            """
            count_params.append(min_r)
        except ValueError:
            pass
    
    total_count = db.execute_query(count_query, count_params, fetch=True, fetchone=True)
    total = total_count['total'] if total_count else 0
    
    # Calculate pagination info
    total_pages = math.ceil(total / per_page)
    has_prev = page > 1
    has_next = page < total_pages
    
    # Get categories for filter dropdown
    categories = db.execute_query(
        "SELECT * FROM categories WHERE is_active = 1 ORDER BY name",
        fetch=True
    )
    
    # Get price range for filter
    price_range = db.execute_query("""
        SELECT MIN(price) as min_price, MAX(price) as max_price 
        FROM products WHERE status = 'active'
    """, fetch=True, fetchone=True)
    
    return render_template('search/results.html',
                         products=products,
                         categories=categories,
                         query=query,
                         current_category=int(category_id) if category_id and category_id != 'all' else None,
                         current_min_price=min_price,
                         current_max_price=max_price,
                         current_min_rating=min_rating,
                         current_sort=sort_by,
                         page=page,
                         total_pages=total_pages,
                         has_prev=has_prev,
                         has_next=has_next,
                         prev_page=page-1 if has_prev else None,
                         next_page=page+1 if has_next else None,
                         total_results=total,
                         price_range=price_range)

@search_bp.route('/suggestions')
def search_suggestions():
    """AJAX endpoint for search autocomplete"""
    query = request.args.get('q', '').strip()
    
    if not query or len(query) < 2:
        return jsonify([])
    
    db = Database()
    
    # Get product name suggestions
    product_suggestions = db.execute_query("""
        SELECT DISTINCT p.name, p.id, p.image_url, p.price
        FROM products p
        WHERE p.status = 'active' AND p.name LIKE %s
        ORDER BY p.name
        LIMIT 8
    """, (f"%{query}%",), fetch=True)
    
    # Get category suggestions
    category_suggestions = db.execute_query("""
        SELECT DISTINCT c.name, c.id
        FROM categories c
        WHERE c.is_active = 1 AND c.name LIKE %s
        ORDER BY c.name
        LIMIT 3
    """, (f"%{query}%",), fetch=True)
    
    suggestions = {
        'products': product_suggestions or [],
        'categories': category_suggestions or []
    }
    
    return jsonify(suggestions)

@search_bp.route('/filters/price-range')
def get_price_range():
    """AJAX endpoint to get price range for current filters"""
    category_id = request.args.get('category')
    query = request.args.get('q', '').strip()
    
    db = Database()
    
    price_query = """
        SELECT MIN(p.price) as min_price, MAX(p.price) as max_price
        FROM products p
        JOIN categories c ON p.category_id = c.id
        WHERE p.status = 'active'
    """
    
    params = []
    
    if query:
        price_query += " AND (p.name LIKE %s OR p.description LIKE %s)"
        like_query = f"%{query}%"
        params.extend([like_query, like_query])
    
    if category_id and category_id != 'all':
        try:
            cat_id = int(category_id)
            price_query += " AND p.category_id = %s"
            params.append(cat_id)
        except ValueError:
            pass
    
    price_range = db.execute_query(price_query, params, fetch=True, fetchone=True)
    
    return jsonify({
        'min_price': float(price_range['min_price']) if price_range['min_price'] else 0,
        'max_price': float(price_range['max_price']) if price_range['max_price'] else 1000
    })

@search_bp.route('/category/<int:category_id>')
def browse_category(category_id):
    """Browse products by category"""
    db = Database()
    
    # Get category info
    category = db.execute_query(
        "SELECT * FROM categories WHERE id = %s AND is_active = 1",
        (category_id,), fetch=True, fetchone=True
    )
    
    if not category:
        return render_template('errors/404.html'), 404
    
    # Get sort and pagination parameters
    sort_by = request.args.get('sort', 'newest')
    page = int(request.args.get('page', 1))
    per_page = 20
    offset = (page - 1) * per_page
    
    # Get products in category
    products = Product.list(
        category_id=category_id,
        status='active',
        limit=per_page,
        offset=offset
    )
    
    # Sort products
    if sort_by == 'price_low':
        products.sort(key=lambda x: x['price'])
    elif sort_by == 'price_high':
        products.sort(key=lambda x: x['price'], reverse=True)
    elif sort_by == 'name':
        products.sort(key=lambda x: x['name'])
    # 'newest' is default from database query
    
    # Get total count
    total = Product.count(category_id=category_id, status='active')
    
    # Calculate pagination
    total_pages = math.ceil(total / per_page)
    has_prev = page > 1
    has_next = page < total_pages
    
    # Get related categories (same level)
    related_categories = db.execute_query("""
        SELECT * FROM categories 
        WHERE is_active = 1 AND id != %s 
        ORDER BY name 
        LIMIT 6
    """, (category_id,), fetch=True)
    
    return render_template('search/category.html',
                         category=category,
                         products=products,
                         related_categories=related_categories,
                         current_sort=sort_by,
                         page=page,
                         total_pages=total_pages,
                         has_prev=has_prev,
                         has_next=has_next,
                         prev_page=page-1 if has_prev else None,
                         next_page=page+1 if has_next else None,
                         total_results=total)

@search_bp.route('/trending')
def trending_products():
    """Show trending/popular products"""
    db = Database()
    
    # Get trending products (most ordered in last 30 days)
    trending = db.execute_query("""
        SELECT p.*, c.name as category_name, u.username as seller_username,
               COUNT(oi.id) as order_count,
               AVG(r.rating) as avg_rating,
               COUNT(DISTINCT r.id) as review_count
        FROM products p
        JOIN categories c ON p.category_id = c.id
        JOIN users u ON p.seller_id = u.id
        LEFT JOIN order_items oi ON p.id = oi.product_id
        LEFT JOIN orders o ON oi.order_id = o.id
        LEFT JOIN reviews r ON p.id = r.product_id
        WHERE p.status = 'active'
          AND (o.created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY) OR o.id IS NULL)
        GROUP BY p.id
        ORDER BY order_count DESC, avg_rating DESC
        LIMIT 24
    """, fetch=True)
    
    # Get top rated products
    top_rated = db.execute_query("""
        SELECT p.*, c.name as category_name, u.username as seller_username,
               AVG(r.rating) as avg_rating,
               COUNT(r.id) as review_count
        FROM products p
        JOIN categories c ON p.category_id = c.id
        JOIN users u ON p.seller_id = u.id
        LEFT JOIN reviews r ON p.id = r.product_id
        WHERE p.status = 'active'
        GROUP BY p.id
        HAVING COUNT(r.id) >= 3 AND AVG(r.rating) >= 4.0
        ORDER BY avg_rating DESC, review_count DESC
        LIMIT 12
    """, fetch=True)
    
    # Get newest products
    newest = db.execute_query("""
        SELECT p.*, c.name as category_name, u.username as seller_username,
               AVG(r.rating) as avg_rating,
               COUNT(r.id) as review_count
        FROM products p
        JOIN categories c ON p.category_id = c.id
        JOIN users u ON p.seller_id = u.id
        LEFT JOIN reviews r ON p.id = r.product_id
        WHERE p.status = 'active'
          AND p.created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)
        GROUP BY p.id
        ORDER BY p.created_at DESC
        LIMIT 12
    """, fetch=True)
    
    return render_template('search/trending.html',
                         trending_products=trending,
                         top_rated_products=top_rated,
                         newest_products=newest)