from flask import render_template, redirect, url_for, request, flash, jsonify, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from sqlalchemy import func
from app.modules.admin import bp
from app.models import MenuItem, Category, User, Order, Table, OrderItem, QRCode, RewardItem, CustomerLoyalty, PointTransaction, RewardRedemption, PromotionalCampaign, LoyaltyProgram, Service, SystemSettings
from app.extensions import db
from datetime import datetime, timedelta
import os
from PIL import Image

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']

def save_menu_image(file):
    """Save uploaded menu image and return filename"""
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        # Add timestamp to avoid conflicts
        import time
        timestamp = str(int(time.time()))
        name, ext = os.path.splitext(filename)
        filename = f"{name}_{timestamp}{ext}"

        # Ensure upload directory exists
        upload_path = os.path.join(current_app.root_path, current_app.config['MENU_IMAGE_FOLDER'])
        os.makedirs(upload_path, exist_ok=True)

        file_path = os.path.join(upload_path, filename)
        file.save(file_path)

        # Resize image for web optimization
        try:
            with Image.open(file_path) as img:
                # Convert to RGB if necessary
                if img.mode in ('RGBA', 'LA', 'P'):
                    img = img.convert('RGB')

                # Resize to max 800x600 while maintaining aspect ratio
                img.thumbnail((800, 600), Image.Resampling.LANCZOS)
                img.save(file_path, 'JPEG', quality=85, optimize=True)
        except Exception as e:
            current_app.logger.error(f"Error processing image: {e}")

        return filename
    return None

@bp.route('/')
@login_required
def index():
    """Admin index - redirect to dashboard"""
    if not current_user.is_admin():
        return redirect(url_for('main.index'))
    return redirect(url_for('admin.dashboard'))

@bp.route('/dashboard')
@login_required
def dashboard():
    """Admin dashboard - Enhanced with comprehensive statistics and charts"""
    if not current_user.is_admin():
        return redirect(url_for('main.index'))

    # Performance: Use single query with aggregation for better performance
    from sqlalchemy import func, case, desc, extract, and_
    from datetime import datetime, timedelta, timezone

    # Current time and date (UTC for database operations)
    now = datetime.now(timezone.utc)
    today_start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)

    # Dashboard stats query
    stats_query = db.session.query(
        func.count(MenuItem.item_id).label('total_menu_items'),
        func.sum(case((MenuItem.status == 'available', 1), else_=0)).label('active_menu_items'),
        func.sum(case((MenuItem.status == 'out_of_stock', 1), else_=0)).label('out_of_stock_items')
    ).first()

    # Separate query for categories (usually small dataset)
    total_categories = Category.query.filter_by(is_active=True).count()
    
    # Staff count - Use the dedicated method for accurate counting
    staff_count = User.get_active_staff_count()

    # Tables status based on active QR codes and their table status
    # Get all tables that have active QR codes
    tables_with_qr = db.session.query(Table.table_id).join(
        QRCode, QRCode.table_id == Table.table_id
    ).filter(
        QRCode.is_active == True,
        QRCode.qr_type == 'menu'
    ).distinct().all()
    
    # Extract table IDs from result
    table_ids = [table.table_id for table in tables_with_qr]
    
    if table_ids:
        # If we have tables with QR codes, get their stats
        tables_data = db.session.query(
            func.count(Table.table_id).label('total_tables'),
            func.sum(case((Table.status == 'available', 1), else_=0)).label('available_tables'),
            func.sum(case((Table.status == 'occupied', 1), else_=0)).label('occupied_tables')
        ).filter(Table.table_id.in_(table_ids)).first()
    else:
        # If no tables with QR codes, use None to trigger fallback
        tables_data = None

    # Today's orders and revenue - only completed orders
    today_orders_query = db.session.query(
        func.count(Order.order_id).label('order_count'),
        func.sum(Order.total_amount).label('total_revenue')
    ).filter(
        Order.order_time >= today_start,
        Order.status == 'completed'
    ).first()
    
    # Recent orders for last 7 days
    week_orders_count = Order.query.filter(
        Order.order_time >= now - timedelta(days=7)
    ).count()
    
    # Monthly revenue (current month) - only completed orders
    month_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    monthly_revenue = db.session.query(
        func.sum(Order.total_amount)
    ).filter(
        Order.order_time >= month_start,
        Order.status == 'completed'
    ).scalar() or 0
    
    # Prepare today's order data
    todays_orders = today_orders_query.order_count or 0
    todays_revenue = round(float(today_orders_query.total_revenue or 0), 2)
    
    # Revenue data for chart (last 7 days)
    revenue_data = {'labels': [], 'orders': [], 'revenue': []}
    
    for i in range(6, -1, -1):
        day_date = now - timedelta(days=i)
        day_start = datetime(day_date.year, day_date.month, day_date.day, tzinfo=timezone.utc)
        day_end = day_start + timedelta(days=1)
        
        # Get orders and revenue for this day - only completed orders
        day_data = db.session.query(
            func.count(Order.order_id).label('order_count'),
            func.sum(Order.total_amount).label('revenue')
        ).filter(
            Order.order_time >= day_start,
            Order.order_time < day_end,
            Order.status == 'completed'
        ).first()
        
        # Format date as day name
        day_label = day_date.strftime('%a')
        revenue_data['labels'].append(day_label)
        revenue_data['orders'].append(day_data.order_count or 0)
        revenue_data['revenue'].append(float(day_data.revenue or 0))
    
    # Popular categories data for chart
    category_data = {'labels': [], 'data': []}
    
    # Get top 5 categories by order count in the past month
    top_categories = db.session.query(
        Category.name,
        func.count(OrderItem.order_item_id).label('item_count')
    ).join(
        MenuItem, MenuItem.item_id == OrderItem.item_id
    ).join(
        Category, Category.category_id == MenuItem.category_id
    ).join(
        Order, Order.order_id == OrderItem.order_id
    ).filter(
        Order.order_time >= now - timedelta(days=30)
    ).group_by(
        Category.category_id
    ).order_by(
        desc('item_count')
    ).limit(5).all()
    
    for cat in top_categories:
        category_data['labels'].append(cat.name)
        category_data['data'].append(cat.item_count)
    
    # Order status distribution
    status_data = {'labels': ['New', 'Processing', 'Completed', 'Rejected'], 'data': [], 'colors': []}
    status_colors = {
        'new': 'rgba(59, 130, 246, 0.8)',        # Blue
        'processing': 'rgba(245, 158, 11, 0.8)',  # Yellow/Orange
        'completed': 'rgba(16, 185, 129, 0.8)',   # Green
        'rejected': 'rgba(239, 68, 68, 0.8)'      # Red
    }
    
    for status in status_data['labels']:
        count = Order.query.filter(
            Order.status == status.lower(),
            Order.order_time >= now - timedelta(days=7)
        ).count()
        status_data['data'].append(count)
        status_data['colors'].append(status_colors[status.lower()])
    
    # Prepare stats dictionary
    # Count total QR codes for tables
    qr_code_count = QRCode.query.filter_by(is_active=True, qr_type='menu').count()
    
    # Force sync all table statuses before generating stats
    # This will set tables with active orders to 'occupied' and others to 'available'
    print("Dashboard view: Updating all table statuses before rendering")
    Table.update_all_table_statuses()
    
    # If no tables with QR codes found or no tables in result, get total count of all tables
    if not tables_data or not tables_data.total_tables:
        # Explicit query for all tables
        all_tables_data = db.session.query(
            func.count(Table.table_id).label('total_tables'),
        ).first()
        
        total_tables = all_tables_data.total_tables or 0
        print(f"Using all_tables_data count: {total_tables}")
    else:
        total_tables = tables_data.total_tables or 0
        print(f"Using tables_with_qr count: {total_tables}")
    
    # Double check - get full table count for validation
    actual_total = Table.query.count()
    print(f"Actual total tables in database: {actual_total}")
    
    # Direct query for occupied tables - should match get_occupied_tables_count
    direct_occupied_count = Table.query.filter_by(status='occupied').count()
    print(f"Direct query occupied tables: {direct_occupied_count}")
    
    # Get accurate count of occupied tables using our newly fixed method
    # This checks both table status and active orders in a single query
    occupied_tables = Table.get_occupied_tables_count()
    print(f"Final occupied tables count: {occupied_tables}")
    
    # Ensure total_tables is at least the number of occupied tables
    if total_tables < occupied_tables:
        print(f"Warning: total_tables ({total_tables}) < occupied_tables ({occupied_tables}), adjusting")
        total_tables = actual_total
    
    # Calculate available tables as the difference between total and occupied
    # This ensures consistency between the numbers
    available_tables = max(0, total_tables - occupied_tables)
    print(f"Available tables: {available_tables}")
    
    stats = {
        'total_menu_items': stats_query.total_menu_items or 0,
        'active_menu_items': stats_query.active_menu_items or 0,
        'total_categories': total_categories,
        'out_of_stock_items': stats_query.out_of_stock_items or 0,
        'recent_orders': week_orders_count,
        'todays_orders': todays_orders,
        'todays_revenue': todays_revenue,
        'monthly_revenue': round(float(monthly_revenue), 2),
        'staff_count': staff_count,
        'total_tables': total_tables,
        'available_tables': available_tables,
        'occupied_tables': occupied_tables,
        'qr_code_count': qr_code_count
    }
    
    # Get recent orders for display
    recent_orders = []
    orders_query = Order.query.order_by(Order.order_time.desc()).limit(10)
    
    for order in orders_query:
        # Get customer name
        customer_name = order.customer.name if order.customer else 'Guest'
        
        # Get order type based on whether it has a table
        order_type = 'Dine-in' if order.table else 'Takeaway'
        
        recent_orders.append({
            'id': order.order_id,
            'name': customer_name,
            'qr_number': order.table.table_number if order.table else 'N/A',
            'date': order.order_time.strftime('%d %b %Y, %H:%M'),
            'type': order_type,
            'status': order.status.capitalize(),
            'total': f"{float(order.total_amount):.2f} EGP"
        })

    # Ensure admin_name is properly set and extract first name for a friendlier greeting
    if current_user and current_user.name:
        admin_name = current_user.name
        # Extract first name for a more personal greeting
        admin_first_name = admin_name.split()[0] if admin_name and ' ' in admin_name else admin_name
    else:
        admin_name = "Admin"
        admin_first_name = "Admin"
    
    # Time-based greeting (based on local time)
    hour = now.hour
    if 5 <= hour < 12:
        greeting = "Good morning"
    elif 12 <= hour < 18:
        greeting = "Good afternoon"
    else:
        greeting = "Good evening"
    
    return render_template('dashboard.html', 
                           stats=stats, 
                           now=now, 
                           recent_orders=recent_orders, 
                           revenue_data=revenue_data,
                           category_data=category_data,
                           status_data=status_data,
                           current_user=current_user,
                           admin_name=admin_name,
                           admin_first_name=admin_first_name,
                           greeting=greeting)

@bp.route('/orders')
@login_required
def orders():
    """Admin orders page - Optimized with pagination"""
    if not current_user.is_admin():
        return redirect(url_for('main.index'))

    # Performance: Add pagination and optimize query
    page = request.args.get('page', 1, type=int)
    per_page = 20  # Configurable items per page

    # Performance: Use join to get customer names and table info in single query
    orders_query = Order.query.join(User, Order.user_id == User.user_id).outerjoin(Table).order_by(Order.order_time.desc())

    # Performance: Paginate results to avoid loading all orders
    orders_pagination = orders_query.paginate(
        page=page, per_page=per_page, error_out=False
    )

    # Format orders for template
    formatted_orders = []
    for order in orders_pagination.items:
        # Debug: Let's see what we're getting
        customer_name = "Unknown"
        if hasattr(order, 'customer') and order.customer:
            customer_name = order.customer.name
        else:
            # Fallback: try to get the user directly
            user = User.query.get(order.user_id)
            if user:
                customer_name = user.name
        
        formatted_orders.append({
            'id': order.order_id,  # Keep as integer for JS to handle correctly
            'name': customer_name,
            'qr_number': f"#{order.table.table_number}" if order.table else "N/A",
            'date': order.order_time.strftime('%d %b %Y'),
            'type': 'Order',  # Could be enhanced based on order items
            'status': order.status.title(),
            'total': f"{order.total_amount:.2f} EGP"
        })

    return render_template('orders.html',
                         orders=formatted_orders,
                         pagination=orders_pagination,
                         total_orders=Order.query.count(),
                         pending_orders=Order.query.filter(Order.status.in_(['new', 'processing'])).count(),
                         completed_orders=Order.query.filter_by(status='completed').count())

