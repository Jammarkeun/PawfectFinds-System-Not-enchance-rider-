from flask import Blueprint, render_template, request, jsonify, redirect, url_for
from app.utils.db import db
import math

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    """Landing page with featured products and categories"""
    # Get featured products (checking for featured column existence)
    featured_products = db.execute_query("""
        SELECT * FROM products 
        WHERE status = 'active' 
        ORDER BY created_at DESC 
        LIMIT 8
    """)
    
    # Get all active categories (checking for status column existence)
    categories = db.execute_query("""
        SELECT * FROM categories 
        ORDER BY name ASC
    """)
    
    # Default site settings
    site_settings = {
        'site_name': 'Pawfect Finds',
        'site_description': 'Your one-stop shop for pet supplies'
    }
    
    return render_template('public/simple_index.html', 
                         featured_products=featured_products or [],
                         categories=categories or [],
                         site_settings=site_settings)

@main_bp.route('/products')
def products():
    """Product catalog page with basic functionality"""
    # Get all products
    products = db.execute_query("""
        SELECT * FROM products 
        WHERE status = 'active' 
        ORDER BY created_at DESC
    """)
    
    # Get categories
    categories = db.execute_query("""
        SELECT * FROM categories 
        ORDER BY name ASC
    """)
    
    return render_template('public/simple_products.html',
                         products=products or [],
                         categories=categories or [])

@main_bp.route('/product/<int:product_id>')
def product_detail(product_id):
    """Product detail page"""
    product = db.get_one("""
        SELECT * FROM products 
        WHERE id = %s AND status = 'active'
    """, (product_id,))
    
    if not product:
        return "Product not found", 404
    
    return render_template('public/simple_product_detail.html',
                         product=product)

@main_bp.route('/about')
def about():
    """About us page"""
    return render_template('public/simple_about.html')

@main_bp.route('/contact')
def contact():
    """Contact page"""
    return render_template('public/simple_contact.html')

@main_bp.route('/api/search-suggestions')
def search_suggestions():
    """API endpoint for search autocomplete"""
    query = request.args.get('q', '').strip()
    
    if not query or len(query) < 2:
        return jsonify([])
    
    # Get product suggestions
    products = db.execute_query("""
        SELECT id, name, price 
        FROM products 
        WHERE status = 'active' AND name LIKE %s
        LIMIT 5
    """, (f'%{query}%',))
    
    suggestions = []
    if products:
        for product in products:
            suggestions.append({
                'id': product['id'],
                'name': product['name'],
                'price': float(product['price']),
                'image': '/static/img/placeholder.png'
            })
    
    return jsonify(suggestions)
