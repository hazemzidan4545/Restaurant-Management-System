from flask import render_template, redirect, url_for, request, flash, jsonify, session
from flask_login import login_required, current_user
from app.modules.customer import bp
from app.models import MenuItem, Category, Order, OrderItem, Payment, CustomerPreferences, Feedback, ServiceRequest, Service, db, Table, TableSession
from app.extensions import socketio
from sqlalchemy.orm import joinedload
from datetime import datetime, timedelta
import os
from werkzeug.utils import secure_filename
from functools import wraps
import requests

def validate_table_session(f):
    """Enhanced decorator to validate table session with security measures"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check if this is a WhatsApp session
        whatsapp_session_token = session.get('whatsapp_session_token')
        table_id = request.args.get('table_id') or session.get('whatsapp_table_id')

        if whatsapp_session_token and table_id:
            # Enhanced WhatsApp session validation with security checks
            try:
                # Validate session via API
                response = requests.get(f'http://localhost:5000/api/whatsapp-sessions/{whatsapp_session_token}/validate')

                if response.status_code != 200:
                    # Clear invalid session data
                    clear_whatsapp_session()
                    flash('جلسة منتهية الصلاحية. يرجى مسح رمز QR مرة أخرى.', 'error')
                    return redirect(url_for('main.index'))

                session_data = response.json()['data']

                # Security Check 1: Verify table ID matches
                if session_data['table_id'] != int(table_id):
                    clear_whatsapp_session()
                    flash('محاولة وصول غير مصرح بها. رقم الطاولة غير صحيح.', 'error')
                    return redirect(url_for('main.index'))

                # Security Check 2: Verify customer ID matches current user
                if current_user.is_authenticated and current_user.user_id != session_data['customer_id']:
                    clear_whatsapp_session()
                    flash('محاولة وصول غير مصرح بها. العميل غير صحيح.', 'error')
                    return redirect(url_for('main.index'))

                # Security Check 3: Verify IP address consistency (optional)
                stored_ip = session.get('whatsapp_session_ip')
                current_ip = request.remote_addr
                if stored_ip and stored_ip != current_ip:
                    # Log suspicious activity but don't block (mobile networks change IPs)
                    print(f"IP change detected for session {whatsapp_session_token}: {stored_ip} -> {current_ip}")

                # Security Check 4: Check for session hijacking attempts
                user_agent = request.headers.get('User-Agent', '')
                stored_user_agent = session.get('whatsapp_session_user_agent')
                if stored_user_agent and stored_user_agent != user_agent:
                    print(f"User-Agent change detected for session {whatsapp_session_token}")

                # Update session info with security data
                session['whatsapp_customer_id'] = session_data['customer_id']
                session['whatsapp_table_id'] = session_data['table_id']
                session['whatsapp_customer_name'] = session_data['customer_name']
                session['whatsapp_session_ip'] = current_ip
                session['whatsapp_session_user_agent'] = user_agent
                session['whatsapp_session_last_activity'] = datetime.utcnow().isoformat()

                # Add session info to request context
                request.table_session = {
                    'table_id': session_data['table_id'],
                    'customer_id': session_data['customer_id'],
                    'customer_name': session_data['customer_name'],
                    'session_token': whatsapp_session_token,
                    'is_whatsapp_session': True,
                    'expires_at': session_data['expires_at']
                }

                # Security Check 5: Prevent table switching via URL manipulation
                url_table_id = request.args.get('table_id')
                if url_table_id and int(url_table_id) != session_data['table_id']:
                    flash('لا يمكنك الوصول لطاولة أخرى. يرجى استخدام رمز QR الخاص بطاولتك.', 'error')
                    return redirect(url_for('customer.menu', table_id=session_data['table_id'], session=whatsapp_session_token))

            except Exception as e:
                print(f"Error validating WhatsApp session: {e}")
                clear_whatsapp_session()
                flash('حدث خطأ في التحقق من الجلسة.', 'error')
                return redirect(url_for('main.index'))

        else:
            # Traditional session validation (existing functionality)
            request.table_session = {
                'is_whatsapp_session': False
            }

        return f(*args, **kwargs)
    return decorated_function

def clear_whatsapp_session():
    """Clear WhatsApp session data from Flask session"""
    session.pop('whatsapp_session_token', None)
    session.pop('whatsapp_customer_id', None)
    session.pop('whatsapp_table_id', None)
    session.pop('whatsapp_customer_name', None)
    session.pop('whatsapp_session_ip', None)
    session.pop('whatsapp_session_user_agent', None)
    session.pop('whatsapp_session_last_activity', None)

def require_whatsapp_session(f):
    """Decorator that requires a valid WhatsApp session"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        whatsapp_session_token = session.get('whatsapp_session_token')

        if not whatsapp_session_token:
            flash('يجب الوصول عبر رمز QR الخاص بالطاولة.', 'error')
            return redirect(url_for('main.index'))

        return f(*args, **kwargs)
    return decorated_function