@bp.route('/analytics/revenue')
@login_required
def revenue_analytics():
    """Advanced revenue analytics dashboard"""
    if not current_user.is_admin():
        return redirect(url_for('main.index'))

    # Get time period from request args
    period = request.args.get('period', 'month')

    # Calculate date ranges
    now = datetime.now()

    if period == 'today':
        start_date = datetime(now.year, now.month, now.day)
        end_date = start_date + timedelta(days=1)
    elif period == 'week':
        start_date = now - timedelta(days=7)
        end_date = now
    elif period == 'month':
        start_date = datetime(now.year, now.month, 1)
        end_date = now
    elif period == 'quarter':
        quarter_start_month = ((now.month - 1) // 3) * 3 + 1
        start_date = datetime(now.year, quarter_start_month, 1)
        end_date = now
    elif period == 'year':
        start_date = datetime(now.year, 1, 1)
        end_date = now
    else:  # all time
        start_date = None
        end_date = now

    # Build base query - only include completed orders for revenue calculations
    base_query = Order.query.filter(Order.status == 'completed')
    if start_date:
        base_query = base_query.filter(Order.order_time >= start_date)
    base_query = base_query.filter(Order.order_time <= end_date)

    # Revenue metrics
    revenue_data = calculate_revenue_metrics(base_query, start_date, end_date, period)

    # Customer analytics
    customer_data = calculate_customer_analytics(base_query, start_date, end_date)

    # Product performance
    product_data = calculate_product_performance(base_query, start_date, end_date)

    # Time-based analytics
    time_data = calculate_time_analytics(base_query, start_date, end_date, period)

    return render_template('revenue_analytics.html',
                         revenue_data=revenue_data,
                         customer_data=customer_data,
                         product_data=product_data,
                         time_data=time_data,
                         period=period)

@bp.route('/analytics/customers')
@login_required
def customer_analytics():
    """Customer behavior analytics dashboard"""
    if not current_user.is_admin():
        return redirect(url_for('main.index'))

    # Get time period from request args
    period = request.args.get('period', 'month')

    # Calculate date ranges
    now = datetime.now()

    if period == 'week':
        start_date = now - timedelta(days=7)
    elif period == 'month':
        start_date = datetime(now.year, now.month, 1)
    elif period == 'quarter':
        quarter_start_month = ((now.month - 1) // 3) * 3 + 1
        start_date = datetime(now.year, quarter_start_month, 1)
    elif period == 'year':
        start_date = datetime(now.year, 1, 1)
    else:  # all time
        start_date = None

    end_date = now

    # Build base query - only include completed orders for analytics
    base_query = Order.query.filter(Order.status == 'completed')
    if start_date:
        base_query = base_query.filter(Order.order_time >= start_date)
    base_query = base_query.filter(Order.order_time <= end_date)

    # Customer behavior metrics
    behavior_data = calculate_detailed_customer_behavior(base_query, start_date, end_date)

    # Customer segmentation
    segmentation_data = calculate_customer_segmentation(base_query, start_date, end_date)

    # Order patterns
    pattern_data = calculate_order_patterns(base_query, start_date, end_date)

    # Customer lifecycle
    lifecycle_data = calculate_customer_lifecycle(start_date, end_date)

    return render_template('customer_analytics.html',
                         behavior_data=behavior_data,
                         segmentation_data=segmentation_data,
                         pattern_data=pattern_data,
                         lifecycle_data=lifecycle_data,
                         period=period)

@bp.route('/analytics/popular-items')
@login_required
def popular_items_analytics():
    """Popular items analytics page with time period filtering"""
    if not current_user.is_admin():
        return redirect(url_for('main.index'))

    # Get time period from request args
    period = request.args.get('period', 'all')

    # Calculate date range based on period
    end_date = datetime.now()
    start_date = None
    
    if period == 'today':
        start_date = end_date.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == 'week':
        start_date = end_date - timedelta(days=7)
    elif period == 'month':
        start_date = end_date.replace(day=1)
    elif period == 'custom':
        # Parse custom date range
        try:
            start_date = datetime.strptime(request.args.get('start_date'), '%Y-%m-%d')
            end_date = datetime.strptime(request.args.get('end_date'), '%Y-%m-%d')
            # Set end_date to end of day
            end_date = end_date.replace(hour=23, minute=59, second=59)
        except (ValueError, TypeError):
            # If parsing fails, fall back to all-time
            pass

    # Get popular items with counts, filtered by date range if applicable
    if start_date and period != 'all':
        popular_items_data = MenuItem.get_popular_items_with_counts(limit=15, start_date=start_date, end_date=end_date)
    else:
        popular_items_data = MenuItem.get_popular_items_with_counts(limit=15)

    # Format data for template
    analytics_data = []
    for item, count in popular_items_data:
        analytics_data.append({
            'name': item.name,
            'category': item.category.name,
            'price': float(item.price),
            'total_ordered': int(count),
            'revenue': float(item.price) * int(count),
            'image_url': item.image_url
        })

    # Handle empty analytics data
    if not analytics_data:
        flash('No data available for the selected time period.', 'info')
        
    # Calculate totals
    total_orders = sum(item['total_ordered'] for item in analytics_data) if analytics_data else 0
    total_revenue = sum(item['revenue'] for item in analytics_data) if analytics_data else 0

    return render_template('popular_items_analytics.html',
                         analytics_data=analytics_data,
                         total_orders=total_orders,
                         total_revenue=total_revenue)

@bp.route('/services')
@login_required
def services():
    """Admin services management page"""
    if not current_user.is_admin():
        return redirect(url_for('main.index'))

    # Get all services from database
    services = Service.query.order_by(Service.display_order, Service.name).all()
    
    return render_template('services_management.html', services=services)

@bp.route('/services/add', methods=['GET', 'POST'])
@login_required
def add_service():
    """Add new service"""
    if not current_user.is_admin():
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        try:
            # Get form data
            name = request.form.get('name', '').strip()
            icon = request.form.get('icon', 'fas fa-concierge-bell').strip()
            description = request.form.get('description', '').strip()
            is_active = 'is_active' in request.form
            display_order = int(request.form.get('display_order', 0))

            # Validate required fields
            if not name:
                flash('Service name is required', 'error')
                return render_template('add_service.html')

            # Create new service
            service = Service(
                name=name,
                icon=icon,
                description=description if description else None,
                is_active=is_active,
                display_order=display_order
            )

            db.session.add(service)
            db.session.commit()

            flash(f'Service "{name}" added successfully!', 'success')
            return redirect(url_for('admin.services'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error adding service: {str(e)}', 'error')
            return render_template('add_service.html')

    return render_template('add_service.html')

@bp.route('/services/edit/<int:service_id>', methods=['GET', 'POST'])
@login_required
def edit_service(service_id):
    """Edit existing service"""
    if not current_user.is_admin():
        return redirect(url_for('main.index'))

    service = Service.query.get_or_404(service_id)

    if request.method == 'POST':
        try:
            # Get form data
            name = request.form.get('name', '').strip()
            icon = request.form.get('icon', 'fas fa-concierge-bell').strip()
            description = request.form.get('description', '').strip()
            is_active = 'is_active' in request.form
            display_order = int(request.form.get('display_order', 0))

            # Validate required fields
            if not name:
                flash('Service name is required', 'error')
                return render_template('edit_service.html', service=service)

            # Update service
            service.name = name
            service.icon = icon
            service.description = description if description else None
            service.is_active = is_active
            service.display_order = display_order
            service.updated_at = datetime.utcnow()

            db.session.commit()

            flash(f'Service "{name}" updated successfully!', 'success')
            return redirect(url_for('admin.services'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error updating service: {str(e)}', 'error')
            return render_template('edit_service.html', service=service)

    return render_template('edit_service.html', service=service)

@bp.route('/services/delete/<int:service_id>', methods=['POST'])
@login_required
def delete_service(service_id):
    """Delete service"""
    if not current_user.is_admin():
        return redirect(url_for('main.index'))

    try:
        service = Service.query.get_or_404(service_id)
        service_name = service.name

        # Check if service has any requests (handle relationship error gracefully)
        try:
            request_count = service.service_requests.count()
            if request_count > 0:
                flash(f'Cannot delete service "{service_name}" - it has {request_count} associated requests', 'error')
                return redirect(url_for('admin.services'))
        except Exception:
            # If relationship check fails, proceed with deletion (likely no foreign key constraint)
            pass

        db.session.delete(service)
        db.session.commit()

        flash(f'Service "{service_name}" deleted successfully!', 'success')

    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting service: {str(e)}', 'error')

    return redirect(url_for('admin.services'))

@bp.route('/services/toggle/<int:service_id>', methods=['POST'])
@login_required
def toggle_service(service_id):
    """Toggle service active status"""
    if not current_user.is_admin():
        return redirect(url_for('main.index'))

    try:
        service = Service.query.get_or_404(service_id)
        service.is_active = not service.is_active
        service.updated_at = datetime.utcnow()
        
        db.session.commit()

        status = "activated" if service.is_active else "deactivated"
        flash(f'Service "{service.name}" {status} successfully!', 'success')

    except Exception as e:
        db.session.rollback()
        flash(f'Error updating service: {str(e)}', 'error')

    return redirect(url_for('admin.services'))

@bp.route('/qr-codes')
@login_required
def qr_codes():
    """Admin QR codes page"""
    if not current_user.is_admin():
        return redirect(url_for('main.index'))

    # Get all tables with their QR codes
    tables = Table.query.all()
    
    # Get QR code statistics
    qr_codes = QRCode.query.all()
    active_qr_codes = len([qr for qr in qr_codes if qr.is_active])
    table_qr_codes = len([qr for qr in qr_codes if qr.qr_type == 'menu'])

    return render_template('qr_codes.html', 
                         tables=tables,
                         qr_codes=qr_codes,
                         active_qr_codes=active_qr_codes,
                         table_qr_codes=table_qr_codes)


@bp.route('/profile')
@login_required
def profile():
    """Admin profile page"""
    if not current_user.is_admin():
        return redirect(url_for('main.index'))

    # Sample profile data - replace with actual user data
    profile_data = {
        'name': 'Mohammed Shouman',
        'email': 'm.shouman@gmail.com',
        'phone': '+972 9944556633',
        'avatar': None,  # Will use default avatar
        'role': 'Administrator',
        'joined_date': '2024-01-15',
        'last_login': '2024-06-22'
    }

    return render_template('profile.html', profile=profile_data)

# Menu Management Routes

@bp.route('/menu')
@login_required
def menu_management():
    """Menu management page - Optimized with eager loading"""
    if not current_user.is_admin():
        return redirect(url_for('main.index'))

    # Performance: Use eager loading to avoid N+1 queries
    from sqlalchemy.orm import joinedload

    categories = Category.query.filter_by(is_active=True).order_by(Category.display_order).all()

    # Performance: Eager load category relationship to avoid N+1 queries
    menu_items = MenuItem.query.options(joinedload(MenuItem.category)).join(Category).order_by(
        Category.display_order, MenuItem.name
    ).all()

    return render_template('menu_management.html', categories=categories, menu_items=menu_items)

@bp.route('/menu/categories')
@login_required
def category_management():
    """Category management page"""
    if not current_user.is_admin():
        return redirect(url_for('main.index'))

    categories = Category.query.order_by(Category.display_order).all()
    active_categories = Category.query.filter_by(is_active=True).count()
    total_items = MenuItem.query.count()
    
    return render_template('category_management.html', 
                         categories=categories,
                         active_categories=active_categories,
                         total_items=total_items)

@bp.route('/menu/categories/add', methods=['GET', 'POST'])
@login_required
def add_category():
    """Add new category"""
    if not current_user.is_admin():
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        display_order = request.form.get('display_order', type=int)

        if not name:
            flash('Category name is required', 'error')
            return render_template('add_category.html')

        # Check if category already exists
        if Category.query.filter_by(name=name).first():
            flash('Category with this name already exists', 'error')
            return render_template('add_category.html')

        # Set default display order if not provided
        if display_order is None:
            max_order = db.session.query(db.func.max(Category.display_order)).scalar() or 0
            display_order = max_order + 1

        category = Category(
            name=name,
            description=description,
            display_order=display_order
        )

        try:
            db.session.add(category)
            db.session.commit()
            flash('Category added successfully', 'success')
            return redirect(url_for('admin.category_management'))
        except Exception as e:
            db.session.rollback()
            flash('Error adding category', 'error')
            current_app.logger.error(f"Error adding category: {e}")

    return render_template('add_category.html',
                         existing_categories=Category.query.count())

@bp.route('/menu/categories/<int:category_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_category(category_id):
    """Edit category"""
    if not current_user.is_admin():
        return redirect(url_for('main.index'))

    category = Category.query.get_or_404(category_id)

    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        display_order = request.form.get('display_order', type=int)
        is_active = request.form.get('is_active') == 'on'

        if not name:
            flash('Category name is required', 'error')
            return render_template('edit_category.html', 
                                 category=category,
                                 menu_items_count=MenuItem.query.filter_by(category_id=category_id).count())

        # Check if another category with this name exists
        existing = Category.query.filter(Category.name == name, Category.category_id != category_id).first()
        if existing:
            flash('Category with this name already exists', 'error')
            return render_template('edit_category.html', 
                                 category=category,
                                 menu_items_count=MenuItem.query.filter_by(category_id=category_id).count())

        category.name = name
        category.description = description
        category.display_order = display_order or category.display_order
        category.is_active = is_active

        try:
            db.session.commit()
            flash('Category updated successfully', 'success')
            return redirect(url_for('admin.category_management'))
        except Exception as e:
            db.session.rollback()
            flash('Error updating category', 'error')
            current_app.logger.error(f"Error updating category: {e}")

    return render_template('edit_category.html', 
                         category=category,
                         menu_items_count=MenuItem.query.filter_by(category_id=category_id).count())

@bp.route('/menu/categories/<int:category_id>/delete', methods=['POST'])
@login_required
def delete_category(category_id):
    """Delete category"""
    if not current_user.is_admin():
        return redirect(url_for('main.index'))

    category = Category.query.get_or_404(category_id)

    # Check if category has menu items
    if category.menu_items.count() > 0:
        flash('Cannot delete category with menu items. Please move or delete items first.', 'error')
        return redirect(url_for('admin.category_management'))

    try:
        db.session.delete(category)
        db.session.commit()
        flash('Category deleted successfully', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error deleting category', 'error')
        current_app.logger.error(f"Error deleting category: {e}")

    return redirect(url_for('admin.category_management'))

# Menu Item Management Routes

@bp.route('/menu/items/add', methods=['GET', 'POST'])
@login_required
def add_menu_item():
    """Add new menu item"""
    if not current_user.is_admin():
        return redirect(url_for('main.index'))

    categories = Category.query.filter_by(is_active=True).order_by(Category.display_order).all()

    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        price = request.form.get('price', type=float)
        category_id = request.form.get('category_id', type=int)
        stock = request.form.get('stock', type=int, default=0)
        status = request.form.get('status', 'available')

        # Get discount information
        discount_percentage = request.form.get('discount_percentage', type=float)
        
        # Handle discount logic
        if discount_percentage and discount_percentage > 0:
            if discount_percentage > 95:
                flash('Discount percentage cannot exceed 95%', 'error')
                return render_template('add_menu_item.html', categories=categories)
        
        # Get nutritional information
        ingredients = request.form.get('ingredients')
        calories = request.form.get('calories', type=int)
        preparation_time = request.form.get('preparation_time', type=int)
        allergens = request.form.get('allergens')
        serving_size = request.form.get('serving_size')
        dietary_info = request.form.get('dietary_info')

        # Get special options
        is_featured = 'is_featured' in request.form
        is_spicy = 'is_spicy' in request.form
        is_vegetarian = 'is_vegetarian' in request.form
        is_vegan = 'is_vegan' in request.form

        if not name or not price or not category_id:
            flash('Name, price, and category are required', 'error')
            return render_template('add_menu_item.html', categories=categories)

        # Check if item already exists
        if MenuItem.query.filter_by(name=name).first():
            flash('Menu item with this name already exists', 'error')
            return render_template('add_menu_item.html', categories=categories)

        # Handle image upload
        image_filename = None
        if 'image' in request.files:
            file = request.files['image']
            if file.filename:
                image_filename = save_menu_image(file)
                if not image_filename:
                    flash('Invalid image file. Please use PNG, JPG, JPEG, or GIF.', 'error')
                    return render_template('add_menu_item.html', categories=categories)

        menu_item = MenuItem(
            name=name,
            description=description,
            price=price,
            category_id=category_id,
            image_url=image_filename,
            stock=stock,
            status=status,
            ingredients=ingredients,
            calories=calories,
            preparation_time=preparation_time,
            allergens=allergens,
            serving_size=serving_size,
            dietary_info=dietary_info,
            discount_percentage=discount_percentage or 0.00,
            is_featured=is_featured,
            is_spicy=is_spicy,
            is_vegetarian=is_vegetarian,
            is_vegan=is_vegan
        )
        
        # Apply discount if provided
        if discount_percentage and discount_percentage > 0:
            menu_item.apply_discount(discount_percentage)

        try:
            db.session.add(menu_item)
            db.session.commit()
            flash('Menu item added successfully', 'success')
            return redirect(url_for('admin.menu_management'))
        except Exception as e:
            db.session.rollback()
            flash('Error adding menu item', 'error')
            current_app.logger.error(f"Error adding menu item: {e}")

    return render_template('add_menu_item.html', 
                         categories=categories,
                         total_items=MenuItem.query.count())

@bp.route('/menu/items/<int:item_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_menu_item(item_id):
    """Edit menu item"""
    if not current_user.is_admin():
        return redirect(url_for('main.index'))

    menu_item = MenuItem.query.get_or_404(item_id)
    categories = Category.query.filter_by(is_active=True).order_by(Category.display_order).all()

    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        price = request.form.get('price', type=float)
        category_id = request.form.get('category_id', type=int)
        stock = request.form.get('stock', type=int)
        status = request.form.get('status')

        # Get discount information
        discount_percentage = request.form.get('discount_percentage', type=float)
        
        # Handle discount logic
        if discount_percentage and discount_percentage > 0:
            if discount_percentage > 95:
                flash('Discount percentage cannot exceed 95%', 'error')
                return render_template('edit_menu_item.html', menu_item=menu_item, categories=categories)

        # Get nutritional information
        ingredients = request.form.get('ingredients')
        calories = request.form.get('calories', type=int)
        preparation_time = request.form.get('preparation_time', type=int)
        allergens = request.form.get('allergens')
        serving_size = request.form.get('serving_size')
        dietary_info = request.form.get('dietary_info')

        # Get special options
        is_featured = 'is_featured' in request.form
        is_spicy = 'is_spicy' in request.form
        is_vegetarian = 'is_vegetarian' in request.form
        is_vegan = 'is_vegan' in request.form

        if not name or not price or not category_id:
            flash('Name, price, and category are required', 'error')
            return render_template('edit_menu_item.html', menu_item=menu_item, categories=categories)

        # Check if another item with this name exists
        existing = MenuItem.query.filter(MenuItem.name == name, MenuItem.item_id != item_id).first()
        if existing:
            flash('Menu item with this name already exists', 'error')
            return render_template('edit_menu_item.html', menu_item=menu_item, categories=categories)

        # Handle image removal
        remove_image = request.form.get('remove_image')
        if remove_image == '1':
            # Delete current image if exists
            if menu_item.image_url:
                old_image_path = os.path.join(current_app.root_path, current_app.config['MENU_IMAGE_FOLDER'], menu_item.image_url)
                if os.path.exists(old_image_path):
                    try:
                        os.remove(old_image_path)
                    except Exception as e:
                        current_app.logger.error(f"Error deleting old image: {e}")
            menu_item.image_url = None

        # Handle image upload
        elif 'image' in request.files:
            file = request.files['image']
            if file.filename:
                # Delete old image if exists
                if menu_item.image_url:
                    old_image_path = os.path.join(current_app.root_path, current_app.config['MENU_IMAGE_FOLDER'], menu_item.image_url)
                    if os.path.exists(old_image_path):
                        try:
                            os.remove(old_image_path)
                        except Exception as e:
                            current_app.logger.error(f"Error deleting old image: {e}")

                # Save new image
                image_filename = save_menu_image(file)
                if image_filename:
                    menu_item.image_url = image_filename
                else:
                    flash('Invalid image file. Please use PNG, JPG, JPEG, or GIF.', 'error')
                    return render_template('edit_menu_item.html', menu_item=menu_item, categories=categories)

        menu_item.name = name
        menu_item.description = description
        menu_item.price = price
        menu_item.category_id = category_id
        menu_item.stock = stock or 0
        menu_item.status = status
        menu_item.ingredients = ingredients
        menu_item.calories = calories
        menu_item.preparation_time = preparation_time
        menu_item.allergens = allergens
        menu_item.serving_size = serving_size
        menu_item.dietary_info = dietary_info

        # Update special options
        menu_item.is_featured = is_featured
        menu_item.is_spicy = is_spicy
        menu_item.is_vegetarian = is_vegetarian
        menu_item.is_vegan = is_vegan
        
        # Handle discount updates
        if discount_percentage and discount_percentage > 0:
            menu_item.apply_discount(discount_percentage)
        elif menu_item.discount_percentage and menu_item.discount_percentage > 0:
            # Clear discount if percentage is 0 or empty
            menu_item.remove_discount()

        try:
            db.session.commit()
            flash('Menu item updated successfully', 'success')
            return redirect(url_for('admin.menu_management'))
        except Exception as e:
            db.session.rollback()
            flash('Error updating menu item', 'error')
            current_app.logger.error(f"Error updating menu item: {e}")

    return render_template('edit_menu_item.html', menu_item=menu_item, categories=categories)

@bp.route('/menu/items/<int:item_id>/delete', methods=['POST'])
@login_required
def delete_menu_item(item_id):
    """Delete menu item"""
    if not current_user.is_admin():
        return redirect(url_for('main.index'))

    menu_item = MenuItem.query.get_or_404(item_id)

    # Delete associated image
    if menu_item.image_url:
        image_path = os.path.join(current_app.root_path, current_app.config['MENU_IMAGE_FOLDER'], menu_item.image_url)
        if os.path.exists(image_path):
            try:
                os.remove(image_path)
            except Exception as e:
                current_app.logger.error(f"Error deleting image: {e}")

    try:
        db.session.delete(menu_item)
        db.session.commit()
        flash('Menu item deleted successfully', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error deleting menu item', 'error')
        current_app.logger.error(f"Error deleting menu item: {e}")

    return redirect(url_for('admin.menu_management'))

# ======================== REWARD MANAGEMENT ROUTES ========================

@bp.route('/rewards')
@login_required
def rewards_management():
    """Admin rewards management dashboard"""
    if not current_user.is_admin():
        return redirect(url_for('main.index'))
    
    # Get all rewards with their statistics
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    rewards = RewardItem.query.order_by(RewardItem.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    # Get reward statistics
    total_rewards = RewardItem.query.count()
    active_rewards = RewardItem.query.filter_by(status='active').count()
    inactive_rewards = RewardItem.query.filter_by(status='inactive').count()
    
    # Get redemption statistics
    total_redemptions = RewardRedemption.query.count()
    recent_redemptions = RewardRedemption.query.order_by(
        RewardRedemption.redemption_date.desc()
    ).limit(10).all()
    
    return render_template('rewards_management.html',
                         rewards=rewards,
                         total_rewards=total_rewards,
                         active_rewards=active_rewards,
                         inactive_rewards=inactive_rewards,
                         total_redemptions=total_redemptions,
                         recent_redemptions=recent_redemptions,
                         datetime=datetime)

@bp.route('/rewards/add', methods=['GET', 'POST'])
@login_required
def add_reward():
    """Add new reward item"""
    if not current_user.is_admin():
        return redirect(url_for('main.index'))
    
    if request.method == 'POST':
        try:
            reward = RewardItem(
                name=request.form.get('name'),
                description=request.form.get('description'),
                points_required=int(request.form.get('points_required')),
                category=request.form.get('category'),
                status=request.form.get('status', 'active'),
                item_id=int(request.form.get('item_id')) if request.form.get('item_id') else None,
                expiry_date=datetime.strptime(request.form.get('expiry_date'), '%Y-%m-%d') if request.form.get('expiry_date') else None
            )
            
            db.session.add(reward)
            db.session.commit()
            
            flash('Reward added successfully!', 'success')
            return redirect(url_for('admin.rewards_management'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding reward: {str(e)}', 'error')
    
    # Get menu items for linking
    menu_items = MenuItem.query.filter_by(status='available').all()
    categories = ['Cakes & Sweets', 'Beverages', 'Main Course', 'Appetizers', 'Desserts', 'Special Offers']
    
    return render_template('add_reward.html',
                         menu_items=menu_items,
                         categories=categories,
                         existing_rewards=RewardItem.query.count())

@bp.route('/rewards/edit/<int:reward_id>', methods=['GET', 'POST'])
@login_required
def edit_reward(reward_id):
    """Edit existing reward"""
    if not current_user.is_admin():
        return redirect(url_for('main.index'))
    
    reward = RewardItem.query.get_or_404(reward_id)
    
    if request.method == 'POST':
        try:
            reward.name = request.form.get('name')
            reward.description = request.form.get('description')
            reward.points_required = int(request.form.get('points_required'))
            reward.category = request.form.get('category')
            reward.status = request.form.get('status')
            reward.item_id = int(request.form.get('item_id')) if request.form.get('item_id') else None
            reward.expiry_date = datetime.strptime(request.form.get('expiry_date'), '%Y-%m-%d') if request.form.get('expiry_date') else None
            
            db.session.commit()
            
            flash('Reward updated successfully!', 'success')
            return redirect(url_for('admin.rewards_management'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating reward: {str(e)}', 'error')
    
    # Get menu items for linking
    menu_items = MenuItem.query.filter_by(status='available').all()
    categories = ['Cakes & Sweets', 'Beverages', 'Main Course', 'Appetizers', 'Desserts', 'Special Offers']
    
    return render_template('edit_reward.html',
                         reward=reward,
                         menu_items=menu_items,
                         categories=categories)

@bp.route('/rewards/delete/<int:reward_id>', methods=['POST'])
@login_required
def delete_reward(reward_id):
    """Delete reward item"""
    if not current_user.is_admin():
        return redirect(url_for('main.index'))
    
    try:
        reward = RewardItem.query.get_or_404(reward_id)
        
        # Check if reward has been redeemed
        redemptions = RewardRedemption.query.filter_by(reward_id=reward_id).count()
        
        if redemptions > 0:
            # Instead of deleting, mark as inactive
            reward.status = 'inactive'
            db.session.commit()
            flash('Reward marked as inactive (has redemption history)', 'warning')
        else:
            db.session.delete(reward)
            db.session.commit()
            flash('Reward deleted successfully!', 'success')
            
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting reward: {str(e)}', 'error')

    return redirect(url_for('admin.rewards_management'))

@bp.route('/rewards/toggle/<int:reward_id>', methods=['POST'])
@login_required
def toggle_reward_status(reward_id):
    """Toggle reward active/inactive status"""
    if not current_user.is_admin():
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    try:
        reward = RewardItem.query.get_or_404(reward_id)
        reward.status = 'inactive' if reward.status == 'active' else 'active'
        db.session.commit()
        
        return jsonify({
            'success': True,
            'status': reward.status,
            'message': f'Reward {reward.status}'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Error toggling reward status: {str(e)}'
        }), 500

@bp.route('/rewards/bulk-update', methods=['POST'])
@login_required
def bulk_update_rewards():
    """Bulk update rewards (status, category, etc.)"""
    if not current_user.is_admin():
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    try:
        data = request.get_json()
        reward_ids = data.get('reward_ids', [])
        action = data.get('action')
        value = data.get('value')
        
        if not reward_ids or not action:
            return jsonify({'success': False, 'message': 'Missing required parameters'}), 400
        
        rewards = RewardItem.query.filter(RewardItem.reward_id.in_(reward_ids)).all()
        
        for reward in rewards:
            if action == 'status':
                reward.status = value
            elif action == 'category':
                reward.category = value
            elif action == 'points':
                reward.points_required = int(value)
        
        db.session.commit();
        
        return jsonify({
            'success': True,
            'message': f'Updated {len(rewards)} rewards'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Error updating rewards: {str(e)}'
        }), 500

# ======================== END REWARD MANAGEMENT ROUTES

# ======================== LOYALTY MANAGEMENT ROUTES ========================

@bp.route('/loyalty-management')
@login_required
def loyalty_management():
    """Admin loyalty program management dashboard"""
    if not current_user.is_admin():
        return redirect(url_for('main.index'))
    
    # Get pagination parameters
    page = request.args.get('page', 1, type=int)
    per_page = 20  # Number of customers per page
    
    # Get paginated customers with total spent calculation
    customers_query = CustomerLoyalty.query.order_by(
        CustomerLoyalty.total_points.desc()
    )
    
    customers_paginated = customers_query.paginate(
        page=page, 
        per_page=per_page, 
        error_out=False
    )
    
    # Calculate total spent for each customer in the current page
    customers_with_spent = []
    for customer in customers_paginated.items:
        # Calculate total spent from completed orders
        total_spent = db.session.query(func.sum(Order.total_amount)).filter(
            Order.user_id == customer.user_id,
            Order.status.in_(['completed', 'delivered'])
        ).scalar() or 0
        
        # Add the total_spent attribute to the customer object
        customer.total_spent = float(total_spent)
        customers_with_spent.append(customer)
    
    # Update the paginated object items
    customers_paginated.items = customers_with_spent
    
    # Get loyalty program statistics
    total_customers = CustomerLoyalty.query.count()
    active_customers = CustomerLoyalty.query.filter(CustomerLoyalty.total_points > 0).count()
    
    # Get tier distribution
    bronze_customers = CustomerLoyalty.query.filter_by(tier_level='bronze').count()
    silver_customers = CustomerLoyalty.query.filter_by(tier_level='silver').count()
    gold_customers = CustomerLoyalty.query.filter_by(tier_level='gold').count()
    platinum_customers = CustomerLoyalty.query.filter_by(tier_level='platinum').count()
    
    # Get total points distributed
    total_points_distributed = db.session.query(func.sum(PointTransaction.points_earned)).scalar() or 0
    total_points_redeemed = db.session.query(func.sum(PointTransaction.points_redeemed)).scalar() or 0
    
    # Get recent transactions
    recent_transactions = PointTransaction.query.order_by(
        PointTransaction.timestamp.desc()
    ).limit(10).all()
    
    # Top customers by points
    top_customers = CustomerLoyalty.query.order_by(
        CustomerLoyalty.total_points.desc()
    ).limit(10).all()
    
    # Calculate total redemptions
    total_redemptions = RewardRedemption.query.filter_by(status='completed').count()
    
    return render_template('loyalty_management.html',
                         customers=customers_paginated,
                         total_customers=total_customers,
                         active_customers=active_customers,
                         bronze_customers=bronze_customers,
                         silver_customers=silver_customers,
                         gold_customers=gold_customers,
                         platinum_customers=platinum_customers,
                         total_points_distributed=total_points_distributed,
                         total_points_redeemed=total_points_redeemed,
                         total_redemptions=total_redemptions,
                         recent_transactions=recent_transactions,
                         top_customers=top_customers,
                         datetime=datetime)

@bp.route('/loyalty-settings', methods=['GET', 'POST'])
@login_required
def loyalty_settings():
    """Loyalty program settings page"""
    if not current_user.is_admin():
        return redirect(url_for('main.index'))
    
    if request.method == 'POST':
        try:
            # Get or create loyalty program
            program = LoyaltyProgram.query.filter_by(status='active').first()
            if not program:
                program = LoyaltyProgram(
                    name='Restaurant Loyalty Program',
                    description='Earn points with every purchase',
                    status='active'
                )
                db.session.add(program)
            
            # Update settings
            program.points_per_50EGP = int(request.form.get('points_per_50_egp', 100))
            program.points_value = float(request.form.get('points_value', 1.0))
            program.min_redemption = int(request.form.get('min_redemption', 100))
            program.max_redemption_percentage = int(request.form.get('max_redemption_percentage', 50))
            program.status = 'active' if request.form.get('program_active') else 'inactive'
            
            db.session.commit()
            flash('Loyalty program settings updated successfully!', 'success')
            return redirect(url_for('admin.loyalty_settings'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating settings: {str(e)}', 'error')
    
    # Get current program settings
    program = LoyaltyProgram.query.filter_by(status='active').first()
    
    # Mock tier thresholds (these could be stored in database too)
    tier_thresholds = {
        'bronze': 0,
        'silver': 500,
        'gold': 1000,
        'platinum': 2000
    }
    
    return render_template('loyalty_settings.html',
                         program=program,
                         tier_thresholds=tier_thresholds)

@bp.route('/loyalty-adjust-points', methods=['GET', 'POST'])
@login_required
def loyalty_adjust_points():
    """Adjust customer loyalty points"""
    if not current_user.is_admin():
        return redirect(url_for('main.index'))
    
    customer_id = request.args.get('customer_id', type=int)
    customer = None
    
    if customer_id:
        customer = CustomerLoyalty.query.filter_by(loyalty_id=customer_id).first()
        if not customer:
            flash('Customer not found', 'error')
            return redirect(url_for('admin.loyalty_management'))
    
    if request.method == 'POST':
        try:
            customer_id = int(request.form.get('customer_id'))
            adjustment_type = request.form.get('adjustment_type')
            points_amount = int(request.form.get('points_amount'))
            reason = request.form.get('reason')
            
            # Get customer loyalty account
            loyalty = CustomerLoyalty.query.filter_by(loyalty_id=customer_id).first()
            if not loyalty:
                flash('Customer not found', 'error')
                return redirect(url_for('admin.loyalty_adjust_points'))
            
            # Apply adjustment
            if adjustment_type == 'add':
                loyalty.total_points += points_amount
                loyalty.lifetime_points += points_amount
                transaction_type = 'bonus'
                description = f'Admin adjustment: {reason} (+{points_amount} points)'
                points_earned = points_amount
                points_redeemed = 0
            elif adjustment_type == 'deduct':
                if loyalty.total_points < points_amount:
                    flash('Insufficient points for deduction', 'error')
                    return redirect(url_for('admin.loyalty_adjust_points', customer_id=customer_id))
                loyalty.total_points -= points_amount
                transaction_type = 'adjustment'
                description = f'Admin adjustment: {reason} (-{points_amount} points)'
                points_earned = 0
                points_redeemed = points_amount
            elif adjustment_type == 'set':
                old_points = loyalty.total_points
                loyalty.total_points = points_amount
                if points_amount > old_points:
                    loyalty.lifetime_points += (points_amount - old_points)
                transaction_type = 'adjustment'
                description = f'Admin adjustment: {reason} (set to {points_amount} points)'
                points_earned = max(0, points_amount - old_points)
                points_redeemed = max(0, old_points - points_amount)
            
            # Update tier
            loyalty.update_tier()
            
            # Create transaction record
            transaction = PointTransaction(
                user_id=loyalty.user_id,
                points_earned=points_earned,
                points_redeemed=points_redeemed,
                balance_after=loyalty.total_points,
                transaction_type=transaction_type,
                description=description
            )
            db.session.add(transaction)
            db.session.commit()
            
            flash('Points adjusted successfully!', 'success')
            return redirect(url_for('admin.loyalty_customer_details', customer_id=customer_id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error adjusting points: {str(e)}', 'error')
    
    # Get all customers for selection
    customers = CustomerLoyalty.query.order_by(CustomerLoyalty.total_points.desc()).all()
    
    # Get recent adjustments
    recent_adjustments = db.session.query(PointTransaction).join(
        CustomerLoyalty, PointTransaction.user_id == CustomerLoyalty.user_id
    ).filter(
        PointTransaction.transaction_type.in_(['bonus', 'adjustment'])
    ).order_by(PointTransaction.timestamp.desc()).limit(10).all()
    
    return render_template('loyalty_adjust_points.html',
                         customer=customer,
                         customers=customers,
                         customer_id=customer_id,
                         recent_adjustments=recent_adjustments)

@bp.route('/loyalty-customer-details/<int:customer_id>')
@login_required
def loyalty_customer_details(customer_id):
    """Customer loyalty details page"""
    if not current_user.is_admin():
        return redirect(url_for('main.index'))
    
    customer = CustomerLoyalty.query.filter_by(loyalty_id=customer_id).first()
    if not customer:
        flash('Customer not found', 'error')
        return redirect(url_for('admin.loyalty_management'))
    
    # Get recent transactions (last 10)
    recent_transactions = PointTransaction.query.filter_by(
        user_id=customer.user_id
    ).order_by(PointTransaction.timestamp.desc()).limit(10).all()
    
    return render_template('loyalty_customer_details.html',
                         customer=customer,
                         recent_transactions=recent_transactions)

@bp.route('/loyalty-transactions/<int:customer_id>')
@login_required
def loyalty_transactions(customer_id):
    """Customer loyalty transactions page"""
    if not current_user.is_admin():
        return redirect(url_for('main.index'))
    
    customer = CustomerLoyalty.query.filter_by(loyalty_id=customer_id).first()
    if not customer:
        flash('Customer not found', 'error')
        return redirect(url_for('admin.loyalty_management'))
    
    # Get filter parameters
    page = request.args.get('page', 1, type=int)
    transaction_type = request.args.get('transaction_type', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    
    # Build query
    query = PointTransaction.query.filter_by(user_id=customer.user_id)
    
    # Apply filters
    if transaction_type:
        query = query.filter(PointTransaction.transaction_type == transaction_type)
    
    if date_from:
        date_from_obj = datetime.strptime(date_from, '%Y-%m-%d')
        query = query.filter(PointTransaction.timestamp >= date_from_obj)
    
    if date_to:
        date_to_obj = datetime.strptime(date_to, '%Y-%m-%d')
        # Add one day to include the entire end date
        date_to_obj = date_to_obj.replace(hour=23, minute=59, second=59)
        query = query.filter(PointTransaction.timestamp <= date_to_obj)
    
    # Get paginated results
    transactions = query.order_by(
        PointTransaction.timestamp.desc()
    ).paginate(page=page, per_page=20, error_out=False)
    
    # Calculate summary statistics
    all_transactions = PointTransaction.query.filter_by(user_id=customer.user_id).all()
    total_earned = sum(t.points_earned or 0 for t in all_transactions)
    total_redeemed = sum(t.points_redeemed or 0 for t in all_transactions)
    total_bonuses = sum(t.points_earned or 0 for t in all_transactions if t.transaction_type == 'bonus')
    
    return render_template('loyalty_transactions.html',
                         customer=customer,
                         transactions=transactions,
                         transaction_type=transaction_type,
                         date_from=date_from,
                         date_to=date_to,
                         total_earned=total_earned,
                         total_redeemed=total_redeemed,
                         total_bonuses=total_bonuses)

# ======================== END LOYALTY MANAGEMENT ROUTES ========================

# ======================== CAMPAIGNS MANAGEMENT ROUTES ========================

@bp.route('/campaigns-management')
@login_required
def campaigns_management():
    """Admin campaigns management dashboard"""
    if not current_user.is_admin():
        return redirect(url_for('main.index'))
    
    # Get all campaigns with pagination
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    campaigns = PromotionalCampaign.query.order_by(
        PromotionalCampaign.created_at.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)
    
    # Get campaign statistics
    total_campaigns = PromotionalCampaign.query.count()
    active_campaigns = PromotionalCampaign.query.filter_by(status='active').count()
    inactive_campaigns = PromotionalCampaign.query.filter_by(status='inactive').count()
    expired_campaigns = PromotionalCampaign.query.filter_by(status='expired').count()
    
    return render_template('campaigns_management.html',
                         campaigns=campaigns,
                         total_campaigns=total_campaigns,
                         active_campaigns=active_campaigns,
                         inactive_campaigns=inactive_campaigns,
                         expired_campaigns=expired_campaigns,
                         datetime=datetime)

@bp.route('/campaigns/add', methods=['GET', 'POST'])
@login_required
def add_campaign():
    """Add new promotional campaign"""
    if not current_user.is_admin():
        return redirect(url_for('main.index'))

    # Get categories for the form
    categories = Category.query.filter_by(is_active=True).all()
    
    if request.method == 'POST':
        try:
            # Parse specific menu categories if provided
            specific_categories = request.form.getlist('specific_menu_categories')
            categories_json = None
            if specific_categories:
                import json
                categories_json = json.dumps([int(cat_id) for cat_id in specific_categories if cat_id])

            campaign = PromotionalCampaign(
                name=request.form.get('name'),
                description=request.form.get('description'),
                bonus_multiplier=float(request.form.get('bonus_multiplier', 1.0)),
                start_date=datetime.strptime(request.form.get('start_date'), '%Y-%m-%d'),
                end_date=datetime.strptime(request.form.get('end_date'), '%Y-%m-%d'),
                conditions=request.form.get('conditions'),
                status=request.form.get('status', 'active'),
                minimum_order_amount=float(request.form.get('minimum_order_amount') or 0),
                maximum_uses_per_customer=int(request.form.get('maximum_uses_per_customer')) if request.form.get('maximum_uses_per_customer') else None,
                total_usage_limit=int(request.form.get('total_usage_limit')) if request.form.get('total_usage_limit') else None,
                target_customer_tier=request.form.get('target_customer_tier') or 'all',
                applicable_days=request.form.get('applicable_days') or 'all',
                specific_menu_categories=categories_json,
                discount_type=request.form.get('discount_type') or 'points_multiplier',
                discount_value=float(request.form.get('discount_value')) if request.form.get('discount_value') else None
            )
            
            db.session.add(campaign)
            db.session.commit()
            
            flash('Campaign added successfully!', 'success')
            return redirect(url_for('admin.campaigns_management'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding campaign: {str(e)}', 'error')
    
    return render_template('add_campaign.html', categories=categories)

@bp.route('/campaigns/edit/<int:campaign_id>', methods=['GET', 'POST'])
@login_required
def edit_campaign(campaign_id):
    """Edit existing campaign"""
    if not current_user.is_admin():
        return redirect(url_for('main.index'))

    campaign = PromotionalCampaign.query.get_or_404(campaign_id)
    categories = Category.query.filter_by(is_active=True).all()
    
    if request.method == 'POST':
        try:
            # Parse specific menu categories if provided
            specific_categories = request.form.getlist('specific_menu_categories')
            categories_json = None
            if specific_categories:
                import json
                categories_json = json.dumps([int(cat_id) for cat_id in specific_categories if cat_id])

            campaign.name = request.form.get('name')
            campaign.description = request.form.get('description')
            campaign.bonus_multiplier = float(request.form.get('bonus_multiplier', 1.0))
            campaign.start_date = datetime.strptime(request.form.get('start_date'), '%Y-%m-%d')
            campaign.end_date = datetime.strptime(request.form.get('end_date'), '%Y-%m-%d')
            campaign.conditions = request.form.get('conditions')
            campaign.status = request.form.get('status')
            campaign.minimum_order_amount = float(request.form.get('minimum_order_amount') or 0)
            campaign.maximum_uses_per_customer = int(request.form.get('maximum_uses_per_customer')) if request.form.get('maximum_uses_per_customer') else None
            campaign.total_usage_limit = int(request.form.get('total_usage_limit')) if request.form.get('total_usage_limit') else None
            campaign.target_customer_tier = request.form.get('target_customer_tier') or 'all'
            campaign.applicable_days = request.form.get('applicable_days') or 'all'
            campaign.specific_menu_categories = categories_json
            campaign.discount_type = request.form.get('discount_type') or 'points_multiplier'
            campaign.discount_value = float(request.form.get('discount_value')) if request.form.get('discount_value') else None
            
            db.session.commit()
            
            flash('Campaign updated successfully!', 'success')
            return redirect(url_for('admin.campaigns_management'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating campaign: {str(e)}', 'error')
    
    return render_template('edit_campaign.html', campaign=campaign, categories=categories, now=datetime.now)

@bp.route('/campaign-statistics/<int:campaign_id>')
@login_required
def campaign_statistics(campaign_id):
    """Campaign statistics page"""
    if not current_user.is_admin():
        return redirect(url_for('main.index'))
    
    campaign = PromotionalCampaign.query.get(campaign_id)
    if not campaign:
        flash('Campaign not found', 'error')
        return redirect(url_for('admin.campaigns_management'))
    
    # Calculate campaign statistics
    stats = calculate_campaign_stats(campaign)
    
    return render_template('campaign_statistics.html',
                         campaign=campaign,
                         stats=stats,
                         datetime=datetime)

def calculate_campaign_stats(campaign):
    """Calculate comprehensive statistics for a campaign"""
    # Mock statistics - in a real application, these would be calculated from actual data
    
    # Basic stats
    total_orders = 0
    bonus_points_awarded = 0
    customers_engaged = 0
    revenue_impact = 0.0
    
    # Calculate if campaign is currently active
    now = datetime.utcnow()
    is_active = (campaign.status == 'active' and 
                campaign.start_date and campaign.end_date and 
                campaign.start_date <= now <= campaign.end_date)
    
    if is_active:
        # Mock data for active campaigns
        total_orders = 150
        bonus_points_awarded = 15000
        customers_engaged = 85
        revenue_impact = 2500.00
        performance_percentage = 75
        performance_description = "Campaign is performing well with good customer engagement"
        
        # Growth metrics
        total_orders_growth = 25
        revenue_growth = 18
        unique_customers_percentage = 45
        
        # Engagement breakdown by tier
        engagement_breakdown = {
            'bronze': 45,
            'silver': 25,
            'gold': 12,
            'platinum': 3
        }
        
        # Order patterns
        order_patterns = {
            'avg_order_value': 35.50,
            'peak_time': '7:00 PM - 9:00 PM',
            'repeat_customers': 65,
            'new_customers': 35
        }
    else:
        # Mock data for inactive/completed campaigns
        total_orders = 320
        bonus_points_awarded = 25000
        customers_engaged = 150
        revenue_impact = 4200.00
        performance_percentage = 85
        performance_description = "Campaign completed successfully with excellent results"
        
        # Growth metrics
        total_orders_growth = 35
        revenue_growth = 28
        unique_customers_percentage = 60
        
        # Engagement breakdown by tier
        engagement_breakdown = {
            'bronze': 80,
            'silver': 45,
            'gold': 20,
            'platinum': 5
        }
        
        # Order patterns
        order_patterns = {
            'avg_order_value': 42.75,
            'peak_time': '6:30 PM - 8:30 PM',
            'repeat_customers': 70,
            'new_customers': 30
        }
    
    return {
        'total_orders': total_orders,
        'bonus_points_awarded': bonus_points_awarded,
        'customers_engaged': customers_engaged,
        'revenue_impact': revenue_impact,
        'performance_percentage': performance_percentage,
        'performance_description': performance_description,
        'total_orders_growth': total_orders_growth,
        'revenue_growth': revenue_growth,
        'unique_customers_percentage': unique_customers_percentage,
        'engagement_breakdown': engagement_breakdown,
        'order_patterns': order_patterns
    }

# ======================== END CAMPAIGNS MANAGEMENT ROUTES

# API Routes for AJAX operations

@bp.route('/api/recent-activity')
@login_required
def api_recent_activity():
    """API endpoint for recent activity data"""
    if not current_user.is_admin():
        return jsonify({'error': 'Unauthorized'}), 403

    # Performance: Get recent activities with limit
    from datetime import datetime, timedelta, timezone

    recent_orders = Order.query.join(User).filter(
        Order.order_time >= datetime.now(timezone.utc) - timedelta(hours=24)
    ).order_by(Order.order_time.desc()).limit(5).all()

    activities = []
    for order in recent_orders:
        activities.append({
            'title': f'New order from {order.customer.name}',
            'icon': 'fas fa-shopping-cart',
            'timestamp': order.order_time.isoformat() + 'Z',  # UTC timestamp
            'type': 'order'
        })

    return jsonify({'activities': activities})



@bp.route('/api/search')
@login_required
def api_search():
    """API endpoint for search functionality"""
    if not current_user.is_admin():
        return jsonify({'error': 'Unauthorized'}), 403

    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({'results': []})

    # Performance: Search across multiple models with limit
    results = []

    # Search menu items
    menu_items = MenuItem.query.filter(
        MenuItem.name.ilike(f'%{query}%')
    ).limit(5).all()

    for item in menu_items:
        results.append({
            'title': item.name,
            'type': 'menu_item',
            'url': url_for('admin.edit_menu_item', item_id=item.item_id),
            'description': item.description[:100] if item.description else ''
        })

    # Search categories
    categories = Category.query.filter(
        Category.name.ilike(f'%{query}%')
    ).limit(3).all()

    for category in categories:
        results.append({
            'title': category.name,
            'type': 'category',
            'url': url_for('admin.edit_category', category_id=category.category_id),
            'description': category.description[:100] if category.description else ''
        })

    return jsonify({'results': results})

@bp.route('/api/menu/items/<int:item_id>/stock', methods=['POST'])
@login_required
def update_item_stock(item_id):
    """Update menu item stock via AJAX"""
    if not current_user.is_admin():
        return jsonify({'error': 'Unauthorized'}), 403

    menu_item = MenuItem.query.get_or_404(item_id)
    data = request.get_json()

    if 'stock' not in data:
        return jsonify({'error': 'Stock value required'}), 400

    try:
        menu_item.stock = int(data['stock'])
        # Auto-update status based on stock
        if menu_item.stock <= 0:
            menu_item.status = 'out_of_stock'
        elif menu_item.status == 'out_of_stock' and menu_item.stock > 0:
            menu_item.status = 'available'

        db.session.commit()
        return jsonify({
            'success': True,
            'stock': menu_item.stock,
            'status': menu_item.status
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Failed to update stock'}), 500

@bp.route('/api/menu/items/<int:item_id>/status', methods=['POST'])
@login_required
def update_item_status(item_id):
    """Update menu item status via AJAX"""
    if not current_user.is_admin():
        return jsonify({'error': 'Unauthorized'}), 403

    menu_item = MenuItem.query.get_or_404(item_id)
    data = request.get_json()

    if 'status' not in data:
        return jsonify({'error': 'Status value required'}), 400

    valid_statuses = ['available', 'out_of_stock', 'discontinued']
    if data['status'] not in valid_statuses:
        return jsonify({'error': 'Invalid status'}), 400

    try:
        menu_item.status = data['status']
        db.session.commit()
        return jsonify({
            'success': True,
            'status': menu_item.status
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Failed to update status'}), 500

# API Endpoints for Real-time Notifications

@bp.route('/api/order-notifications')
@login_required
def api_order_notifications():
    """API endpoint to get order notification data"""
    if not current_user.is_admin():
        return jsonify({'error': 'Unauthorized'}), 403

    try:
        # Get count of new and processing orders
        new_orders_count = Order.get_new_orders_count()

        # Get recent orders from last 2 hours for more immediate notifications
        recent_cutoff = datetime.utcnow() - timedelta(hours=2)
        recent_orders_count = Order.query.filter(
            Order.order_time >= recent_cutoff,
            Order.status.in_(['new', 'processing'])
        ).count()

        # Determine if there are new orders to notify about
        has_new_orders = new_orders_count > 0

        return jsonify({
            'success': True,
            'has_new_orders': has_new_orders,
            'new_orders_count': new_orders_count,
            'recent_orders_count': recent_orders_count,
            'timestamp': datetime.utcnow().isoformat()
        })

    except Exception as e:
        current_app.logger.error(f"Error fetching order notifications: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to fetch notifications',
            'has_new_orders': False,
            'new_orders_count': 0
        }), 500

@bp.route('/api/mark-orders-seen', methods=['POST'])
@login_required
def api_mark_orders_seen():
    """API endpoint to mark orders as seen (for notification management)"""
    if not current_user.is_admin():
        return jsonify({'error': 'Unauthorized'}), 403

    try:
        # This could be enhanced to track which admin has seen which orders
        # For now, we'll just return success
        return jsonify({
            'success': True,
            'message': 'Orders marked as seen'
        })

    except Exception as e:
        current_app.logger.error(f"Error marking orders as seen: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to mark orders as seen'
        }), 500

# ======================== LOYALTY API ROUTES ========================

@bp.route('/api/loyalty/customer/<int:customer_id>/transactions')
@login_required
def get_customer_transactions(customer_id):
    """Get transaction history for a specific customer"""
    if not current_user.is_admin():
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    try:
        transactions = PointTransaction.query.filter_by(
            user_id=customer_id
        ).order_by(PointTransaction.timestamp.desc()).limit(50).all()
        
        transaction_data = []
        for transaction in transactions:
            transaction_data.append({
                'transaction_id': transaction.transaction_id,
                'timestamp': transaction.timestamp.isoformat(),
                'transaction_type': transaction.transaction_type,
                'description': transaction.description,
                'points_earned': transaction.points_earned,
                'points_redeemed': transaction.points_redeemed,
                'order_id': transaction.order_id
            })
        
        return jsonify({
            'success': True,
            'transactions': transaction_data
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error loading transactions: {str(e)}'
        }), 500

@bp.route('/api/loyalty/adjust-points', methods=['POST'])
@login_required
def adjust_customer_points():
    """Adjust customer loyalty points"""
    if not current_user.is_admin():
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    try:
        data = request.get_json()
        customer_id = data.get('customer_id')
        adjustment_type = data.get('adjustment_type')
        points_amount = data.get('points_amount')
        reason = data.get('reason')
        
        # Get customer loyalty account
        loyalty = CustomerLoyalty.query.filter_by(loyalty_id=customer_id).first()
        if not loyalty:
            return jsonify({'success': False, 'message': 'Customer not found'}), 404
        
        # Apply adjustment
        if adjustment_type == 'add':
            loyalty.total_points += points_amount
            loyalty.lifetime_points += points_amount
            transaction_type = 'bonus'
            description = f'Admin adjustment: {reason} (+{points_amount} points)'
        elif adjustment_type == 'deduct':
            if loyalty.total_points < points_amount:
                return jsonify({'success': False, 'message': 'Insufficient points'}), 400
            loyalty.total_points -= points_amount
            transaction_type = 'adjustment'
            description = f'Admin adjustment: {reason} (-{points_amount} points)'
        elif adjustment_type == 'set':
            old_points = loyalty.total_points
            loyalty.total_points = points_amount
            if points_amount > old_points:
                loyalty.lifetime_points += (points_amount - old_points)
            transaction_type = 'adjustment'
            description = f'Admin adjustment: {reason} (set to {points_amount} points)'
        
        # Update tier
        loyalty.update_tier()
        
        # Create transaction record
        transaction = PointTransaction(
            user_id=loyalty.user_id,
            points_earned=points_amount if adjustment_type == 'add' else 0,
            points_redeemed=points_amount if adjustment_type == 'deduct' else 0,
            transaction_type=transaction_type,
            description=description
        )
        db.session.add(transaction)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Points adjusted successfully',
            'new_balance': loyalty.total_points
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Error adjusting points: {str(e)}'
        }), 500

@bp.route('/api/loyalty/settings', methods=['POST'])
@login_required
def save_loyalty_settings():
    """Save loyalty program settings"""
    if not current_user.is_admin():
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    try:
        data = request.get_json()
        
        # Get or create loyalty program
        program = LoyaltyProgram.query.filter_by(status='active').first()
        if not program:
            program = LoyaltyProgram(
                name='Restaurant Loyalty Program',
                description='Earn points with every purchase'
            )
            db.session.add(program)
        
        # Update settings
        program.points_per_50EGP = data.get('points_per_50_egp', 100)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Settings saved successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Error saving settings: {str(e)}'
        }), 500

# ======================== CAMPAIGN API ROUTES ========================

@bp.route('/api/campaigns/<int:campaign_id>/stats')
@login_required
def get_campaign_stats(campaign_id):
    """Get statistics for a specific campaign"""
    if not current_user.is_admin():
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    try:
        campaign = PromotionalCampaign.query.get(campaign_id)
        if not campaign:
            return jsonify({'success': False, 'message': 'Campaign not found'}), 404
        
        # Calculate statistics (mock data for now)
        stats = {
            'total_orders': 0,
            'bonus_points_awarded': 0,
            'customers_engaged': 0,
            'revenue_impact': '0.00',
            'performance_percentage': 0,
            'performance_description': 'Campaign statistics will be calculated based on actual usage'
        }
        
        # You can enhance this with real data from point transactions
        # where the campaign was active
        
        return jsonify({
            'success': True,
            'stats': stats
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error loading statistics: {str(e)}'
        }), 500

@bp.route('/api/campaigns/<int:campaign_id>/toggle', methods=['POST'])
@login_required
def toggle_campaign(campaign_id):
    """Toggle campaign active status"""
    if not current_user.is_admin():
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    try:
        campaign = PromotionalCampaign.query.get(campaign_id)
        if not campaign:
            return jsonify({'success': False, 'message': 'Campaign not found'}),  404
        
        # Toggle status
        campaign.status = 'inactive' if campaign.status == 'active' else 'active'
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Campaign {"deactivated" if campaign.status == "inactive" else "activated"} successfully',
            'new_status': campaign.status
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Error toggling campaign: {str(e)}'
        }), 500

@bp.route('/api/campaigns/<int:campaign_id>', methods=['DELETE'])
@login_required
def delete_campaign(campaign_id):
    """Delete a campaign"""
    if not current_user.is_admin():
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    try:
        campaign = PromotionalCampaign.query.get(campaign_id)
        if not campaign:
            return jsonify({'success': False, 'message': 'Campaign not found'}), 404
        
        db.session.delete(campaign)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Campaign deleted successfully'
        })
        
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Error deleting campaign: {str(e)}'
        }), 500

@bp.route('/api/notifications')
@login_required
def api_notifications():
    """API endpoint to get all real-time notifications"""
    if not current_user.is_admin():
        return jsonify({'error': 'Unauthorized'}), 403

    try:
        notifications = []
        
        # Recent orders (last 30 minutes)
        recent_cutoff = datetime.utcnow() - timedelta(minutes=30)
        recent_orders = Order.query.filter(
            Order.order_time >= recent_cutoff,
            Order.status.in_(['new', 'processing'])
        ).order_by(Order.order_time.desc()).limit(5).all()
        
        for order in recent_orders:
            # Send UTC timestamp to frontend for timezone conversion
            notifications.append({
                'id': f"order_{order.id}",
                'type': 'order',
                'icon': 'fas fa-shopping-cart',
                'color': 'success' if order.status == 'processing' else 'warning',
                'title': f"Order #{order.id}",
                'message': f"Status: {order.status.title()}",
                'timestamp': order.order_time.isoformat() + 'Z',  # UTC timestamp
                'url': url_for('admin.orders')
            })
        
        # Low stock items
        low_stock_items = MenuItem.query.filter(
            MenuItem.stock <= 5,
            MenuItem.stock > 0,
            MenuItem.status == 'available'
        ).limit(3).all()
        
        for item in low_stock_items:
            notifications.append({
                'id': f"stock_{item.id}",
                'type': 'stock',
                'icon': 'fas fa-exclamation-triangle',
                'color': 'warning',
                'title': f"Low Stock: {item.name}",
                'message': f"Only {item.stock} items left",
                'timestamp': datetime.utcnow().isoformat() + 'Z',  # Current UTC timestamp
                'url': url_for('admin.menu_management')
            })
        
        # Recent loyalty redemptions (last hour)
        recent_redemptions = RewardRedemption.query.filter(
            RewardRedemption.redeemed_at >= datetime.utcnow() - timedelta(hours=1)
        ).order_by(RewardRedemption.redeemed_at.desc()).limit(3).all()
        
        for redemption in recent_redemptions:
            notifications.append({
                'id': f"redemption_{redemption.id}",
                'type': 'loyalty',
                'icon': 'fas fa-gift',
                'color': 'info',
                'title': "Reward Redeemed",
                'message': f"{redemption.reward.name}",
                'timestamp': redemption.redeemed_at.isoformat() + 'Z',  # UTC timestamp
                'url': url_for('admin.rewards_management')
            })
        
        # Sort by most recent (using timestamp)
        notifications.sort(key=lambda x: x['timestamp'], reverse=True)
        
        return jsonify({
            'success': True,
            'notifications': notifications[:10],  # Limit to 10 most recent
            'total_count': len(notifications),
            'has_new': len(notifications) > 0
        })
        
    except Exception as e:
        current_app.logger.error(f"Error fetching notifications: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to fetch notifications'
        }), 500

# ======================== TABLE MANAGEMENT API ROUTES ========================

@bp.route('/api/tables', methods=['GET'])
@login_required
def api_get_tables():
    """Get all tables with their details"""
    if not current_user.is_admin():
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    try:
        tables = Table.query.order_by(Table.table_number).all()
        tables_data = []
        
        for table in tables:
            # Get active orders count for this table
            active_orders = Order.query.filter(
                Order.table_id == table.table_id,
                Order.status.in_(['new', 'processing'])
            ).count()
            
            # Get QR codes for this table
            qr_codes = QRCode.query.filter_by(table_id=table.table_id).count()
            
            tables_data.append({
                'table_id': table.table_id,
                'table_number': table.table_number,
                'capacity': table.capacity,
                'status': table.status,
                'is_occupied': table.status == 'occupied',
                'active_orders': active_orders,
                'qr_codes_count': qr_codes,
                'created_at': table.created_at.isoformat() if table.created_at else None
            })
        
        return jsonify({
            'success': True,
            'tables': tables_data,
            'total_count': len(tables_data)
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error fetching tables: {str(e)}'
        }), 500

@bp.route('/api/tables', methods=['POST'])
@login_required
def api_create_table():
    """Create a new table"""
    if not current_user.is_admin():
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    try:
        data = request.get_json()
        
        # Validate required fields
        if not data.get('table_number'):
            return jsonify({
                'success': False,
                'message': 'Table number is required'
            }), 400
        
        # Check if table number already exists
        existing_table = Table.query.filter_by(table_number=data['table_number']).first()
        if existing_table:
            return jsonify({
                'success': False,
                'message': 'Table number already exists'
            }), 400
        
        # Create new table
        table = Table(
            table_number=data['table_number'],
            capacity=int(data.get('capacity', 4)),
            status='available'
        )
        
        db.session.add(table)
        db.session.commit()
        
        # Automatically create QR code for the new table
        qr_url = f"{request.url_root}table/{table.table_id}?table={table.table_number}"
        qr_code = QRCode(
            table_id=table.table_id,
            url=qr_url,
            qr_type='menu',
            is_active=True
        )
        db.session.add(qr_code)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Table created successfully',
            'table': {
                'table_id': table.table_id,
                'table_number': table.table_number,
                'capacity': table.capacity,
                'status': table.status,
                'qr_code_id': qr_code.qr_id
            }
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Error creating table: {str(e)}'
        }), 500

@bp.route('/api/tables/<int:table_id>', methods=['GET'])
@login_required
def api_get_table(table_id):
    """Get specific table details"""
    if not current_user.is_admin():
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    try:
        table = Table.query.get_or_404(table_id)
        
        # Get active orders for this table
        active_orders = Order.query.filter(
            Order.table_id == table.table_id,
            Order.status.in_(['new', 'processing'])
        ).all()
        
        # Get QR codes for this table
        qr_codes = QRCode.query.filter_by(table_id=table.table_id).all()
        
        return jsonify({
            'success': True,
            'table': {
                'table_id': table.table_id,
                'table_number': table.table_number,
                'capacity': table.capacity,
                'status': table.status,
                'is_occupied': table.status == 'occupied',
                'is_active': True,  # Default for now
                'location': '',  # Add this field to Table model if needed
                'table_type': 'regular',  # Add this field to Table model if needed
                'active_orders': [
                    {
                        'order_id': order.order_id,
                        'status': order.status,
                        'order_time': order.order_time.isoformat(),
                        'customer_name': order.customer.name if order.customer else 'Unknown'
                    }
                    for order in active_orders
                ],
                'qr_codes': [
                    {
                        'qr_id': qr.qr_id,
                        'url': qr.url,
                        'is_active': qr.is_active,
                        'scan_count': qr.scan_count
                    }
                    for qr in qr_codes
                ]
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error fetching table: {str(e)}'
        }), 500

@bp.route('/api/tables/<int:table_id>', methods=['PUT'])
@login_required
def api_update_table(table_id):
    """Update table details"""
    if not current_user.is_admin():
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    try:
        table = Table.query.get_or_404(table_id)
        data = request.get_json()
        
        # Update table fields
        if 'table_number' in data:
            # Check if new table number conflicts with existing
            existing_table = Table.query.filter(
                Table.table_number == data['table_number'],
                Table.table_id != table_id
            ).first()
            if existing_table:
                return jsonify({
                    'success': False,
                    'message': 'Table number already exists'
                }), 400
            table.table_number = data['table_number']
        
        if 'capacity' in data:
            table.capacity = int(data['capacity'])
        
        if 'status' in data:
            table.status = data['status']
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Table updated successfully',
            'table': {
                'table_id': table.table_id,
                'table_number': table.table_number,
                'capacity': table.capacity,
                'status': table.status
            }
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Error updating table: {str(e)}'
        }), 500

@bp.route('/api/tables/<int:table_id>', methods=['DELETE'])
@login_required
def api_delete_table(table_id):
    """Delete a table"""
    if not current_user.is_admin():
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    try:
        table = Table.query.get_or_404(table_id)
        
        # Check if table has active orders
        active_orders = Order.query.filter(
            Order.table_id == table.table_id,
            Order.status.in_(['new', 'processing'])
        ).count()
        
        if active_orders > 0:
            return jsonify({
                'success': False,
                'message': 'Cannot delete table with active orders'
            }), 400
        
        # Delete associated QR codes first
        QRCode.query.filter_by(table_id=table.table_id).delete()
        
        # Delete the table
        db.session.delete(table)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Table deleted successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Error deleting table: {str(e)}'
        }), 500

@bp.route('/api/qr-codes/generate/<int:table_id>', methods=['POST'])
@login_required
def generate_table_qr(table_id):
    """Generate QR code for a specific table"""
    if not current_user.is_admin():
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    try:
        import qrcode
        from PIL import Image
        import io
        import base64
        
        # Get table
        table = Table.query.get_or_404(table_id)
        
        # Create table URL
        base_url = "http://localhost:5000"  # Change to your production domain
        table_url = f"{base_url}/table/{table.table_id}"
        
        # Generate QR code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=4,
        )
        qr.add_data(table_url)
        qr.make(fit=True)

        # Create QR code image
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Resize to 300x300
        img = img.resize((300, 300), Image.Resampling.LANCZOS)

        # Convert to base64
        buffered = io.BytesIO()
        img.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode()
        
        # Check if QR code exists
        existing_qr = QRCode.query.filter_by(table_id=table.table_id).first()
        
        if existing_qr:
            existing_qr.url = table_url
            existing_qr.qr_image_data = img_str
            existing_qr.is_active = True
        else:
            new_qr = QRCode(
                table_id=table.table_id,
                url=table_url,
                qr_type='menu',
                is_active=True,
                qr_image_data=img_str
            )
            db.session.add(new_qr)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'QR code generated successfully',
            'qr_image': f"data:image/png;base64,{img_str}",
            'scan_count': existing_qr.scan_count if existing_qr else 0,
            'last_scanned': existing_qr.last_scanned.isoformat() if existing_qr and existing_qr.last_scanned else None
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Error generating QR code: {str(e)}'
        }), 500

@bp.route('/api/qr-codes/<int:table_id>/image', methods=['GET'])
@login_required
def get_qr_image(table_id):
    """Get QR code image for a specific table"""
    if not current_user.is_admin():
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    try:
        qr_type = request.args.get('type', 'menu')

        # Get existing QR code
        qr_code = QRCode.query.filter_by(
            table_id=table_id,
            qr_type=qr_type,
            is_active=True
        ).first()

        if qr_code and qr_code.qr_image_data:
            return jsonify({
                'success': True,
                'qr_image': f"data:image/png;base64,{qr_code.qr_image_data}",
                'scan_count': qr_code.scan_count,
                'last_scanned': qr_code.last_scanned.isoformat() if qr_code.last_scanned else None
            })
        else:
            return jsonify({
                'success': False,
                'message': 'QR code not found'
            }), 404

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error retrieving QR code: {str(e)}'
        }), 500

@bp.route('/api/qr-codes/generate-all', methods=['POST'])
@login_required
def generate_all_qr():
    """Generate QR codes for all tables"""
    if not current_user.is_admin():
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    try:
        import qrcode
        from PIL import Image
        import io
        import base64
        
        # Get all tables
        tables = Table.query.all()
        created_count = 0
        updated_count = 0
        
        base_url = "http://localhost:5000"  # Change to your production domain
        
        for table in tables:
            try:
                # Create table URL
                table_url = f"{base_url}/table/{table.table_id}"
                
                # Generate QR code
                qr = qrcode.QRCode(
                    version=1,
                    error_correction=qrcode.constants.ERROR_CORRECT_M,
                    box_size=10,
                    border=4,
                )
                qr.add_data(table_url)
                qr.make(fit=True)

                # Create QR code image
                img = qr.make_image(fill_color="black", back_color="white")
                
                # Resize to 300x300
                img = img.resize((300, 300), Image.Resampling.LANCZOS)

                # Convert to base64
                buffered = io.BytesIO()
                img.save(buffered, format="PNG")
                img_str = base64.b64encode(buffered.getvalue()).decode()
                
                # Check if QR code exists
                existing_qr = QRCode.query.filter_by(table_id=table.table_id).first()
                
                if existing_qr:
                    existing_qr.url = table_url
                    existing_qr.qr_image_data = img_str
                    existing_qr.is_active = True
                    updated_count += 1
                else:
                    new_qr = QRCode(
                        table_id=table.table_id,
                        url=table_url,
                        qr_type='menu',
                        is_active=True,
                        qr_image_data=img_str
                    )
                    db.session.add(new_qr)
                    created_count += 1
                    
            except Exception as e:
                current_app.logger.error(f"Error processing Table {table.table_number}: {e}")
                continue
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'QR codes generated successfully for all tables. Created: {created_count}, Updated: {updated_count}'
        })
            
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Error generating QR codes: {str(e)}'
        }), 500

@bp.route('/api/qr-codes/analytics', methods=['GET'])
@login_required
def get_qr_analytics():
    """Get QR code analytics and statistics"""
    if not current_user.is_admin():
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    try:
        # Get QR code statistics
        total_qr_codes = QRCode.query.count()
        active_qr_codes = QRCode.query.filter_by(is_active=True).count()
        menu_qr_codes = QRCode.query.filter_by(qr_type='menu', is_active=True).count()
        whatsapp_qr_codes = QRCode.query.filter_by(qr_type='whatsapp', is_active=True).count()

        # Get scan statistics
        total_scans = db.session.query(db.func.sum(QRCode.scan_count)).scalar() or 0

        # Get most scanned QR codes
        most_scanned = QRCode.query.filter(QRCode.scan_count > 0).order_by(
            QRCode.scan_count.desc()
        ).limit(5).all()

        most_scanned_data = []
        for qr in most_scanned:
            most_scanned_data.append({
                'table_id': qr.table_id,
                'table_number': qr.table.table_number,
                'qr_type': qr.qr_type,
                'scan_count': qr.scan_count,
                'last_scanned': qr.last_scanned.isoformat() if qr.last_scanned else None
            })

        return jsonify({
            'success': True,
            'analytics': {
                'total_qr_codes': total_qr_codes,
                'active_qr_codes': active_qr_codes,
                'menu_qr_codes': menu_qr_codes,
                'whatsapp_qr_codes': whatsapp_qr_codes,
                'total_scans': total_scans,
                'most_scanned': most_scanned_data
            }
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error retrieving QR analytics: {str(e)}'
        }), 500

@bp.route('/api/qr-codes/<int:table_id>/stats', methods=['GET'])
@login_required
def get_table_qr_stats(table_id):
    """Get QR code statistics for a specific table"""
    if not current_user.is_admin():
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    try:
        # Get all QR codes for this table
        qr_codes = QRCode.query.filter_by(table_id=table_id, is_active=True).all()

        stats = []
        for qr in qr_codes:
            stats.append({
                'qr_type': qr.qr_type,
                'scan_count': qr.scan_count,
                'last_scanned': qr.last_scanned.isoformat() if qr.last_scanned else None,
                'url': qr.url
            })

        return jsonify({
            'success': True,
            'stats': stats
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error retrieving table QR stats: {str(e)}'
        }), 500

# ======================== SYSTEM SETTINGS ROUTES ========================

@bp.route('/system-settings', methods=['GET', 'POST'])
@login_required
def system_settings():
    """System settings management"""
    if not current_user.is_admin():
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('main.index'))
    
    if request.method == 'POST':
        try:
            # Currency & Pricing Settings
            SystemSettings.set_setting('system_currency', request.form.get('system_currency', 'EGP'), 'string', 
                                     'Default system currency', 'currency')
            SystemSettings.set_setting('tax_rate', request.form.get('tax_rate', '0'), 'float', 
                                     'Tax rate percentage', 'currency')
            SystemSettings.set_setting('service_charge', request.form.get('service_charge', '0'), 'float', 
                                     'Service charge percentage', 'currency')
            
            # Restaurant Information
            SystemSettings.set_setting('restaurant_name', request.form.get('restaurant_name', 'Restaurant Management System'), 'string', 
                                     'Restaurant display name', 'general')
            SystemSettings.set_setting('restaurant_phone', request.form.get('restaurant_phone', ''), 'string', 
                                     'Restaurant phone number', 'general')
            SystemSettings.set_setting('restaurant_address', request.form.get('restaurant_address', ''), 'string', 
                                     'Restaurant address', 'general')
            
            # Order Settings
            SystemSettings.set_setting('auto_accept_orders', 'auto_accept_orders' in request.form, 'boolean', 
                                     'Automatically accept new orders', 'orders')
            SystemSettings.set_setting('default_prep_time', request.form.get('default_prep_time', '30'), 'integer', 
                                     'Default preparation time in minutes', 'orders')
            SystemSettings.set_setting('max_order_items', request.form.get('max_order_items', '50'), 'integer', 
                                     'Maximum items per order', 'orders')
            
            # Notification Settings
            SystemSettings.set_setting('enable_push_notifications', 'enable_push_notifications' in request.form, 'boolean', 
                                     'Enable push notifications', 'notifications')
            SystemSettings.set_setting('email_notifications', 'email_notifications' in request.form, 'boolean', 
                                     'Send email notifications to staff', 'notifications')
            SystemSettings.set_setting('notification_sound', 'notification_sound' in request.form, 'boolean', 
                                     'Play sound for new orders', 'notifications')
            
            # Loyalty Program Settings
            SystemSettings.set_setting('loyalty_enabled', 'loyalty_enabled' in request.form, 'boolean', 
                                     'Enable loyalty program', 'loyalty')
            SystemSettings.set_setting('points_per_currency', request.form.get('points_per_currency', '2'), 'integer', 
                                     'Points earned per currency unit spent', 'loyalty')
            SystemSettings.set_setting('point_value', request.form.get('point_value', '0.5'), 'float', 
                                     'Value of each loyalty point', 'loyalty')
            
            # System Maintenance
            SystemSettings.set_setting('maintenance_mode', 'maintenance_mode' in request.form, 'boolean', 
                                     'Enable maintenance mode', 'system')
            SystemSettings.set_setting('backup_frequency', request.form.get('backup_frequency', 'daily'), 'string', 
                                     'Automatic backup frequency', 'system')
            
            flash('System settings saved successfully!', 'success')
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error saving settings: {str(e)}', 'error')
            current_app.logger.error(f"Error saving system settings: {str(e)}")
    
    # Load current settings
    settings = {}
    all_settings = SystemSettings.query.all()
    for setting in all_settings:
        if setting.setting_type == 'boolean':
            settings[setting.key] = setting.value.lower() in ('true', '1', 'yes') if setting.value else False
        elif setting.setting_type == 'integer':
            settings[setting.key] = int(setting.value) if setting.value else 0
        elif setting.setting_type == 'float':
            settings[setting.key] = float(setting.value) if setting.value else 0.0
        else:
            settings[setting.key] = setting.value
    
    return render_template('system_settings.html', settings=settings)

