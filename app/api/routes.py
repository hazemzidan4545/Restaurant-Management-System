from flask import jsonify, request, current_app
from flask_login import current_user, login_required
from app.api import bp
from app.models import MenuItem, Category, Order, OrderItem, User, Table, Service, ServiceRequest, TableSession
from app.extensions import db
from datetime import datetime, timedelta
import uuid

@bp.route('/health')
def health():
    """API health check"""
    return jsonify({'status': 'healthy', 'message': 'Restaurant API is running'})

@bp.route('/categories')
def get_categories():
    """Get all menu categories"""
    try:
        categories = Category.query.filter_by(is_active=True).order_by(Category.display_order).all()
        category_list = []

        for category in categories:
            category_list.append({
                'id': category.category_id,
                'name': category.name,
                'description': category.description,
                'display_order': category.display_order,
                'is_active': category.is_active
            })

        return jsonify({
            'status': 'success',
            'data': category_list
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@bp.route('/customers/phone/<phone>')
def get_customer_by_phone(phone):
    """Get customer by phone number (supports n8n integration)"""
    try:
        # Clean phone number (handle both regular and WhatsApp formats)
        clean_phone = phone.replace('@c.us', '').replace('+', '').replace('-', '').replace(' ', '')

        customer = User.query.filter_by(phone=clean_phone, role='customer').first()

        if customer:
            return jsonify({
                'status': 'success',
                'data': {
                    'id': customer.user_id,
                    'name': customer.name,
                    'email': customer.email,
                    'phone': customer.phone,
                    'role': customer.role,
                    'is_active': customer.is_active
                }
            })
        else:
            return jsonify({
                'status': 'error',
                'message': 'Customer not found'
            }), 404

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@bp.route('/customers', methods=['POST'])
def create_customer():
    """Create new customer"""
    try:
        data = request.get_json()

        if not data or not data.get('name') or not data.get('phone'):
            return jsonify({
                'status': 'error',
                'message': 'Name and phone are required'
            }), 400

        # Clean phone number
        clean_phone = data['phone'].replace('+', '').replace('-', '').replace(' ', '')

        # Check if customer already exists
        existing_customer = User.query.filter_by(phone=clean_phone, role='customer').first()
        if existing_customer:
            return jsonify({
                'status': 'error',
                'message': 'Customer with this phone number already exists'
            }), 409

        # Create new customer
        customer = User(
            name=data['name'],
            email=data.get('email'),
            phone=clean_phone,
            password_hash='whatsapp_customer',  # Placeholder for WhatsApp customers
            role='customer',
            is_active=True
        )

        db.session.add(customer)
        db.session.commit()

        return jsonify({
            'status': 'success',
            'data': {
                'id': customer.user_id,
                'name': customer.name,
                'email': customer.email,
                'phone': customer.phone,
                'role': customer.role,
                'is_active': customer.is_active
            }
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@bp.route('/menu-items')
def get_menu_items():
    """Get all available menu items"""
    try:
        items = MenuItem.query.filter_by(status='available').all()
        menu_items = []

        for item in items:
            # Get default image URL based on category
            default_images = {
                'Hookah': 'https://images.unsplash.com/photo-1578662996442-48f60103fc96?w=300&h=200&fit=crop',
                'Drinks': 'https://images.unsplash.com/photo-1544145945-f90425340c7e?w=300&h=200&fit=crop',
                'Brunch': 'https://images.unsplash.com/photo-1533089860892-a7c6f0a88666?w=300&h=200&fit=crop',
                'Main Courses': 'https://images.unsplash.com/photo-1546833999-b9f581a1996d?w=300&h=200&fit=crop',
                'Desserts': 'https://images.unsplash.com/photo-1551024506-0bccd828d307?w=300&h=200&fit=crop'
            }

            category_name = item.category.name if item.category else 'Main Courses'
            image_url = item.image_url or default_images.get(category_name, 'https://images.unsplash.com/photo-1546833999-b9f581a1996d?w=300&h=200&fit=crop')

            menu_items.append({
                'id': item.item_id,
                'name': item.name,
                'description': item.description,
                'price': float(item.price),
                'category': category_name,
                'image': image_url,
                'stock': item.stock
            })

        return jsonify({
            'status': 'success',
            'data': menu_items
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@bp.route('/menu-items/suggested')
def get_suggested_items():
    """Get suggested menu items for cart"""
    try:
        # Get different types of items for variety
        suggested_items = []
        
        # Try to get popular items from different categories
        categories = ['Beverages', 'Main Courses', 'Desserts', 'Appetizers', 'Drinks']
        
        for category_name in categories:
            # Find items from this category
            category_items = MenuItem.query.join(Category).filter(
                Category.name == category_name,
                MenuItem.status == 'available'
            ).limit(1).all()
            
            if category_items:
                suggested_items.extend(category_items)
            
            # Stop if we have enough items
            if len(suggested_items) >= 3:
                break
        
        # If we don't have enough items from specific categories, get random ones
        if len(suggested_items) < 3:
            remaining_needed = 3 - len(suggested_items)
            existing_ids = [item.item_id for item in suggested_items]
            
            additional_items = MenuItem.query.filter(
                MenuItem.status == 'available',
                ~MenuItem.item_id.in_(existing_ids) if existing_ids else True
            ).order_by(db.func.random()).limit(remaining_needed).all()
            
            suggested_items.extend(additional_items)

        # Format response
        response_items = []
        for item in suggested_items[:3]:  # Ensure max 3 items
            # Get default image URL based on category
            default_images = {
                'Hookah': 'https://images.unsplash.com/photo-1578662996442-48f60103fc96?w=200&h=200&fit=crop',
                'Beverages': 'https://images.unsplash.com/photo-1544145945-f90425340c7e?w=200&h=200&fit=crop',
                'Drinks': 'https://images.unsplash.com/photo-1544145945-f90425340c7e?w=200&h=200&fit=crop',
                'Brunch': 'https://images.unsplash.com/photo-1533089860892-a7c6f0a88666?w=200&h=200&fit=crop',
                'Main Courses': 'https://images.unsplash.com/photo-1546833999-b9f581a1996d?w=200&h=200&fit=crop',
                'Desserts': 'https://images.unsplash.com/photo-1551024506-0bccd828d307?w=200&h=200&fit=crop',
                'Appetizers': 'https://images.unsplash.com/photo-1504674900247-0877df9cc836?w=200&h=200&fit=crop'
            }

            category_name = item.category.name if item.category else 'Main Courses'
            image_url = item.image_url or default_images.get(category_name, 'https://images.unsplash.com/photo-1546833999-b9f581a1996d?w=200&h=200&fit=crop')

            response_items.append({
                'id': item.item_id,
                'name': item.name,
                'description': item.description or f'Delicious {category_name.lower()}',
                'price': float(item.price),
                'category': category_name,
                'image': image_url
            })

        return jsonify({
            'status': 'success',
            'data': response_items
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@bp.route('/orders', methods=['POST'])
@login_required
def create_order():
    """Process checkout and create new order"""
    try:
        data = request.get_json()

        # Validate required fields
        if not data or 'items' not in data or 'paymentMethod' not in data:
            return jsonify({
                'status': 'error',
                'message': 'Missing required fields: items and paymentMethod'
            }), 400

        if not data['items']:
            return jsonify({
                'status': 'error',
                'message': 'Cart is empty'
            }), 400

        # Create new order using the logged-in user
        order = Order(
            user_id=current_user.user_id,  # Use the authenticated user's ID
            status='new',
            total_amount=0,  # Will be calculated
            notes=data.get('notes', ''),
            order_time=datetime.utcnow(),
            table_id=data.get('table_id')  # Add table_id if provided
        )

        db.session.add(order)
        db.session.flush()  # Get order ID

        total_amount = 0

        # Process each cart item
        for cart_item in data['items']:
            # Validate item ID format
            item_id = cart_item['id']
            try:
                item_id_int = int(item_id)
                if item_id_int > 1000000:
                    return jsonify({
                        'status': 'error',
                        'message': f'Invalid item ID {item_id}. Please clear your cart and try again.'
                    }), 400
            except (ValueError, TypeError):
                return jsonify({
                    'status': 'error',
                    'message': f'Invalid item ID format: {item_id}'
                }), 400

            # Find menu item
            menu_item = MenuItem.query.get(item_id)
            if not menu_item:
                return jsonify({
                    'status': 'error',
                    'message': f'Menu item {item_id} not found. Please refresh the page and try again.'
                }), 400

            # Check availability
            if menu_item.status != 'available':
                return jsonify({
                    'status': 'error',
                    'message': f'{menu_item.name} is not available'
                }), 400

            # Create order item
            order_item = OrderItem(
                order_id=order.order_id,
                item_id=menu_item.item_id,
                quantity=cart_item['quantity'],
                note=cart_item.get('specialInstructions', ''),
                unit_price=menu_item.price
            )

            db.session.add(order_item)
            total_amount += float(menu_item.price) * cart_item['quantity']

        # Add service charge
        service_charge = 2.00
        total_amount += service_charge

        # Update order total
        order.total_amount = total_amount
        
        # Update table status if a table is associated with this order
        if order.table_id:
            table = Table.query.get(order.table_id)
            if table:
                table.status = 'occupied'  # Mark table as occupied for new orders

        # Commit transaction
        db.session.commit()

        # Generate order number for display
        order_number = f"ORD-{order.order_id:06d}"

        return jsonify({
            'status': 'success',
            'message': 'Order placed successfully',
            'data': {
                'order_id': order.order_id,
                'order_number': order_number,
                'total_amount': float(total_amount),
                'status': order.status,
                'estimated_time': 25,  # Default 25 minutes
                'order_time': order.order_time.isoformat()
            }
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'status': 'error',
            'message': f'Failed to process order: {str(e)}'
        }), 500

@bp.route('/orders/<int:order_id>')
def get_order(order_id):
    """Get order details by ID"""
    try:
        order = Order.query.get_or_404(order_id)

        # Get order items with menu item details
        order_items = []
        for item in order.order_items:
            order_items.append({
                'id': item.item_id,
                'name': item.menu_item.name,
                'quantity': item.quantity,
                'unit_price': float(item.unit_price),
                'total_price': float(item.unit_price * item.quantity),
                'note': item.note
            })

        return jsonify({
            'status': 'success',
            'data': {
                'order_id': order.order_id,
                'order_number': f"ORD-{order.order_id:06d}",
                'status': order.status,
                'total_amount': float(order.total_amount),
                'order_time': order.order_time.isoformat(),
                'estimated_time': order.estimated_time or 25,
                'notes': order.notes,
                'items': order_items
            }
        })

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@bp.route('/orders/<int:order_id>/status', methods=['PUT'])
def update_order_status(order_id):
    """Update order status"""
    try:
        data = request.get_json()

        if not data or 'status' not in data:
            return jsonify({
                'status': 'error',
                'message': 'Status is required'
            }), 400

        valid_statuses = ['new', 'processing', 'completed', 'rejected', 'cancelled']
        if data['status'] not in valid_statuses:
            return jsonify({
                'status': 'error',
                'message': f'Invalid status. Must be one of: {", ".join(valid_statuses)}'
            }), 400

        order = Order.query.get_or_404(order_id)
        previous_status = order.status
        order.status = data['status']

        # Set completion time if order is completed
        if data['status'] == 'completed':
            order.completed_at = datetime.utcnow()

        # Update table status if the order has a table assigned
        # Check table status on ANY order status change, not just completion
        if order.table_id is not None:
            table = order.table
            table.update_status_based_on_orders()  # This now handles the commit
        else:
            # Only commit here if we didn't update a table (since update_status_based_on_orders commits)
            db.session.commit()

        # Award loyalty points when order is completed
        if data['status'] == 'completed' and previous_status != 'completed':
            try:
                from app.modules.loyalty.loyalty_service import award_points_for_order
                current_app.logger.info(f"Attempting to award points for order {order_id} to user {order.user_id}")
                result = award_points_for_order(order_id, order.user_id)
                current_app.logger.info(f"Point awarding result for order {order_id}: {result}")
            except Exception as e:
                current_app.logger.error(f"Error awarding loyalty points for order {order_id}: {str(e)}")
                import traceback
                current_app.logger.error(f"Traceback: {traceback.format_exc()}")

        return jsonify({
            'status': 'success',
            'message': 'Order status updated successfully',
            'data': {
                'order_id': order.order_id,
                'status': order.status,
                'completed_at': order.completed_at.isoformat() if order.completed_at else None
            }
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@bp.route('/orders/<int:order_id>', methods=['PUT'])
def update_order(order_id):
    """Update order details (status, notes, items)"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'status': 'error',
                'message': 'Request data is required'
            }), 400

        order = Order.query.get_or_404(order_id)
        
        # Update status if provided
        if 'status' in data:
            valid_statuses = ['new', 'processing', 'completed', 'rejected', 'cancelled', 'on-hold', 'in-transit']
            if data['status'] in valid_statuses:
                previous_status = order.status
                order.status = data['status']

                # Set completion time if order is completed
                if data['status'] == 'completed':
                    order.completed_at = datetime.utcnow()

                # Award loyalty points when order is completed
                if data['status'] == 'completed' and previous_status != 'completed':
                    try:
                        from app.modules.loyalty.loyalty_service import award_points_for_order
                        current_app.logger.info(f"Attempting to award points for order {order_id} to user {order.user_id}")
                        result = award_points_for_order(order_id, order.user_id)
                        current_app.logger.info(f"Point awarding result for order {order_id}: {result}")
                    except Exception as e:
                        current_app.logger.error(f"Error awarding loyalty points for order {order_id}: {str(e)}")
                        import traceback
                        current_app.logger.error(f"Traceback: {traceback.format_exc()}")
        
        # Update notes if provided
        if 'notes' in data:
            order.notes = data['notes']
        
        # Update items if provided
        if 'items' in data and isinstance(data['items'], list):
            # For now, we'll only update existing items (quantity and notes)
            # Not adding/removing items as that's more complex
            for item_data in data['items']:
                if 'item_id' not in item_data:
                    return jsonify({
                        'status': 'error',
                        'message': 'Item missing item_id'
                    }), 400
                
                # Find the order item
                order_item = None
                for existing_item in order.order_items:
                    if existing_item.item_id == item_data['item_id']:
                        order_item = existing_item
                        break
                
                if order_item:
                    # Update quantity and note
                    if 'quantity' in item_data:
                        order_item.quantity = max(1, int(item_data['quantity']))
                    if 'note' in item_data:
                        order_item.note = item_data['note']
                else:
                    return jsonify({
                        'status': 'error',
                        'message': f'Order item with id {item_data["item_id"]} not found'
                    }), 400
            
            # Recalculate total amount after updating items
            total = sum(item.unit_price * item.quantity for item in order.order_items)
            order.total_amount = total
        
        db.session.commit()

        # Return updated order data
        order_items = []
        for item in order.order_items:
            order_items.append({
                'id': item.item_id,
                'name': item.menu_item.name,
                'quantity': item.quantity,
                'unit_price': float(item.unit_price),
                'total_price': float(item.unit_price * item.quantity),
                'note': item.note
            })

        return jsonify({
            'status': 'success',
            'message': 'Order updated successfully',
            'data': {
                'order_id': order.order_id,
                'order_number': f"ORD-{order.order_id:06d}",
                'status': order.status,
                'total_amount': float(order.total_amount),
                'order_time': order.order_time.isoformat(),
                'estimated_time': order.estimated_time or 25,
                'notes': order.notes,
                'items': order_items
            }
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@bp.route('/admin/sync-table-statuses', methods=['POST'])
def sync_table_statuses():
    """Synchronize all table statuses based on their orders
    
    This is useful for admin purposes if table statuses get out of sync.
    It checks all tables and updates their statuses based on active orders.
    """
    try:
        # Get counts before sync for comparison
        before_occupied = Table.query.filter_by(status='occupied').count()
        active_orders = Order.query.filter(
            Order.status.in_(['new', 'processing']),
            Order.table_id.isnot(None)
        ).count()
        
        print(f"Before sync - Occupied tables: {before_occupied}, Active orders: {active_orders}")
        
        # Call our table update method
        total_count = Table.update_all_table_statuses()
        
        # Get counts after sync
        after_occupied = Table.query.filter_by(status='occupied').count()
        
        print(f"After sync - Total tables: {total_count}, Occupied tables: {after_occupied}")
        
        return jsonify({
            'status': 'success',
            'message': f'Updated status for {total_count} tables. Now {after_occupied} tables are occupied.',
            'data': {
                'total_tables': total_count,
                'occupied_tables': after_occupied,
                'available_tables': total_count - after_occupied
            }
        })

    except Exception as e:
        print(f"Error in sync_table_statuses: {str(e)}")
        import traceback
        traceback.print_exc()
        
        return jsonify({
            'status': 'error',
            'message': f'Error synchronizing table statuses: {str(e)}'
        }), 500

@bp.route('/admin/table-status', methods=['GET'])
def get_table_statuses():
    """Get detailed information about table statuses
    
    This is a debugging endpoint to help diagnose issues with table status tracking.
    It shows each table along with its status and any active orders.
    
    Query parameters:
    - fix=true: Automatically fix any status mismatches
    """
    try:
        auto_fix = request.args.get('fix', 'false').lower() == 'true'
        results = []
        tables = Table.query.all()
        
        # Track tables with mismatches
        mismatched_tables = []
        
        for table in tables:
            # Get active orders for this table
            active_orders = Order.query.filter(
                Order.table_id == table.table_id,
                Order.status.in_(['new', 'processing'])
            ).all()
            
            # Check for status mismatch
            has_active_orders = len(active_orders) > 0
            status_mismatch = (table.status == 'occupied' and not has_active_orders) or \
                             (table.status == 'available' and has_active_orders)
            
            if status_mismatch:
                mismatched_tables.append(table.table_id)
                
                # Auto-fix if requested
                if auto_fix:
                    expected_status = 'occupied' if has_active_orders else 'available'
                    print(f"Fixing table {table.table_number} status: {table.status} -> {expected_status}")
                    table.status = expected_status
            
            # Format active orders
            order_info = []
            for order in active_orders:
                order_info.append({
                    'id': order.order_id,
                    'status': order.status,
                    'time': order.order_time.isoformat() if order.order_time else None,
                    'items_count': Order.query.filter_by(order_id=order.order_id).first().items.count() 
                    if hasattr(Order, 'items') else 0
                })
            
            results.append({
                'table_id': table.table_id,
                'table_number': table.table_number,
                'status': table.status,
                'active_orders_count': len(active_orders),
                'active_orders': order_info,
                'status_mismatch': status_mismatch,
                'expected_status': 'occupied' if has_active_orders else 'available'
            })
        
        # Commit changes if we did auto-fixes
        if auto_fix and mismatched_tables:
            db.session.commit()
            print(f"Fixed status for {len(mismatched_tables)} tables")
        
        # Also get overall stats
        total_tables = Table.query.count()
        occupied_tables = Table.query.filter_by(status='occupied').count()
        tables_with_active_orders = len([t for t in results if t['active_orders_count'] > 0])
        
        mismatch_tables = [
            t for t in results 
            if (t['status'] == 'occupied' and t['active_orders_count'] == 0) or
               (t['status'] == 'available' and t['active_orders_count'] > 0)
        ]
        
        return jsonify({
            'status': 'success',
            'auto_fix_applied': auto_fix,
            'data': {
                'tables': results,
                'stats': {
                    'total_tables': total_tables,
                    'occupied_tables': occupied_tables,
                    'tables_with_active_orders': tables_with_active_orders,
                    'tables_with_status_mismatch': len(mismatch_tables),
                    'mismatch_details': [
                        {
                            'table_id': t['table_id'], 
                            'table_number': t['table_number'],
                            'current': t['status'], 
                            'expected': t['expected_status']
                        }
                        for t in mismatch_tables
                    ]
                }
            }
        })
    except Exception as e:
        print(f"Error in get_table_statuses: {str(e)}")
        import traceback
        traceback.print_exc()
        
        return jsonify({
            'status': 'error',
            'message': f'Error getting table statuses: {str(e)}'
        }), 500

@bp.route('/service_request', methods=['POST'])
@login_required
def create_service_request():
    """Create a new service request from customer"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'message': 'No data provided'
            }), 400
            
        service_id = data.get('service_id')
        if not service_id:
            return jsonify({
                'success': False,
                'message': 'Service ID is required'
            }), 400
            
        # Verify service exists and is active
        service = Service.query.filter_by(service_id=service_id, is_active=True).first()
        if not service:
            return jsonify({
                'success': False,
                'message': 'Service not found or unavailable'
            }), 404
            
        # Get user's current table from session or request data
        table_id = data.get('table_id')
        
        # If no table_id provided, try to get from active table session
        if not table_id and current_user.is_authenticated:
            active_session = TableSession.query.filter(
                TableSession.user_id == current_user.user_id,
                TableSession.is_active == True
            ).order_by(TableSession.started_at.desc()).first()
            
            if active_session:
                table_id = active_session.table_id
        
        if not table_id:
            return jsonify({
                'success': False,
                'message': 'Table assignment required for service request'
            }), 400
        
        # Create service request
        service_request = ServiceRequest(
            service_id=service_id,
            user_id=current_user.user_id,
            table_id=table_id,
            request_type=data.get('request_type', 'general'),
            status='pending',
            description=data.get('description', data.get('notes', ''))
        )
        
        db.session.add(service_request)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'{service.name} request submitted successfully',
            'request_id': service_request.request_id
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error creating service request: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Unable to submit service request. Please try again.'
        }), 500

@bp.route('/table-session', methods=['GET', 'POST'])
def table_session_api():
    """Handle table session operations"""
    
    if request.method == 'GET':
        # Get current table session info
        table_id = request.args.get('table_id', type=int)
        session_token = request.args.get('session_token')
        
        if not table_id:
            return jsonify({
                'success': False,
                'message': 'Table ID is required'
            }), 400
        
        try:
            # Get active session
            table_session = TableSession.get_active_session(
                table_id=table_id,
                user_id=current_user.user_id if current_user.is_authenticated else None,
                session_token=session_token
            )
            
            if not table_session:
                return jsonify({
                    'success': False,
                    'message': 'No active session found'
                }), 404
            
            return jsonify({
                'success': True,
                'session': {
                    'session_id': table_session.session_id,
                    'table_id': table_session.table_id,
                    'session_token': table_session.session_token,
                    'started_at': table_session.started_at.isoformat(),
                    'is_active': table_session.is_active,
                    'table_number': table_session.table.table_number,
                    'table_status': table_session.table.status
                }
            })
            
        except Exception as e:
            return jsonify({
                'success': False,
                'message': f'Error retrieving session: {str(e)}'
            }), 500
    
    elif request.method == 'POST':
        # Create or manage table session
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'message': 'No data provided'
            }), 400
        
        action = data.get('action', 'create')
        table_id = data.get('table_id')
        
        if not table_id:
            return jsonify({
                'success': False,
                'message': 'Table ID is required'
            }), 400
        
        try:
            if action == 'create':
                # Create new session
                device_info = request.headers.get('User-Agent', 'Unknown')
                ip_address = request.remote_addr
                
                table_session = TableSession.create_session(
                    table_id=table_id,
                    user_id=current_user.user_id if current_user.is_authenticated else None,
                    device_info=device_info,
                    ip_address=ip_address
                )
                
                return jsonify({
                    'success': True,
                    'message': 'Session created successfully',
                    'session': {
                        'session_id': table_session.session_id,
                        'session_token': table_session.session_token,
                        'table_id': table_session.table_id
                    }
                })
                
            elif action == 'end':
                # End existing session
                session_token = data.get('session_token')
                table_session = TableSession.get_active_session(
                    table_id=table_id,
                    user_id=current_user.user_id if current_user.is_authenticated else None,
                    session_token=session_token
                )
                
                if table_session:
                    table_session.end_session()
                    
                    # Update table status to available if no other active sessions
                    other_sessions = TableSession.query.filter(
                        TableSession.table_id == table_id,
                        TableSession.is_active == True,
                        TableSession.session_id != table_session.session_id
                    ).count()
                    
                    if other_sessions == 0:
                        table = Table.query.get(table_id)
                        if table:
                            table.status = 'available'
                            db.session.commit()
                    
                    return jsonify({
                        'success': True,
                        'message': 'Session ended successfully'
                    })
                else:
                    return jsonify({
                        'success': False,
                        'message': 'Session not found'
                    }), 404
            
            else:
                return jsonify({
                    'success': False,
                    'message': 'Invalid action'
                }), 400
                
        except Exception as e:
            db.session.rollback()
            return jsonify({
                'success': False,
                'message': f'Error managing session: {str(e)}'
            }), 500

# WhatsApp Bot Integration Endpoints

@bp.route('/orders/whatsapp-legacy', methods=['GET', 'POST'])
def handle_orders_legacy():
    """Handle order operations for WhatsApp bot"""

    if request.method == 'GET':
        # Get orders for a customer
        customer_id = request.args.get('customer_id', type=int)
        limit = request.args.get('limit', 10, type=int)

        if not customer_id:
            return jsonify({
                'status': 'error',
                'message': 'Customer ID is required'
            }), 400

        try:
            orders = Order.query.filter_by(user_id=customer_id).order_by(
                Order.order_time.desc()
            ).limit(limit).all()

            order_list = []
            for order in orders:
                order_items = []
                for item in order.order_items:
                    order_items.append({
                        'id': item.item_id,
                        'name': item.menu_item.name,
                        'quantity': item.quantity,
                        'unit_price': float(item.unit_price),
                        'note': item.note
                    })

                order_list.append({
                    'order_id': order.order_id,
                    'customer_id': order.user_id,
                    'table_id': order.table_id,
                    'status': order.status,
                    'total_amount': float(order.total_amount),
                    'notes': order.notes,
                    'estimated_time': order.estimated_time,
                    'order_time': order.order_time.isoformat(),
                    'items': order_items
                })

            return jsonify({
                'status': 'success',
                'data': order_list
            })

        except Exception as e:
            return jsonify({
                'status': 'error',
                'message': str(e)
            }), 500

    elif request.method == 'POST':
        # Create new order
        try:
            data = request.get_json()

            if not data or not data.get('customer_id') or not data.get('items'):
                return jsonify({
                    'status': 'error',
                    'message': 'Customer ID and items are required'
                }), 400

            # Create order
            order = Order(
                user_id=data['customer_id'],
                table_id=data.get('table_id'),
                status='new',
                notes=data.get('notes', ''),
                estimated_time=25  # Default 25 minutes
            )

            db.session.add(order)
            db.session.flush()  # Get order ID

            # Add order items
            total_amount = 0
            for item_data in data['items']:
                menu_item = MenuItem.query.get(item_data['item_id'])
                if not menu_item:
                    db.session.rollback()
                    return jsonify({
                        'status': 'error',
                        'message': f'Menu item {item_data["item_id"]} not found'
                    }), 400

                order_item = OrderItem(
                    order_id=order.order_id,
                    item_id=item_data['item_id'],
                    quantity=item_data['quantity'],
                    unit_price=menu_item.price,
                    note=item_data.get('note', '')
                )

                db.session.add(order_item)
                total_amount += float(menu_item.price) * item_data['quantity']

            order.total_amount = total_amount
            db.session.commit()

            return jsonify({
                'status': 'success',
                'data': {
                    'id': order.order_id,
                    'customer_id': order.user_id,
                    'table_id': order.table_id,
                    'status': order.status,
                    'total_amount': float(order.total_amount),
                    'estimated_time': order.estimated_time,
                    'order_time': order.order_time.isoformat()
                }
            }), 201

        except Exception as e:
            db.session.rollback()
            return jsonify({
                'status': 'error',
                'message': str(e)
            }), 500

# WhatsApp Table Session Management

@bp.route('/whatsapp-sessions', methods=['POST'])
def create_whatsapp_session():
    """Create a secure table session for WhatsApp customer"""
    try:
        data = request.get_json()

        if not data or not data.get('customer_phone') or not data.get('table_id'):
            return jsonify({
                'status': 'error',
                'message': 'Customer phone and table ID are required'
            }), 400

        customer_phone = data['customer_phone'].replace('@c.us', '').replace('+', '')
        table_id = data['table_id']
        session_token = data.get('session_token')

        # Validate table exists
        table = Table.query.get(table_id)
        if not table:
            return jsonify({
                'status': 'error',
                'message': 'Table not found'
            }), 404

        # Get or create customer
        customer = User.query.filter_by(phone=customer_phone, role='customer').first()
        if not customer:
            return jsonify({
                'status': 'error',
                'message': 'Customer not found'
            }), 404

        # Check for existing active session for this table
        existing_session = TableSession.query.filter_by(
            table_id=table_id,
            is_active=True
        ).first()

        if existing_session and existing_session.user_id != customer.user_id:
            return jsonify({
                'status': 'error',
                'message': 'Table is already occupied by another customer'
            }), 409

        # Create or update session
        if existing_session and existing_session.user_id == customer.user_id:
            # Update existing session
            existing_session.session_token = session_token
            existing_session.started_at = datetime.utcnow()
            table_session = existing_session
        else:
            # Create new session
            table_session = TableSession(
                table_id=table_id,
                user_id=customer.user_id,
                session_token=session_token,
                device_info=request.headers.get('User-Agent', 'WhatsApp Bot'),
                ip_address=request.remote_addr
            )
            db.session.add(table_session)

        # Update table status
        if table.status == 'available':
            table.status = 'occupied'

        db.session.commit()

        return jsonify({
            'status': 'success',
            'data': {
                'session_id': table_session.session_id,
                'session_token': table_session.session_token,
                'table_id': table_session.table_id,
                'customer_id': table_session.user_id,
                'expires_at': (table_session.started_at + timedelta(hours=4)).isoformat()
            }
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@bp.route('/whatsapp-sessions/<session_token>/validate', methods=['GET'])
def validate_whatsapp_session(session_token):
    """Enhanced WhatsApp session token validation with security checks"""
    try:
        # Security Check 1: Validate session token format
        if not session_token or len(session_token) < 32:
            return jsonify({
                'status': 'error',
                'message': 'Invalid session token format'
            }), 400

        # Find active session
        table_session = TableSession.query.filter_by(
            session_token=session_token,
            is_active=True
        ).first()

        if not table_session:
            return jsonify({
                'status': 'error',
                'message': 'Invalid or expired session'
            }), 404

        # Security Check 2: Check if session is expired (4 hours)
        session_age = datetime.utcnow() - table_session.started_at
        if session_age > timedelta(hours=4):
            table_session.is_active = False
            db.session.commit()
            return jsonify({
                'status': 'error',
                'message': 'Session expired'
            }), 401

        # Security Check 3: Rate limiting - check for too many validation requests
        # (In production, implement proper rate limiting with Redis)

        # Security Check 4: IP address validation (optional)
        current_ip = request.remote_addr
        if table_session.ip_address and table_session.ip_address != current_ip:
            # Log but don't block (mobile networks change IPs)
            print(f"IP change detected for session {session_token}: {table_session.ip_address} -> {current_ip}")

        # Update last activity timestamp
        table_session.last_activity = datetime.utcnow()
        db.session.commit()

        return jsonify({
            'status': 'success',
            'data': {
                'session_id': table_session.session_id,
                'table_id': table_session.table_id,
                'customer_id': table_session.user_id,
                'customer_name': table_session.user.name,
                'table_number': table_session.table.table_number,
                'started_at': table_session.started_at.isoformat(),
                'expires_at': (table_session.started_at + timedelta(hours=4)).isoformat(),
                'remaining_time': str(timedelta(hours=4) - session_age)
            }
        })

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@bp.route('/whatsapp-sessions/<session_token>', methods=['DELETE'])
def end_whatsapp_session(session_token):
    """End WhatsApp session"""
    try:
        table_session = TableSession.query.filter_by(
            session_token=session_token,
            is_active=True
        ).first()

        if not table_session:
            return jsonify({
                'status': 'error',
                'message': 'Session not found'
            }), 404

        # End session
        table_session.end_session()

        # Update table status if no other active sessions
        other_sessions = TableSession.query.filter_by(
            table_id=table_session.table_id,
            is_active=True
        ).count()

        if other_sessions == 0:
            table_session.table.status = 'available'
            db.session.commit()

        return jsonify({
            'status': 'success',
            'message': 'Session ended successfully'
        })

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@bp.route('/customers/<int:customer_id>')
def get_customer_by_id(customer_id):
    """Get customer by ID"""
    try:
        customer = User.query.filter_by(user_id=customer_id, role='customer').first()

        if customer:
            return jsonify({
                'status': 'success',
                'data': {
                    'id': customer.user_id,
                    'name': customer.name,
                    'email': customer.email,
                    'phone': customer.phone,
                    'role': customer.role,
                    'is_active': customer.is_active
                }
            })
        else:
            return jsonify({
                'status': 'error',
                'message': 'Customer not found'
            }), 404

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

# n8n Integration Endpoints

@bp.route('/menu/categories')
def get_menu_categories():
    """Get all menu categories for n8n integration"""
    try:
        categories = Category.query.filter_by(is_active=True).order_by(Category.display_order).all()

        category_list = []
        for category in categories:
            category_list.append({
                'id': category.category_id,
                'name': category.name,
                'description': category.description,
                'display_order': category.display_order,
                'is_active': category.is_active
            })

        return jsonify({
            'status': 'success',
            'data': category_list
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@bp.route('/menu/items/<int:category_id>')
def get_items_by_category(category_id):
    """Get menu items by category for n8n integration"""
    try:
        items = MenuItem.query.filter_by(category_id=category_id, status='available').all()

        item_list = []
        for item in items:
            item_list.append({
                'id': item.item_id,
                'name': item.name,
                'description': item.description,
                'price': float(item.price),
                'category_id': item.category_id,
                'image_url': item.image_url,
                'stock': item.stock,
                'status': item.status
            })

        return jsonify({
            'status': 'success',
            'data': item_list
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@bp.route('/menu/item/<int:item_id>')
def get_menu_item(item_id):
    """Get specific menu item details for n8n integration"""
    try:
        item = MenuItem.query.get_or_404(item_id)

        return jsonify({
            'status': 'success',
            'data': {
                'id': item.item_id,
                'name': item.name,
                'description': item.description,
                'price': float(item.price),
                'category_id': item.category_id,
                'category_name': item.category.name if item.category else None,
                'image_url': item.image_url,
                'stock': item.stock,
                'status': item.status
            }
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@bp.route('/orders/customer/<phone>')
def get_customer_orders_by_phone(phone):
    """Get customer orders by phone number for n8n integration"""
    try:
        # Clean phone number
        clean_phone = phone.replace('@c.us', '').replace('+', '').replace('-', '').replace(' ', '')

        customer = User.query.filter_by(phone=clean_phone, role='customer').first()
        if not customer:
            return jsonify({
                'status': 'error',
                'message': 'Customer not found'
            }), 404

        orders = Order.query.filter_by(user_id=customer.user_id).order_by(Order.order_time.desc()).limit(10).all()

        order_list = []
        for order in orders:
            order_items = []
            for item in order.order_items:
                order_items.append({
                    'id': item.item_id,
                    'name': item.menu_item.name,
                    'quantity': item.quantity,
                    'unit_price': float(item.unit_price),
                    'total_price': float(item.unit_price * item.quantity),
                    'note': item.note
                })

            order_list.append({
                'order_id': order.order_id,
                'order_number': f"ORD-{order.order_id:06d}",
                'status': order.status,
                'total_amount': float(order.total_amount),
                'order_time': order.order_time.isoformat(),
                'estimated_time': order.estimated_time or 25,
                'notes': order.notes,
                'items': order_items
            })

        return jsonify({
            'status': 'success',
            'data': order_list
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@bp.route('/orders/whatsapp', methods=['POST'])
def create_whatsapp_order():
    """Create order from WhatsApp via n8n integration"""
    try:
        data = request.get_json()

        if not data:
            return jsonify({
                'status': 'error',
                'message': 'No data provided'
            }), 400

        # Required fields
        customer_phone = data.get('customer_phone')
        items = data.get('items', [])

        if not customer_phone or not items:
            return jsonify({
                'status': 'error',
                'message': 'Customer phone and items are required'
            }), 400

        # Clean phone number
        clean_phone = customer_phone.replace('@c.us', '').replace('+', '').replace('-', '').replace(' ', '')

        # Get or create customer
        customer = User.query.filter_by(phone=clean_phone, role='customer').first()
        if not customer:
            # Create new customer with basic info
            customer = User(
                name=data.get('customer_name', f'WhatsApp Customer {clean_phone[-4:]}'),
                phone=clean_phone,
                password_hash='whatsapp_customer',
                role='customer',
                is_active=True
            )
            db.session.add(customer)
            db.session.flush()

        # Create order
        order = Order(
            user_id=customer.user_id,
            table_id=data.get('table_id'),
            notes=data.get('notes', ''),
            status='new'
        )
        db.session.add(order)
        db.session.flush()

        total_amount = 0
        order_items = []

        # Add order items
        for item_data in items:
            item_id = item_data.get('item_id')
            quantity = item_data.get('quantity', 1)
            note = item_data.get('note', '')

            menu_item = MenuItem.query.get(item_id)
            if not menu_item:
                db.session.rollback()
                return jsonify({
                    'status': 'error',
                    'message': f'Menu item {item_id} not found'
                }), 404

            if menu_item.status != 'available':
                db.session.rollback()
                return jsonify({
                    'status': 'error',
                    'message': f'Menu item {menu_item.name} is not available'
                }), 400

            order_item = OrderItem(
                order_id=order.order_id,
                item_id=item_id,
                quantity=quantity,
                unit_price=menu_item.price,
                note=note
            )
            db.session.add(order_item)

            total_amount += float(menu_item.price) * quantity
            order_items.append({
                'name': menu_item.name,
                'quantity': quantity,
                'unit_price': float(menu_item.price),
                'total_price': float(menu_item.price) * quantity,
                'note': note
            })

        order.total_amount = total_amount
        db.session.commit()

        return jsonify({
            'status': 'success',
            'data': {
                'order_id': order.order_id,
                'order_number': f"ORD-{order.order_id:06d}",
                'customer_id': customer.user_id,
                'customer_name': customer.name,
                'customer_phone': customer.phone,
                'total_amount': total_amount,
                'status': order.status,
                'items': order_items,
                'estimated_time': 25
            }
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@bp.route('/orders/<int:order_id>/status/n8n', methods=['PUT'])
def update_order_status_n8n(order_id):
    """Update order status for n8n integration"""
    try:
        data = request.get_json()
        new_status = data.get('status')

        if not new_status:
            return jsonify({
                'status': 'error',
                'message': 'Status is required'
            }), 400

        if new_status not in ['new', 'processing', 'completed', 'rejected', 'cancelled']:
            return jsonify({
                'status': 'error',
                'message': 'Invalid status'
            }), 400

        order = Order.query.get_or_404(order_id)
        order.status = new_status

        if new_status == 'completed':
            order.completion_time = datetime.utcnow()

        db.session.commit()

        return jsonify({
            'status': 'success',
            'data': {
                'order_id': order.order_id,
                'status': order.status,
                'completion_time': order.completion_time.isoformat() if order.completion_time else None
            }
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@bp.route('/tables/<int:table_id>')
def get_table_info(table_id):
    """Get table information for n8n integration"""
    try:
        table = Table.query.get_or_404(table_id)

        return jsonify({
            'status': 'success',
            'data': {
                'id': table.table_id,
                'number': table.table_number,
                'capacity': table.capacity,
                'status': table.status,
                'location': table.location
            }
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@bp.route('/tables/<int:table_id>/service-request', methods=['POST'])
def create_table_service_request(table_id):
    """Create service request for table via n8n integration"""
    try:
        data = request.get_json()

        customer_phone = data.get('customer_phone')
        request_type = data.get('request_type', 'general')
        description = data.get('description', '')

        if not customer_phone:
            return jsonify({
                'status': 'error',
                'message': 'Customer phone is required'
            }), 400

        # Clean phone number and get customer
        clean_phone = customer_phone.replace('@c.us', '').replace('+', '').replace('-', '').replace(' ', '')
        customer = User.query.filter_by(phone=clean_phone, role='customer').first()

        if not customer:
            return jsonify({
                'status': 'error',
                'message': 'Customer not found'
            }), 404

        # Validate table exists
        table = Table.query.get_or_404(table_id)

        # Create service request
        service_request = ServiceRequest(
            user_id=customer.user_id,
            table_id=table_id,
            request_type=request_type,
            description=description,
            status='pending'
        )

        db.session.add(service_request)
        db.session.commit()

        return jsonify({
            'status': 'success',
            'data': {
                'request_id': service_request.request_id,
                'table_id': table_id,
                'customer_id': customer.user_id,
                'request_type': request_type,
                'description': description,
                'status': service_request.status,
                'created_at': service_request.created_at.isoformat()
            }
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500



@bp.route('/service-requests', methods=['POST'])
def create_whatsapp_service_request():
    """Create service request for WhatsApp bot"""
    try:
        data = request.get_json()

        if not data or not data.get('customer_id') or not data.get('table_id'):
            return jsonify({
                'status': 'error',
                'message': 'Customer ID and table ID are required'
            }), 400

        service_request = ServiceRequest(
            user_id=data['customer_id'],
            table_id=data['table_id'],
            service_type=data.get('service_type', 'general'),
            description=data.get('description', ''),
            status='pending',
            priority='normal'
        )

        db.session.add(service_request)
        db.session.commit()

        return jsonify({
            'status': 'success',
            'data': {
                'id': service_request.request_id,
                'status': service_request.status
            }
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@bp.route('/loyalty/points/<int:customer_id>')
def get_loyalty_points(customer_id):
    """Get customer loyalty points"""
    try:
        from app.models import CustomerLoyalty

        loyalty = CustomerLoyalty.query.filter_by(user_id=customer_id).first()

        if loyalty:
            return jsonify({
                'status': 'success',
                'points': loyalty.total_points
            })
        else:
            return jsonify({
                'status': 'success',
                'points': 0
            })

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@bp.route('/loyalty/rewards')
def get_loyalty_rewards():
    """Get available loyalty rewards"""
    try:
        from app.models import RewardItem

        rewards = RewardItem.query.filter_by(status='active').all()

        reward_list = []
        for reward in rewards:
            reward_list.append({
                'id': reward.reward_id,
                'name': reward.name,
                'description': reward.description,
                'points_required': reward.points_required,
                'category': reward.category
            })

        return jsonify({
            'status': 'success',
            'data': reward_list
        })

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500