@bp.route('/menu')
@validate_table_session
def menu():
    """Customer menu view with ratings"""
    # Load categories and menu items from database
    categories = Category.query.filter_by(is_active=True).order_by(Category.display_order).all()
    menu_items = MenuItem.query.options(joinedload(MenuItem.category)).filter_by(status='available').join(Category).order_by(
        Category.display_order, MenuItem.name
    ).all()

    # Calculate ratings for each menu item
    items_with_ratings = []
    for item in menu_items:
        rating_data = item.get_average_rating()
        item_data = {
            'item': item,
            'rating': rating_data
        }
        items_with_ratings.append(item_data)

    return render_template('menu.html', categories=categories, menu_items=menu_items, items_with_ratings=items_with_ratings)

@bp.route('/profile')
@login_required
def profile():
    """Customer profile"""
    if not current_user.is_customer():
        return redirect(url_for('main.index'))
    
    # Get or create preferences for display
    preferences = current_user.preferences
    if not preferences:
        preferences = CustomerPreferences(user_id=current_user.user_id)
        db.session.add(preferences)
        db.session.commit()
    
    return render_template('customer_profile.html', profile=current_user, preferences=preferences, now=datetime.utcnow())

@bp.route('/profile/edit', methods=['GET', 'POST'])
@login_required
def edit_profile():
    """Customer edit profile"""
    if not current_user.is_customer():
        return redirect(url_for('main.index'))
    
    if request.method == 'POST':
        try:
            # Update basic profile information
            current_user.name = request.form.get('name', '').strip()
            current_user.email = request.form.get('email', '').strip()
            current_user.phone = request.form.get('phone', '').strip() or None
            
            # Handle profile image upload
            if 'profile_img' in request.files:
                file = request.files['profile_img']
                if file and file.filename != '':
                    # Create uploads directory if it doesn't exist
                    upload_folder = 'app/static/uploads/profile_images'
                    os.makedirs(upload_folder, exist_ok=True)
                    
                    # Secure filename and save
                    filename = secure_filename(file.filename)
                    file_path = os.path.join(upload_folder, f"user_{current_user.user_id}_{filename}")
                    file.save(file_path)
                    
                    # Store relative path for web access
                    current_user.profile_img = f"/static/uploads/profile_images/user_{current_user.user_id}_{filename}"
            
            # Save to database
            db.session.commit()
            flash('Profile updated successfully!', 'success')
            return redirect(url_for('customer.profile'))
            
        except Exception as e:
            db.session.rollback()
            flash('Error updating profile. Please try again.', 'error')
            
    return render_template('customer_edit_profile.html', profile=current_user)