# ======================== ANALYTICS HELPER FUNCTIONS ========================

def calculate_revenue_metrics(base_query, start_date, end_date, period):
    """Calculate comprehensive revenue metrics"""
    from sqlalchemy import func

    # Total revenue and orders
    total_stats = base_query.with_entities(
        func.sum(Order.total_amount).label('total_revenue'),
        func.count(Order.order_id).label('total_orders'),
        func.avg(Order.total_amount).label('avg_order_value')
    ).first()

    total_revenue = float(total_stats.total_revenue or 0)
    total_orders = int(total_stats.total_orders or 0)
    avg_order_value = float(total_stats.avg_order_value or 0)

    # Revenue by status
    status_revenue = base_query.with_entities(
        Order.status,
        func.sum(Order.total_amount).label('revenue'),
        func.count(Order.order_id).label('count')
    ).group_by(Order.status).all()

    # Calculate growth (compare with previous period)
    growth_data = calculate_growth_metrics(start_date, end_date, period)

    return {
        'total_revenue': total_revenue,
        'total_orders': total_orders,
        'avg_order_value': avg_order_value,
        'status_breakdown': [
            {
                'status': status,
                'revenue': float(revenue or 0),
                'count': int(count or 0),
                'percentage': (float(revenue or 0) / total_revenue * 100) if total_revenue > 0 else 0
            }
            for status, revenue, count in status_revenue
        ],
        'growth': growth_data
    }

