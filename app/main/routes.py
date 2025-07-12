from flask import render_template, redirect, url_for, send_from_directory, current_app, request, session, jsonify, flash
from flask_login import current_user, login_user
from app.main import bp
from app.models import MenuItem, Category, Table, TableSession, QRCode, User
from app.extensions import db
import os

@bp.route('/')
def index():
    """Main landing page"""
    if current_user.is_authenticated:
        if current_user.is_admin():
            return redirect(url_for('admin.dashboard'))
        elif current_user.is_waiter():
            return redirect(url_for('waiter.dashboard'))
        else:
            return redirect(url_for('customer.home'))

    # Load popular menu items based on order frequency for the landing page
    popular_items = MenuItem.get_popular_items(limit=4)

    # If no popular items (no orders yet), fall back to first 4 available items
    if not popular_items:
        popular_items = MenuItem.query.filter_by(status='available').limit(4).all()

    return render_template('shared/landing.html', popular_items=popular_items)

@bp.route('/test-checkout')
def test_checkout():
    """Test checkout functionality"""
    return send_from_directory('.', 'test_checkout.html')

@bp.route('/uploads/<path:filename>')
def uploaded_file(filename):
    """Serve uploaded files"""
    upload_folder = os.path.join(current_app.root_path, current_app.config['UPLOAD_FOLDER'])
    return send_from_directory(upload_folder, filename)

@bp.route('/customer-service-test')
def customer_service_test():
    """Customer service test page"""
    return send_from_directory('.', 'customer_service_test.html')

@bp.route('/table/<int:table_id>')
def table_landing(table_id):
    """Customer landing page when scanning QR code or accessing via WhatsApp session"""
    # Get table info
    table = Table.query.get_or_404(table_id)

    # Get session token from URL parameter (WhatsApp integration)
    session_token = request.args.get('session')

    if session_token:
        # Validate WhatsApp session
        return handle_whatsapp_session_access(table_id, session_token)
    else:
        # Handle traditional web access
        return handle_traditional_web_access(table_id)

def handle_whatsapp_session_access(table_id, session_token):
    """Handle access via WhatsApp session token"""
    try:
        # Validate session via API
        import requests
        response = requests.get(f'http://localhost:5000/api/whatsapp-sessions/{session_token}/validate')

        if response.status_code != 200:
            flash('جلسة غير صالحة أو منتهية الصلاحية. يرجى مسح رمز QR مرة أخرى.', 'error')
            return redirect(url_for('main.index'))

        session_data = response.json()['data']

        # Verify table ID matches
        if session_data['table_id'] != table_id:
            flash('رقم الطاولة غير صحيح.', 'error')
            return redirect(url_for('main.index'))

        # Store session info in Flask session
        session['whatsapp_session_token'] = session_token
        session['whatsapp_customer_id'] = session_data['customer_id']
        session['whatsapp_table_id'] = table_id
        session['whatsapp_customer_name'] = session_data['customer_name']

        # Get customer and login automatically
        customer = User.query.get(session_data['customer_id'])
        if customer:
            login_user(customer, remember=False)

        # Redirect to customer menu with session context
        return redirect(url_for('customer.menu', table_id=table_id, session=session_token))

    except Exception as e:
        print(f"Error validating WhatsApp session: {e}")
        flash('حدث خطأ في التحقق من الجلسة. يرجى المحاولة مرة أخرى.', 'error')
        return redirect(url_for('main.index'))

def handle_traditional_web_access(table_id):
    """Handle traditional web access (existing functionality)"""
    # Get or create table session
    session_token = session.get(f'table_{table_id}_session')
    user_id = current_user.user_id if current_user.is_authenticated else None

    # Get device and IP info
    device_info = request.headers.get('User-Agent', 'Unknown')
    ip_address = request.remote_addr

    # Check for existing active session
    table_session = TableSession.get_active_session(
        table_id=table_id,
        user_id=user_id,
        session_token=session_token
    )
    
    # Create new session if none exists
    if not table_session:
        table_session = TableSession.create_session(
            table_id=table_id,
            user_id=user_id,
            device_info=device_info,
            ip_address=ip_address
        )
    
    # Store session token in browser session
    session[f'table_{table_id}_session'] = table_session.session_token
    
    # Update table status if available
    if table.status == 'available':
        table.status = 'occupied'
        db.session.commit()
    
    # Get popular menu items for the table landing
    popular_items = MenuItem.get_popular_items(limit=6)
    if not popular_items:
        popular_items = MenuItem.query.filter_by(status='available').limit(6).all()
    
    # Get all categories for menu navigation
    categories = Category.query.filter_by(is_active=True).all()
    
    return render_template('table_landing.html',
                         table=table,
                         table_session=table_session,
                         popular_items=popular_items,
                         categories=categories)

@bp.route('/clear-cart')
def clear_cart():
    """Cart cleanup utility page"""
    return render_template('clear_cart.html')