@bp.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    """Customer settings"""
    if not current_user.is_customer():
        return redirect(url_for('main.index'))
    
    # Get or create preferences
    preferences = current_user.preferences
    if not preferences:
        preferences = CustomerPreferences(user_id=current_user.user_id)
        db.session.add(preferences)
        db.session.commit()
    
    if request.method == 'POST':
        try:
            # Handle password change
            if 'current_password' in request.form and 'new_password' in request.form:
                current_password = request.form.get('current_password')
                new_password = request.form.get('new_password')
                confirm_password = request.form.get('confirm_password')
                
                if not current_user.check_password(current_password):
                    flash('Current password is incorrect.', 'error')
                elif new_password != confirm_password:
                    flash('New passwords do not match.', 'error')
                elif len(new_password) < 6:
                    flash('Password must be at least 6 characters long.', 'error')
                else:
                    current_user.set_password(new_password)
                    db.session.commit()
                    flash('Password updated successfully!', 'success')
                    return redirect(url_for('customer.settings'))
            
            # Handle account deactivation
            elif 'deactivate_account' in request.form:
                confirm_password = request.form.get('deactivate_password')
                if current_user.check_password(confirm_password):
                    current_user.is_active = False
                    db.session.commit()
                    flash('Account deactivated successfully.', 'success')
                    return redirect(url_for('main.index'))
                else:
                    flash('Password is incorrect. Account not deactivated.', 'error')
                    
        except Exception as e:
            db.session.rollback()
            flash('An error occurred. Please try again.', 'error')
            
    return render_template('customer_settings.html', profile=current_user, preferences=preferences)