def calculate_customer_analytics(base_query, start_date, end_date):
    """Calculate customer behavior analytics"""
    from sqlalchemy import func

    # Customer metrics
    customer_stats = base_query.join(User).with_entities(
        func.count(func.distinct(Order.user_id)).label('unique_customers'),
        func.count(Order.order_id).label('total_orders')
    ).first()

    unique_customers = int(customer_stats.unique_customers or 0)
    total_orders = int(customer_stats.total_orders or 0)

    # Top customers by revenue
    top_customers = base_query.join(User).with_entities(
        User.name,
        User.email,
        func.sum(Order.total_amount).label('total_spent'),
        func.count(Order.order_id).label('order_count')
    ).group_by(User.user_id).order_by(
        func.sum(Order.total_amount).desc()
    ).limit(10).all()

    return {
        'unique_customers': unique_customers,
        'total_orders': total_orders,
        'orders_per_customer': round(total_orders / unique_customers, 2) if unique_customers > 0 else 0,
        'top_customers': [
            {
                'name': name,
                'email': email,
                'total_spent': float(total_spent or 0),
                'order_count': int(order_count or 0)
            }
            for name, email, total_spent, order_count in top_customers
        ]
    }

def calculate_product_performance(base_query, start_date, end_date):
    """Calculate product performance analytics"""
    from sqlalchemy import func

    # Top products by revenue
    top_products = base_query.join(OrderItem).join(MenuItem).with_entities(
        MenuItem.name,
        MenuItem.category_id,
        func.sum(OrderItem.quantity * OrderItem.unit_price).label('revenue'),
        func.sum(OrderItem.quantity).label('quantity_sold'),
        func.count(func.distinct(Order.order_id)).label('orders_count')
    ).group_by(MenuItem.item_id).order_by(
        func.sum(OrderItem.quantity * OrderItem.unit_price).desc()
    ).limit(15).all()

    # Category performance
    category_performance = base_query.join(OrderItem).join(MenuItem).join(Category).with_entities(
        Category.name,
        func.sum(OrderItem.quantity * OrderItem.unit_price).label('revenue'),
        func.sum(OrderItem.quantity).label('quantity_sold'),
        func.count(func.distinct(Order.order_id)).label('orders_count')
    ).group_by(Category.category_id).order_by(
        func.sum(OrderItem.quantity * OrderItem.unit_price).desc()
    ).all()

    return {
        'top_products': [
            {
                'name': name,
                'category_id': category_id,
                'revenue': float(revenue or 0),
                'quantity_sold': int(quantity_sold or 0),
                'orders_count': int(orders_count or 0)
            }
            for name, category_id, revenue, quantity_sold, orders_count in top_products
        ],
        'category_performance': [
            {
                'name': name,
                'revenue': float(revenue or 0),
                'quantity_sold': int(quantity_sold or 0),
                'orders_count': int(orders_count or 0)
            }
            for name, revenue, quantity_sold, orders_count in category_performance
        ]
    }

def calculate_time_analytics(base_query, start_date, end_date, period):
    """Calculate time-based analytics"""
    from sqlalchemy import func

    # Hourly distribution
    hourly_data = base_query.with_entities(
        func.extract('hour', Order.order_time).label('hour'),
        func.sum(Order.total_amount).label('revenue'),
        func.count(Order.order_id).label('orders')
    ).group_by(func.extract('hour', Order.order_time)).all()

    return {
        'hourly_distribution': [
            {
                'hour': int(hour or 0),
                'revenue': float(revenue or 0),
                'orders': int(orders or 0)
            }
            for hour, revenue, orders in hourly_data
        ]
    }

def calculate_growth_metrics(start_date, end_date, period):
    """Calculate growth metrics compared to previous period"""
    if not start_date:
        return {'revenue_growth': 0, 'order_growth': 0, 'customer_growth': 0}

    # Calculate previous period
    period_length = end_date - start_date
    prev_start = start_date - period_length
    prev_end = start_date

    # Current period metrics - only completed orders
    current_stats = Order.query.filter(
        Order.order_time >= start_date,
        Order.order_time <= end_date,
        Order.status == 'completed'
    ).with_entities(
        func.sum(Order.total_amount).label('revenue'),
        func.count(Order.order_id).label('orders'),
        func.count(func.distinct(Order.user_id)).label('customers')
    ).first()

    # Previous period metrics - only completed orders
    prev_stats = Order.query.filter(
        Order.order_time >= prev_start,
        Order.order_time < prev_end,
        Order.status == 'completed'
    ).with_entities(
        func.sum(Order.total_amount).label('revenue'),
        func.count(Order.order_id).label('orders'),
        func.count(func.distinct(Order.user_id)).label('customers')
    ).first()

    # Calculate growth percentages
    def calc_growth(current, previous):
        if not previous or previous == 0:
            return 100 if current > 0 else 0
        return round(((current - previous) / previous) * 100, 2)

    return {
        'revenue_growth': calc_growth(
            float(current_stats.revenue or 0),
            float(prev_stats.revenue or 0)
        ),
        'order_growth': calc_growth(
            int(current_stats.orders or 0),
            int(prev_stats.orders or 0)
        ),
        'customer_growth': calc_growth(
            int(current_stats.customers or 0),
            int(prev_stats.customers or 0)
        )
    }