@bp.route('/settings/preferences', methods=['POST'])
@login_required
def update_preferences():
    """Update notification and privacy preferences via AJAX"""
    if not current_user.is_customer():
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    try:
        # Get or create preferences
        preferences = current_user.preferences
        if not preferences:
            preferences = CustomerPreferences(user_id=current_user.user_id)
            db.session.add(preferences)
        
        data = request.get_json()
        
        # Update notification preferences
        if 'notify_order_updates' in data:
            preferences.notify_order_updates = data['notify_order_updates']
        if 'notify_loyalty_points' in data:
            preferences.notify_loyalty_points = data['notify_loyalty_points']
        if 'notify_promotions' in data:
            preferences.notify_promotions = data['notify_promotions']
        if 'notify_service_requests' in data:
            preferences.notify_service_requests = data['notify_service_requests']
            
        # Update privacy preferences
        if 'profile_visible' in data:
            preferences.profile_visible = data['profile_visible']
        if 'order_history_private' in data:
            preferences.order_history_private = data['order_history_private']
        if 'analytics_enabled' in data:
            preferences.analytics_enabled = data['analytics_enabled']
        
        db.session.commit()
        return jsonify({'success': True, 'message': 'Preferences updated successfully'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Failed to update preferences'}), 500

@bp.route('/checkout')
@validate_table_session
def checkout():
    """Customer checkout page"""
    return render_template('checkout.html')

@bp.route('/order-confirmation/<int:order_id>')
def order_confirmation(order_id):
    """Order confirmation page"""
    return render_template('order_confirmation.html', order_id=order_id)

@bp.route('/track-order/<int:order_id>')
@login_required
def track_order(order_id):
    """Order tracking page"""
    if not current_user.is_customer():
        flash('Access denied. Customer account required.', 'error')
        return redirect(url_for('main.index'))
    
    # Verify the order belongs to the current user
    order = Order.query.filter_by(order_id=order_id, user_id=current_user.user_id).first()
    if not order:
        flash('Order not found or access denied.', 'error')
        return redirect(url_for('customer.my_orders'))
    
    return render_template('track_order.html', order_id=order_id, order=order)

@bp.route('/home')
@bp.route('/')
def home():
    """Customer home page using default landing template"""
    # Load popular menu items for the landing page
    popular_items = MenuItem.get_popular_items(limit=4)

    # If no popular items (no orders yet), fall back to first 4 available items
    if not popular_items:
        popular_items = MenuItem.query.filter_by(status='available').limit(4).all()

    return render_template('shared/landing.html', popular_items=popular_items)

@bp.route('/orders')
@login_required
@validate_table_session
def my_orders():
    """Customer orders page"""
    if not current_user.is_customer():
        flash('Access denied. Customer account required.', 'error')
        return redirect(url_for('main.index'))
    
    try:
        # Get orders for the current user with simple query first
        orders = Order.query.filter_by(user_id=current_user.user_id).order_by(Order.order_time.desc()).all()
        
        print(f"DEBUG: Loading orders for user {current_user.user_id} ({current_user.email})")
        print(f"DEBUG: Found {len(orders)} orders")
        
        # Load relationships manually to avoid lazy loading issues
        for order in orders:
            try:
                # Force load order items
                order_items = order.order_items.all()
                order._order_items = order_items
                print(f"DEBUG: Order {order.order_id} has {len(order_items)} items")
                
                # Force load payments
                payments = order.payments.all()
                order._payments = payments
                print(f"DEBUG: Order {order.order_id} has {len(payments)} payments")
                
            except Exception as item_error:
                print(f"DEBUG: Error loading items/payments for order {order.order_id}: {item_error}")
                order._order_items = []
                order._payments = []
        
        if not orders:
            flash('No orders found. Place your first order from our menu!', 'info')
        
        return render_template('customer_orders.html', orders=orders)
        
    except Exception as e:
        print(f"ERROR loading orders: {e}")
        import traceback
        traceback.print_exc()
        flash('Error loading orders. Please try again.', 'error')
        return render_template('customer_orders.html', orders=[])

@bp.route('/loyalty')
@login_required
def loyalty():
    """Customer loyalty page - redirect to main loyalty module"""
    if not current_user.is_customer():
        return redirect(url_for('main.index'))
    
    return redirect(url_for('loyalty.index'))

@bp.route('/order/<int:order_id>/reorder', methods=['POST'])
@login_required
def reorder(order_id):
    """Reorder items from a previous order"""
    if not current_user.is_customer():
        return jsonify({'success': False, 'message': 'Access denied'}), 403
    
    try:
        # Verify the order belongs to the current user
        order = Order.query.filter_by(order_id=order_id, user_id=current_user.user_id).first()
        if not order:
            return jsonify({'success': False, 'message': 'Order not found'}), 404
        
        # Check if order is in a reorderable state
        if order.status not in ['delivered', 'completed']:
            return jsonify({'success': False, 'message': 'Can only reorder completed orders'}), 400
        
        # Get all items from the original order
        order_items = order.order_items.all()
        if not order_items:
            return jsonify({'success': False, 'message': 'No items found in original order'}), 400
        
        # Create a new order
        new_order = Order(
            user_id=current_user.user_id,
            status='new',
            total_amount=0,  # Will be calculated after adding items
            notes=f'Reorder from Order #{order_id}',
            order_time=datetime.utcnow()
        )
        db.session.add(new_order)
        db.session.flush()  # Get the new order ID
        
        total_amount = 0
        reordered_items = []
        
        # Add each item from the original order
        for original_item in order_items:
            # Check if the menu item is still available
            menu_item = MenuItem.query.get(original_item.item_id)
            if menu_item and menu_item.status == 'available':
                new_item = OrderItem(
                    order_id=new_order.order_id,
                    item_id=original_item.item_id,
                    quantity=original_item.quantity,
                    unit_price=menu_item.price,  # Use current price
                    special_requests=original_item.special_requests
                )
                db.session.add(new_item)
                total_amount += menu_item.price * original_item.quantity
                reordered_items.append(menu_item.name)
            
        # Update the new order total
        new_order.total_amount = total_amount
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'message': f'Successfully reordered {len(reordered_items)} items',
            'new_order_id': new_order.order_id,
            'items': reordered_items
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Failed to reorder items'}), 500

@bp.route('/order/<int:order_id>/cancel', methods=['POST'])
@login_required
def cancel_order(order_id):
    """Cancel an order"""
    if not current_user.is_customer():
        return jsonify({'success': False, 'message': 'Access denied'}), 403
    
    try:
        # Verify the order belongs to the current user
        order = Order.query.filter_by(order_id=order_id, user_id=current_user.user_id).first()
        if not order:
            return jsonify({'success': False, 'message': 'Order not found'}), 404
        
        # Check if order can be cancelled
        if order.status not in ['new', 'confirmed', 'processing']:
            return jsonify({'success': False, 'message': 'Order cannot be cancelled at this stage'}), 400
        
        # Check if order has been paid
        payments = order.payments.filter_by(status='completed').all()
        if payments:
            return jsonify({'success': False, 'message': 'Paid orders cannot be cancelled. Please contact support for refund.'}), 400
        
        # Cancel the order
        order.status = 'cancelled'
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'message': f'Order #{order_id} has been cancelled successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Failed to cancel order'}), 500