def calculate_detailed_customer_behavior(base_query, start_date, end_date):
    """Calculate detailed customer behavior metrics"""
    from sqlalchemy import func

    # Customer spending distribution
    spending_distribution = base_query.join(User).with_entities(
        User.user_id,
        User.name,
        User.email,
        func.sum(Order.total_amount).label('total_spent'),
        func.count(Order.order_id).label('order_count'),
        func.avg(Order.total_amount).label('avg_order_value'),
        func.min(Order.order_time).label('first_order'),
        func.max(Order.order_time).label('last_order')
    ).group_by(User.user_id).order_by(
        func.sum(Order.total_amount).desc()
    ).all()

    # Calculate customer lifetime value and frequency
    customer_metrics = []
    for user_id, name, email, total_spent, order_count, avg_order, first_order, last_order in spending_distribution:
        # Calculate days between first and last order
        if first_order and last_order:
            days_active = (last_order - first_order).days + 1
            frequency = order_count / days_active if days_active > 0 else 0
        else:
            days_active = 0
            frequency = 0

        customer_metrics.append({
            'user_id': user_id,
            'name': name,
            'email': email,
            'total_spent': float(total_spent or 0),
            'order_count': int(order_count or 0),
            'avg_order_value': float(avg_order or 0),
            'days_active': days_active,
            'frequency': round(frequency, 3),
            'first_order': first_order,
            'last_order': last_order
        })

    # Order frequency analysis
    frequency_ranges = [
        (1, 1, 'One-time'),
        (2, 3, 'Occasional'),
        (4, 7, 'Regular'),
        (8, 15, 'Frequent'),
        (16, float('inf'), 'VIP')
    ]

    frequency_analysis = {}
    for min_orders, max_orders, label in frequency_ranges:
        count = len([c for c in customer_metrics if min_orders <= c['order_count'] <= max_orders])
        frequency_analysis[label] = count

    return {
        'customer_metrics': customer_metrics,
        'frequency_analysis': frequency_analysis,
        'total_customers': len(customer_metrics),
        'avg_customer_value': sum(c['total_spent'] for c in customer_metrics) / len(customer_metrics) if customer_metrics else 0,
        'avg_orders_per_customer': sum(c['order_count'] for c in customer_metrics) / len(customer_metrics) if customer_metrics else 0
    }

def calculate_customer_segmentation(base_query, start_date, end_date):
    """Calculate customer segmentation based on RFM analysis"""
    from sqlalchemy import func

    # RFM Analysis (Recency, Frequency, Monetary)
    now = datetime.now()

    rfm_data = base_query.join(User).with_entities(
        User.user_id,
        User.name,
        func.max(Order.order_time).label('last_order_date'),
        func.count(Order.order_id).label('frequency'),
        func.sum(Order.total_amount).label('monetary')
    ).group_by(User.user_id).all()

    # Calculate RFM scores
    rfm_customers = []
    for user_id, name, last_order_date, frequency, monetary in rfm_data:
        if last_order_date:
            recency = (now - last_order_date).days
        else:
            recency = 999  # Very old

        rfm_customers.append({
            'user_id': user_id,
            'name': name,
            'recency': recency,
            'frequency': int(frequency or 0),
            'monetary': float(monetary or 0)
        })

    # Segment customers
    segments = {
        'Champions': [],
        'Loyal Customers': [],
        'Potential Loyalists': [],
        'New Customers': [],
        'At Risk': [],
        'Cannot Lose Them': [],
        'Hibernating': []
    }

    for customer in rfm_customers:
        r = customer['recency']
        f = customer['frequency']
        m = customer['monetary']

        # Simple segmentation logic
        if r <= 7 and f >= 5 and m >= 200:
            segments['Champions'].append(customer)
        elif r <= 14 and f >= 3 and m >= 100:
            segments['Loyal Customers'].append(customer)
        elif r <= 30 and f >= 2:
            segments['Potential Loyalists'].append(customer)
        elif r <= 7 and f == 1:
            segments['New Customers'].append(customer)
        elif r > 30 and r <= 60 and f >= 2:
            segments['At Risk'].append(customer)
        elif r > 60 and m >= 150:
            segments['Cannot Lose Them'].append(customer)
        else:
            segments['Hibernating'].append(customer)

    return segments