@bp.route('/order/<int:order_id>/review', methods=['GET', 'POST'])
@login_required
def review_order(order_id):
    """Leave a review for an order and its items"""
    if not current_user.is_customer():
        return redirect(url_for('main.index'))
    
    # Verify the order belongs to the current user
    order = Order.query.filter_by(order_id=order_id, user_id=current_user.user_id).first()
    if not order:
        flash('Order not found or access denied.', 'error')
        return redirect(url_for('customer.my_orders'))
    
    # Check if order is reviewable
    if order.status not in ['delivered', 'completed']:
        flash('Can only review completed orders.', 'error')
        return redirect(url_for('customer.my_orders'))
    
    # Check if overall review already exists
    existing_order_review = Feedback.query.filter_by(order_id=order_id, user_id=current_user.user_id, item_id=None).first()
    
    # Get existing item reviews
    existing_item_reviews = {}
    item_reviews = Feedback.query.filter_by(order_id=order_id, user_id=current_user.user_id).filter(Feedback.item_id.isnot(None)).all()
    for review in item_reviews:
        existing_item_reviews[review.item_id] = review
    
    if request.method == 'POST':
        try:
            # Get overall rating
            overall_rating = int(request.form.get('overall_rating', 0))
            overall_comment = request.form.get('overall_comment', '').strip()
            
            if overall_rating < 1 or overall_rating > 5:
                flash('Please provide an overall rating between 1 and 5 stars.', 'error')
                return redirect(request.url)
            
            # Save or update overall order review
            if existing_order_review:
                existing_order_review.rating = overall_rating
                existing_order_review.comment = overall_comment
                existing_order_review.timestamp = datetime.utcnow()
            else:
                order_review = Feedback(
                    user_id=current_user.user_id,
                    order_id=order_id,
                    item_id=None,  # Overall order review
                    rating=overall_rating,
                    comment=overall_comment,
                    timestamp=datetime.utcnow()
                )
                db.session.add(order_review)
            
            # Process individual item reviews
            order_items = order.order_items.all()
            for item in order_items:
                item_rating_key = f'item_rating_{item.item_id}'
                item_comment_key = f'item_comment_{item.item_id}'
                
                item_rating = request.form.get(item_rating_key, '0')
                item_comment = request.form.get(item_comment_key, '').strip()
                
                # Only process if rating is provided (optional)
                if item_rating and int(item_rating) > 0:
                    item_rating = int(item_rating)
                    
                    if item_rating < 1 or item_rating > 5:
                        continue  # Skip invalid ratings
                    
                    if item.item_id in existing_item_reviews:
                        # Update existing item review
                        existing_review = existing_item_reviews[item.item_id]
                        existing_review.rating = item_rating
                        existing_review.comment = item_comment
                        existing_review.timestamp = datetime.utcnow()
                    else:
                        # Create new item review
                        item_review = Feedback(
                            user_id=current_user.user_id,
                            order_id=order_id,
                            item_id=item.item_id,
                            rating=item_rating,
                            comment=item_comment,
                            timestamp=datetime.utcnow()
                        )
                        db.session.add(item_review)
            
            db.session.commit()
            flash('Thank you for your detailed reviews!', 'success')
            return redirect(url_for('customer.my_orders'))
            
        except Exception as e:
            db.session.rollback()
            flash('Failed to save reviews. Please try again.', 'error')
    
    return render_template('review_order.html', 
                         order=order, 
                         existing_order_review=existing_order_review,
                         existing_item_reviews=existing_item_reviews)