def calculate_order_patterns(base_query, start_date, end_date):
    """Calculate order patterns and preferences"""
    from sqlalchemy import func

    # Day of week analysis
    dow_analysis = base_query.with_entities(
        func.extract('dow', Order.order_time).label('day_of_week'),
        func.count(Order.order_id).label('order_count'),
        func.sum(Order.total_amount).label('revenue')
    ).group_by(func.extract('dow', Order.order_time)).all()

    # Hour of day analysis
    hour_analysis = base_query.with_entities(
        func.extract('hour', Order.order_time).label('hour'),
        func.count(Order.order_id).label('order_count'),
        func.sum(Order.total_amount).label('revenue')
    ).group_by(func.extract('hour', Order.order_time)).all()

    # Popular item combinations
    item_combinations = base_query.join(OrderItem).join(MenuItem).with_entities(
        MenuItem.name,
        func.count(OrderItem.order_item_id).label('frequency')
    ).group_by(MenuItem.item_id).order_by(
        func.count(OrderItem.order_item_id).desc()
    ).limit(10).all()

    return {
        'day_of_week': [
            {
                'day': int(dow or 0),
                'day_name': ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'][int(dow or 0)],
                'orders': int(count or 0),
                'revenue': float(revenue or 0)
            }
            for dow, count, revenue in dow_analysis
        ],
        'hour_of_day': [
            {
                'hour': int(hour or 0),
                'orders': int(count or 0),
                'revenue': float(revenue or 0)
            }
            for hour, count, revenue in hour_analysis
        ],
        'popular_items': [
            {
                'name': name,
                'frequency': int(frequency or 0)
            }
            for name, frequency in item_combinations
        ]
    }

def calculate_customer_lifecycle(start_date, end_date):
    """Calculate customer lifecycle metrics"""
    from sqlalchemy import func

    # New customers in period
    new_customers = User.query.filter_by(role='customer')
    if start_date:
        new_customers = new_customers.filter(User.created_at >= start_date)
    if end_date:
        new_customers = new_customers.filter(User.created_at <= end_date)
    new_customers_count = new_customers.count()

    # Returning customers (customers who made orders in this period but registered before)
    returning_query = Order.query.join(User)
    if start_date:
        returning_query = returning_query.filter(
            Order.order_time >= start_date,
            User.created_at < start_date
        )
    if end_date:
        returning_query = returning_query.filter(Order.order_time <= end_date)

    returning_customers = returning_query.with_entities(
        func.count(func.distinct(Order.user_id))
    ).scalar() or 0

    # Customer retention rate (simplified)
    total_customers = User.query.filter_by(role='customer').count()
    retention_rate = (returning_customers / total_customers * 100) if total_customers > 0 else 0

    return {
        'new_customers': new_customers_count,
        'returning_customers': returning_customers,
        'total_customers': total_customers,
        'retention_rate': round(retention_rate, 2)
    }

# WhatsApp QR Code Integration Endpoints

@bp.route('/api/qr-codes/whatsapp/<int:table_id>', methods=['POST'])
@login_required
def generate_whatsapp_qr(table_id):
    """Generate WhatsApp QR code for a specific table"""
    if not current_user.is_admin():
        return jsonify({'success': False, 'message': 'Admin access required'}), 403

    try:
        from app.modules.qr.qr_service import QRCodeService
        qr_service = QRCodeService()

        # Get WhatsApp settings from request if provided
        data = request.get_json() if request.is_json else {}
        whatsapp_number = data.get('whatsapp_number', current_app.config.get('WHATSAPP_BOT_NUMBER', '201234567890'))

        # Temporarily store settings in request for QR service to access
        if request.is_json:
            request._whatsapp_settings = {
                'whatsapp_number': whatsapp_number,
                'message_template': data.get('whatsapp_message', 'Hello! I\'m at table {table_number} and would like to place an order.')
            }

        # Generate WhatsApp QR code
        result = qr_service.generate_qr_as_base64(table_id, qr_type='whatsapp')

        if result['success']:
            # Update database with WhatsApp QR code
            existing_qr = QRCode.query.filter_by(
                table_id=table_id,
                qr_type='whatsapp'
            ).first()

            if existing_qr:
                existing_qr.url = result['url']
                existing_qr.is_active = True
            else:
                qr_code = QRCode(
                    table_id=table_id,
                    url=result['url'],
                    qr_type='whatsapp',
                    is_active=True
                )
                db.session.add(qr_code)

            db.session.commit()

            return jsonify({
                'success': True,
                'message': f'WhatsApp QR code generated for table {table_id}',
                'qr_image': result['base64'],
                'whatsapp_url': result['url']
            })
        else:
            return jsonify({
                'success': False,
                'message': result['message']
            }), 400

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error generating WhatsApp QR code: {str(e)}'
        }), 500

@bp.route('/api/qr-codes/whatsapp/bulk', methods=['POST'])
@login_required
def generate_whatsapp_qr_bulk():
    """Generate WhatsApp QR codes for all tables"""
    if not current_user.is_admin():
        return jsonify({'success': False, 'message': 'Admin access required'}), 403

    try:
        from app.modules.qr.qr_service import QRCodeService
        qr_service = QRCodeService()

        # Get all tables
        tables = Table.query.all()
        results = []

        for table in tables:
            try:
                result = qr_service.generate_qr_as_base64(table.table_id, qr_type='whatsapp')

                if result['success']:
                    # Update database
                    existing_qr = QRCode.query.filter_by(
                        table_id=table.table_id,
                        qr_type='whatsapp'
                    ).first()

                    if existing_qr:
                        existing_qr.url = result['url']
                        existing_qr.is_active = True
                    else:
                        qr_code = QRCode(
                            table_id=table.table_id,
                            url=result['url'],
                            qr_type='whatsapp',
                            is_active=True
                        )
                        db.session.add(qr_code)

                    results.append({
                        'table_id': table.table_id,
                        'table_number': table.table_number,
                        'success': True,
                        'whatsapp_url': result['url']
                    })
                else:
                    results.append({
                        'table_id': table.table_id,
                        'table_number': table.table_number,
                        'success': False,
                        'error': result['message']
                    })

            except Exception as e:
                results.append({
                    'table_id': table.table_id,
                    'table_number': table.table_number,
                    'success': False,
                    'error': str(e)
                })

        db.session.commit()

        successful_count = sum(1 for r in results if r['success'])

        return jsonify({
            'success': True,
            'message': f'Generated WhatsApp QR codes for {successful_count}/{len(tables)} tables',
            'results': results
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error generating WhatsApp QR codes: {str(e)}'
        }), 500