@bp.route('/order/<int:order_id>/reorder-to-cart', methods=['POST'])
@login_required
def reorder_to_cart(order_id):
    """Add items from a previous order to the user's cart (session-based)"""
    if not current_user.is_customer():
        return jsonify({'success': False, 'message': 'Access denied'}), 403
    
    try:
        # Verify the order belongs to the current user
        order = Order.query.filter_by(order_id=order_id, user_id=current_user.user_id).first()
        if not order:
            return jsonify({'success': False, 'message': 'Order not found'}), 404
        
        # Check if order is in a reorderable state
        if order.status not in ['delivered', 'completed']:
            return jsonify({'success': False, 'message': 'Can only reorder completed orders'}), 400
        
        # Get all items from the original order
        order_items = order.order_items.all()
        if not order_items:
            return jsonify({'success': False, 'message': 'No items found in original order'}), 400
        
        # Initialize cart in session if it doesn't exist
        if 'cart' not in session:
            session['cart'] = []
        
        unique_items_added = 0
        total_quantity_added = 0
        unavailable_items = []
        processed_items = []
        
        # Add each item from the original order to the cart
        for original_item in order_items:
            try:
                # Check if the menu item is still available
                menu_item = MenuItem.query.get(original_item.item_id)
                if not menu_item:
                    print(f"Menu item {original_item.item_id} not found")
                    unavailable_items.append(original_item.item_id)
                    continue
                
                if menu_item.status != 'available':
                    print(f"Menu item {original_item.item_id} ({menu_item.name}) not available")
                    unavailable_items.append(original_item.item_id)
                    continue
            except Exception as item_error:
                print(f"Error processing menu item {original_item.item_id}: {str(item_error)}")
                unavailable_items.append(original_item.item_id)
                continue
            
            if menu_item and menu_item.status == 'available':
                # Check if item already exists in cart
                existing_item = None
                for cart_item in session['cart']:
                    if cart_item['id'] == menu_item.item_id:
                        existing_item = cart_item
                        break
                
                if existing_item:
                    # Update quantity of existing item
                    existing_item['quantity'] += original_item.quantity
                    total_quantity_added += original_item.quantity
                else:
                    # Add new item to cart
                    cart_item = {
                        'id': menu_item.item_id,
                        'name': menu_item.name,
                        'price': float(menu_item.price),
                        'quantity': original_item.quantity,
                        'image': menu_item.image_url or 'https://images.unsplash.com/photo-1546833999-b9f581a1996d?w=300&h=200&fit=crop',
                        'specialInstructions': original_item.note or '',
                        'category': 'Reordered Item'
                    }
                    session['cart'].append(cart_item)
                    total_quantity_added += original_item.quantity
                    unique_items_added += 1
                
                processed_items.append(menu_item.name)
            else:
                unavailable_items.append(original_item.item_id)
        
        # Mark session as modified to ensure it's saved
        session.modified = True
        
        message = f'Successfully added {total_quantity_added} items ({unique_items_added} unique items) to your cart'
        if unavailable_items:
            message += f'. {len(unavailable_items)} items were unavailable and skipped.'
        
        return jsonify({
            'success': True, 
            'message': message,
            'items_added': unique_items_added,
            'total_quantity_added': total_quantity_added,
            'unavailable_items': len(unavailable_items),
            'cart_items': session['cart']  # Include the cart items for frontend sync
        })
        
    except Exception as e:
        # Log the actual error for debugging
        print(f"Error in reorder_to_cart: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': f'Failed to add items to cart: {str(e)}'}), 500

@bp.route('/order/<int:order_id>/delete', methods=['DELETE'])
@login_required
def delete_order(order_id):
    """Delete an order from customer's history (customer only)"""
    if not current_user.is_customer():
        return jsonify({'success': False, 'message': 'Access denied'}), 403
    
    try:
        # Verify the order belongs to the current user
        order = Order.query.filter_by(order_id=order_id, user_id=current_user.user_id).first()
        if not order:
            return jsonify({'success': False, 'message': 'Order not found'}), 404
        
        # Only allow deletion of completed, cancelled, or delivered orders
        if order.status not in ['delivered', 'completed', 'cancelled']:
            return jsonify({'success': False, 'message': 'Can only delete completed, delivered, or cancelled orders'}), 400
        
        # Delete related order items first (due to foreign key constraints)
        OrderItem.query.filter_by(order_id=order_id).delete()
        
        # Delete related payments
        Payment.query.filter_by(order_id=order_id).delete()
        
        # Delete the order
        db.session.delete(order)
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'message': f'Order #{order_id} has been deleted from your history'
        })
        
    except Exception as e:
        db.session.rollback()
        # Log the actual error for debugging
        print(f"Error in delete_order: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': f'Failed to delete order: {str(e)}'}), 500

@bp.route('/service-requests')
@login_required
def service_requests():
    """Customer service requests page"""
    if not current_user.is_customer():
        return redirect(url_for('main.index'))

    # Get available services
    services = Service.query.filter_by(is_active=True).order_by(Service.display_order, Service.name).all()

    # Get customer's recent service requests
    recent_requests = ServiceRequest.query.filter_by(user_id=current_user.user_id).order_by(
        ServiceRequest.created_at.desc()
    ).limit(10).all()

    return render_template('service_requests.html', services=services, recent_requests=recent_requests)

@bp.route('/service-request', methods=['POST'])
@login_required
def create_service_request():
    """Create a new service request"""
    if not current_user.is_customer():
        return jsonify({'success': False, 'message': 'Access denied'}), 403

    try:
        data = request.get_json()

        if not data:
            return jsonify({'success': False, 'message': 'No data provided'}), 400

        request_type = data.get('request_type')
        description = data.get('description', '')
        table_id = data.get('table_id')

        if not request_type:
            return jsonify({'success': False, 'message': 'Request type is required'}), 400

        # Create service request
        service_request = ServiceRequest(
            user_id=current_user.user_id,
            table_id=table_id,
            request_type=request_type,
            description=description,
            status='pending'
        )

        db.session.add(service_request)
        db.session.commit()

        # Send real-time notification to waiters
        socketio.emit('new_service_request', {
            'request_id': service_request.request_id,
            'customer_name': current_user.name,
            'customer_id': current_user.user_id,
            'request_type': request_type,
            'description': description,
            'table_id': table_id,
            'timestamp': service_request.created_at.isoformat() if service_request.created_at else datetime.utcnow().isoformat(),
            'status': 'pending'
        }, room='waiter')

        # Also notify admins
        socketio.emit('new_service_request', {
            'request_id': service_request.request_id,
            'customer_name': current_user.name,
            'customer_id': current_user.user_id,
            'request_type': request_type,
            'description': description,
            'table_id': table_id,
            'timestamp': service_request.created_at.isoformat() if service_request.created_at else datetime.utcnow().isoformat(),
            'status': 'pending'
        }, room='admin')

        return jsonify({
            'success': True,
            'message': 'Service request submitted successfully',
            'request_id': service_request.request_id
        })

    except Exception as e:
        db.session.rollback()
        print(f"Error creating service request: {str(e)}")
        return jsonify({'success': False, 'message': 'Failed to submit request'}), 500
