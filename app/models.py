from datetime import datetime, timedelta
from decimal import Decimal
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import Numeric
from sqlalchemy.orm import foreign
from app.extensions import db

class User(UserMixin, db.Model):
    """Unified user model with role-based permissions"""
    __tablename__ = 'users'
    
    user_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    phone = db.Column(db.String(20), nullable=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.Enum('customer', 'admin', 'waiter', name='user_roles'), nullable=False, default='customer')
    profile_img = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    language_preference = db.Column(db.String(5), default='ar')  # 'ar' for Arabic, 'en' for English
    
    # Relationships
    orders = db.relationship('Order', backref='customer', lazy='dynamic')
    service_requests = db.relationship('ServiceRequest',
                                     foreign_keys='ServiceRequest.user_id',
                                     backref='customer', lazy='dynamic')
    handled_requests = db.relationship('ServiceRequest',
                                     foreign_keys='ServiceRequest.handled_by',
                                     backref='handler', lazy='dynamic')
    notifications = db.relationship('Notification', backref='user', lazy='dynamic')
    feedback = db.relationship('Feedback', backref='user', lazy='dynamic')
    loyalty_account = db.relationship('CustomerLoyalty', back_populates='user', uselist=False)
    point_transactions = db.relationship('PointTransaction', backref='user', lazy='dynamic')
    reward_redemptions = db.relationship('RewardRedemption', backref='user', lazy='dynamic')
    audit_logs = db.relationship('AuditLog', backref='user', lazy='dynamic')
    
    @classmethod
    def get_active_staff_count(cls):
        """Get count of active staff members (admin and waiters)"""
        return cls.query.filter(
            cls.role.in_(['admin', 'waiter']),
            cls.is_active == True
        ).count()
    
    def get_id(self):
        return str(self.user_id)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def is_admin(self):
        return self.role == 'admin'
    
    def is_waiter(self):
        return self.role == 'waiter'
    
    def is_customer(self):
        return self.role == 'customer'
    
    def __repr__(self):
        return f'<User {self.email}>'

class Table(db.Model):
    """Physical restaurant tables"""
    __tablename__ = 'tables'
    
    table_id = db.Column(db.Integer, primary_key=True)
    table_number = db.Column(db.String(10), unique=True, nullable=False)
    status = db.Column(db.Enum('available', 'occupied', 'reserved', name='table_status'), 
                      nullable=False, default='available')
    capacity = db.Column(db.Integer, nullable=False, default=4)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    orders = db.relationship('Order', backref='table', lazy='dynamic')
    service_requests = db.relationship('ServiceRequest', backref='table', lazy='dynamic')
    qr_codes = db.relationship('QRCode', backref='table', lazy='dynamic')
    
    @classmethod
    def get_tables_with_active_orders(cls):
        """Get count of tables that have active (new/processing) orders"""
        from sqlalchemy import func, distinct
        
        return db.session.query(func.count(distinct(cls.table_id))).join(
            Order, Order.table_id == cls.table_id
        ).filter(
            Order.status.in_(['new', 'processing'])
        ).scalar() or 0
    
    @classmethod
    def get_occupied_tables_count(cls):
        """Get count of tables that are currently occupied based on table status and active orders
        
        This is a more accurate way to count occupied tables, as it:
        1. Checks tables explicitly marked as 'occupied'
        2. Includes tables with active orders even if not explicitly marked
        """
        from sqlalchemy import func, distinct, or_, and_
        
        # Let's first try to get tables that are explicitly marked as occupied
        explicitly_marked = cls.query.filter_by(status='occupied').count()
        print(f"Tables explicitly marked as occupied: {explicitly_marked}")
        
        # Now get tables with active orders
        tables_with_orders = db.session.query(func.count(distinct(Order.table_id))).filter(
            Order.status.in_(['new', 'processing']),
            Order.table_id.isnot(None)
        ).scalar() or 0
        print(f"Tables with active orders: {tables_with_orders}")
        
        # For the combined count, use a query with OR condition to get tables that are either
        # marked as occupied OR have active orders
        occupied_tables_count = db.session.query(func.count(distinct(cls.table_id))).outerjoin(
            Order, Order.table_id == cls.table_id
        ).filter(
            or_(
                cls.status == 'occupied',
                and_(
                    Order.status.in_(['new', 'processing']),
                    Order.table_id.isnot(None)
                )
            )
        ).scalar() or 0
        
        print(f"Combined occupied tables count: {occupied_tables_count}")
        
        # If there's a mismatch, update table statuses to match reality
        if occupied_tables_count != explicitly_marked:
            print(f"Mismatch detected between occupied status ({explicitly_marked}) and actual occupied tables ({occupied_tables_count})")
            # Force an update of table statuses to match reality
            cls.update_all_table_statuses()
            # Recalculate after update
            occupied_tables_count = cls.query.filter_by(status='occupied').count()
            print(f"After forced update: {occupied_tables_count} tables are occupied")
        
        return occupied_tables_count
    
    def update_status_based_on_orders(self):
        """Update the table's status based on its active orders
        
        If there are any active orders (new or processing), mark as occupied.
        If no active orders, mark as available.
        """
        # Check if there are any active orders for this table
        active_orders_count = self.orders.filter(Order.status.in_(['new', 'processing'])).count()
        
        # Get old status for logging
        old_status = self.status
        
        # Update status accordingly
        if active_orders_count > 0:
            # If there are active orders, table should be occupied
            self.status = 'occupied'
        else:
            # If no active orders, table can be available
            self.status = 'available'
        
        # Log status change if it changed
        if old_status != self.status:
            print(f"Table {self.table_number} status changed from {old_status} to {self.status}")
        
        # Make sure changes are saved immediately
        db.session.commit()
        
        return self.status
    
    @classmethod
    def update_all_table_statuses(cls):
        """Update all tables' statuses based on their orders.
        This can be used for a system-wide refresh if needed.
        """
        # Count tables before update for logging
        total_tables = cls.query.count()
        
        # Get tables with their status before the update for logging
        tables_before = {table.table_id: table.status for table in cls.query.all()}
        
        # First, reset all tables to available
        cls.query.update({cls.status: 'available'}, synchronize_session=False)
        
        # Then identify tables with active orders and set them to occupied
        occupied_table_ids = db.session.query(Order.table_id).filter(
            Order.status.in_(['new', 'processing']),
            Order.table_id.isnot(None)
        ).distinct().all()
        
        occupied_ids = [t[0] for t in occupied_table_ids]
        print(f"Found {len(occupied_ids)} tables with active orders: {occupied_ids}")
        
        if occupied_ids:
            update_result = cls.query.filter(cls.table_id.in_(occupied_ids)).update(
                {cls.status: 'occupied'}, 
                synchronize_session=False
            )
            print(f"Updated {update_result} tables to 'occupied' status")
        
        # Get tables with their status after the update for logging
        tables_after = {table.table_id: table.status for table in cls.query.all()}
        
        # Log changed tables
        changed_tables = []
        for table_id, status_after in tables_after.items():
            status_before = tables_before.get(table_id)
            if status_before != status_after:
                changed_tables.append(f"Table {table_id}: {status_before} -> {status_after}")
        
        if changed_tables:
            print(f"Changed table statuses: {'; '.join(changed_tables)}")
        else:
            print("No table statuses changed")
        
        # Commit all changes
        db.session.commit()
        
        # Final verification - count currently occupied tables
        occupied_count = cls.query.filter_by(status='occupied').count()
        print(f"After sync: {occupied_count} tables are occupied")
        
        return total_tables
    
    def __repr__(self):
        return f'<Table {self.table_number}>'

class Category(db.Model):
    """Menu organization categories"""
    __tablename__ = 'categories'
    
    category_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    display_order = db.Column(db.Integer, nullable=False, default=0)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    menu_items = db.relationship('MenuItem', backref='category', lazy='dynamic')
    
    def __repr__(self):
        return f'<Category {self.name}>'

class MenuItem(db.Model):
    """Food and service items"""
    __tablename__ = 'menu_items'

    item_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    price = db.Column(Numeric(10, 2), nullable=False)  # EGP
    category_id = db.Column(db.Integer, db.ForeignKey('categories.category_id'), nullable=False)
    image_url = db.Column(db.String(255), nullable=True)
    stock = db.Column(db.Integer, nullable=False, default=0)
    status = db.Column(db.Enum('available', 'out_of_stock', 'discontinued', name='item_status'),
                      nullable=False, default='available')

    # Discount and pricing information
    discount_percentage = db.Column(Numeric(5, 2), nullable=True, default=0.00)  # Discount percentage (0-100)
    original_price = db.Column(Numeric(10, 2), nullable=True)  # Original price before discount

    # Nutritional and detailed information
    ingredients = db.Column(db.Text, nullable=True)
    calories = db.Column(db.Integer, nullable=True)
    preparation_time = db.Column(db.Integer, nullable=True)  # in minutes
    allergens = db.Column(db.String(255), nullable=True)
    serving_size = db.Column(db.String(50), nullable=True)
    dietary_info = db.Column(db.String(255), nullable=True)  # vegetarian, vegan, gluten-free, etc.

    # Special options
    is_featured = db.Column(db.Boolean, nullable=False, default=False)
    is_spicy = db.Column(db.Boolean, nullable=False, default=False)
    is_vegetarian = db.Column(db.Boolean, nullable=False, default=False)
    is_vegan = db.Column(db.Boolean, nullable=False, default=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    order_items = db.relationship('OrderItem', backref='menu_item', lazy='dynamic', foreign_keys='OrderItem.item_id')
    images = db.relationship('MenuItemImage', backref='menu_item', lazy='dynamic')
    feedback = db.relationship('Feedback', backref='menu_item', lazy='dynamic')
    reward_items = db.relationship('RewardItem', backref='menu_item', lazy='dynamic')
    
    @classmethod
    def get_popular_items(cls, limit=4):
        """Get the most popular menu items based on order frequency"""
        from sqlalchemy import func

        popular_items = db.session.query(
            cls,
            func.sum(OrderItem.quantity).label('total_ordered')
        ).join(OrderItem).join(Order, OrderItem.order_id == Order.order_id).filter(
            cls.status == 'available',
            Order.status == 'completed'
        ).group_by(cls.item_id).order_by(
            func.sum(OrderItem.quantity).desc()
        ).limit(limit).all()

        # Return just the menu items (not the tuples with counts)
        return [item[0] for item in popular_items]

    @classmethod
    def get_popular_items_with_counts(cls, limit=10, start_date=None, end_date=None):
        """Get popular items with their order counts for analytics
        
        Args:
            limit (int): Maximum number of results to return
            start_date (datetime): Optional start date for filtering
            end_date (datetime): Optional end date for filtering
        """
        from sqlalchemy import func
        
        query = db.session.query(
            cls,
            func.sum(OrderItem.quantity).label('total_ordered')
        ).join(OrderItem).join(Order, OrderItem.order_id == Order.order_id)

        # Apply filters - only include completed orders
        query = query.filter(cls.status == 'available')
        query = query.filter(Order.status == 'completed')

        # Apply date filtering if specified
        if start_date:
            query = query.filter(Order.order_time >= start_date)
        if end_date:
            query = query.filter(Order.order_time <= end_date)
            
        return query.group_by(cls.item_id).order_by(
            func.sum(OrderItem.quantity).desc()
        ).limit(limit).all()

    def get_average_rating(self):
        """Get the average rating for this menu item"""
        from sqlalchemy import func
        
        result = db.session.query(
            func.avg(Feedback.rating).label('avg_rating'),
            func.count(Feedback.feedback_id).label('review_count')
        ).filter(
            Feedback.item_id == self.item_id,
            Feedback.is_approved == True
        ).first()
        
        if result.review_count > 0:
            return {
                'average': round(float(result.avg_rating), 1),
                'count': result.review_count
            }
        else:
            return {
                'average': 0.0,
                'count': 0
            }

    def get_rating_distribution(self):
        """Get the distribution of ratings (1-5 stars) for this menu item"""
        from sqlalchemy import func
        
        ratings = db.session.query(
            Feedback.rating,
            func.count(Feedback.feedback_id).label('count')
        ).filter(
            Feedback.item_id == self.item_id,
            Feedback.is_approved == True
        ).group_by(Feedback.rating).all()
        
        # Initialize distribution with zeros
        distribution = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        
        # Fill in actual counts
        for rating, count in ratings:
            distribution[rating] = count
            
        return distribution

    def get_discounted_price(self):
        """Get the discounted price (alias for get_display_price for compatibility)"""
        return self.get_display_price()

    def get_display_price(self):
        """Get the current display price (with discount applied if any)"""
        if self.discount_percentage and self.discount_percentage > 0:
            discount_multiplier = (100 - float(self.discount_percentage)) / 100
            return float(self.price) * discount_multiplier
        return float(self.price)
    
    def get_original_price(self):
        """Get the original price before any discounts"""
        return float(self.original_price) if self.original_price else float(self.price)
    
    def has_discount(self):
        """Check if this item has an active discount"""
        return self.discount_percentage and self.discount_percentage > 0
    
    def get_discount_amount(self):
        """Calculate the discount amount in EGP"""
        if self.has_discount():
            original = self.get_original_price()
            discounted = self.get_display_price()
            return original - discounted
        return 0

    def apply_discount(self, discount_percentage):
        """Apply a discount to this menu item"""
        if not self.original_price:
            self.original_price = self.price
        self.discount_percentage = discount_percentage

    def remove_discount(self):
        """Remove discount and restore original price"""
        if self.original_price:
            self.price = self.original_price
        self.discount_percentage = 0.00
        self.original_price = None



    def __repr__(self):
        return f'<MenuItem {self.name}>'

class MenuItemImage(db.Model):
    """Multiple images per menu item"""
    __tablename__ = 'menu_item_images'
    
    image_id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey('menu_items.item_id'), nullable=False)
    image_url = db.Column(db.String(255), nullable=False)
    is_primary = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<MenuItemImage {self.image_url}>'

class Order(db.Model):
    """Customer orders with status tracking"""
    __tablename__ = 'orders'

    order_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    table_id = db.Column(db.Integer, db.ForeignKey('tables.table_id'), nullable=True)
    order_time = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.Enum('new', 'processing', 'completed', 'rejected', 'cancelled', name='order_status'),
                      nullable=False, default='new')
    total_amount = db.Column(Numeric(10, 2), nullable=False, default=0.00)
    notes = db.Column(db.Text, nullable=True)
    estimated_time = db.Column(db.Integer, nullable=True)  # minutes
    completed_at = db.Column(db.DateTime, nullable=True)

    # Relationships
    order_items = db.relationship('OrderItem', backref='order', lazy='dynamic', cascade='all, delete-orphan')
    payments = db.relationship('Payment', backref='order', lazy='dynamic')
    point_transactions = db.relationship('PointTransaction', backref='order', lazy='dynamic')
    reward_redemptions = db.relationship('RewardRedemption', backref='order', lazy='dynamic')

    def calculate_total(self):
        """Calculate total amount from order items"""
        total = sum(item.quantity * item.menu_item.price for item in self.order_items)
        self.total_amount = total
        return total

    def award_loyalty_points(self):
        """Award loyalty points when order is completed"""
        if self.status == 'completed' and self.user_id:
            # Get or create customer loyalty account
            loyalty_account = CustomerLoyalty.query.filter_by(user_id=self.user_id).first()
            if not loyalty_account:
                loyalty_account = CustomerLoyalty(user_id=self.user_id)
                db.session.add(loyalty_account)
                db.session.flush()  # Get the ID
            
            # Calculate points based on order total
            points_to_award = loyalty_account.calculate_loyalty_points(float(self.total_amount))
            
            # Check if points already awarded for this order
            existing_transaction = PointTransaction.query.filter_by(
                order_id=self.order_id, 
                transaction_type='earned'
            ).first()
            
            if not existing_transaction and points_to_award > 0:
                # Award points
                transaction = loyalty_account.add_points(
                    points_to_award, 
                    order_id=self.order_id,
                    description=f"Points earned from order #{self.order_id}"
                )
                
                # Create notification
                from app.models import Notification
                notification = Notification(
                    user_id=self.user_id,
                    message=f"You earned {points_to_award} loyalty points from your order!",
                    notification_type='loyalty_points'
                )
                db.session.add(notification)
                
                db.session.commit()
                return points_to_award
        
        return 0

    @classmethod
    def get_new_orders_count(cls):
        """Get count of new orders that need attention"""
        return cls.query.filter(cls.status.in_(['new', 'processing'])).count()

    @classmethod
    def get_recent_orders_count(cls, hours=24):
        """Get count of orders from the last N hours"""
        from datetime import datetime, timedelta, timezone
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)
        return cls.query.filter(cls.order_time >= cutoff_time).count()

    def __repr__(self):
        return f'<Order {self.order_id}>'

class OrderItem(db.Model):
    """Individual items within orders"""
    __tablename__ = 'order_items'

    order_item_id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.order_id'), nullable=False)
    item_id = db.Column(db.Integer, db.ForeignKey('menu_items.item_id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    note = db.Column(db.String(255), nullable=True)  # customizations like "No Onions"
    unit_price = db.Column(Numeric(10, 2), nullable=False)
    
    # Note: The relationship to MenuItem is defined in the MenuItem class with backref='menu_item'

    def __repr__(self):
        return f'<OrderItem {self.order_item_id}>'

class Payment(db.Model):
    """Payment tracking and processing"""
    __tablename__ = 'payments'

    payment_id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.order_id'), nullable=False)
    amount = db.Column(Numeric(10, 2), nullable=False)
    payment_type = db.Column(db.Enum('cash', 'card', 'wallet', name='payment_types'),
                           nullable=False, default='cash')
    status = db.Column(db.Enum('pending', 'completed', 'failed', 'refunded', name='payment_status'),
                      nullable=False, default='pending')
    transaction_id = db.Column(db.String(100), nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Payment {self.payment_id}>'

class Service(db.Model):
    """Available services for customers"""
    __tablename__ = 'services'

    service_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    icon = db.Column(db.String(50), nullable=False, default='fas fa-concierge-bell')
    description = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    display_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship with service requests (manual join condition)
    service_requests = db.relationship(
        'ServiceRequest', 
        primaryjoin='Service.service_id == foreign(ServiceRequest.service_id)',
        backref='service', 
        lazy='dynamic'
    )

    def __repr__(self):
        return f'<Service {self.name}>'

class ServiceRequest(db.Model):
    """Waiter service requests"""
    __tablename__ = 'service_requests'

    request_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    table_id = db.Column(db.Integer, db.ForeignKey('tables.table_id'), nullable=True)  # Allow null for general requests
    service_id = db.Column(db.Integer, nullable=True)  # Removed FK constraint for now
    request_type = db.Column(db.String(50), nullable=False)  # 'clean_table', 'refill_coals', 'adjust_ac', etc.
    status = db.Column(db.String(12), nullable=False, default='pending')  # 'pending', 'acknowledged', 'completed'
    description = db.Column(db.Text, nullable=True)  # Additional details about the request
    handled_by = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=True)  # Waiter who handled the request
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Keep timestamp for backward compatibility
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<ServiceRequest {self.request_id}>'

class Notification(db.Model):
    """System-wide messaging"""
    __tablename__ = 'notifications'

    notification_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    notification_type = db.Column(db.Enum('order_update', 'service_request', 'loyalty_points', 'system', name='notification_types'),
                                nullable=False, default='system')
    seen = db.Column(db.Boolean, default=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Notification {self.notification_id}>'

class Feedback(db.Model):
    """Customer reviews and ratings"""
    __tablename__ = 'feedback'

    feedback_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    item_id = db.Column(db.Integer, db.ForeignKey('menu_items.item_id'), nullable=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.order_id'), nullable=True)
    rating = db.Column(db.Integer, nullable=False)  # 1-5 scale
    comment = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    is_approved = db.Column(db.Boolean, default=True)

    def __repr__(self):
        return f'<Feedback {self.feedback_id}>'

class LoyaltyProgram(db.Model):
    """Point-based customer rewards program"""
    __tablename__ = 'loyalty_programs'

    program_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    points_per_50EGP = db.Column(db.Integer, nullable=False, default=100)
    points_value = db.Column(db.Float, nullable=False, default=1.0)  # EGP value per 100 points
    min_redemption = db.Column(db.Integer, nullable=False, default=100)  # Minimum points for redemption
    max_redemption_percentage = db.Column(db.Integer, nullable=False, default=50)  # Max % of order total
    status = db.Column(db.Enum('active', 'inactive', name='program_status'),
                      nullable=False, default='active')
    created_date = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<LoyaltyProgram {self.name}>'

class CustomerLoyalty(db.Model):
    """Individual customer loyalty accounts"""
    __tablename__ = 'customer_loyalty'

    loyalty_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False, unique=True)
    total_points = db.Column(db.Integer, nullable=False, default=0)
    lifetime_points = db.Column(db.Integer, nullable=False, default=0)
    tier_level = db.Column(db.Enum('bronze', 'silver', 'gold', 'platinum', name='loyalty_tiers'),
                          nullable=False, default='bronze')
    join_date = db.Column(db.DateTime, default=datetime.utcnow)
    last_activity = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    user = db.relationship('User', back_populates='loyalty_account', lazy='joined')

    def update_tier(self):
        """Update tier based on lifetime points"""
        if self.lifetime_points >= 10000:
            self.tier_level = 'platinum'
        elif self.lifetime_points >= 5000:
            self.tier_level = 'gold'
        elif self.lifetime_points >= 2000:
            self.tier_level = 'silver'
        else:
            self.tier_level = 'bronze'

    def calculate_loyalty_points(self, order_total):
        """Calculate loyalty points based on order total"""
        # Base rate: 1 point per EGP spent
        base_points = int(order_total)
        
        # Tier multipliers
        multiplier = 1.0
        if self.tier_level == 'silver':
            multiplier = 1.2
        elif self.tier_level == 'gold':
            multiplier = 1.5
        elif self.tier_level == 'platinum':
            multiplier = 2.0
            
        return int(base_points * multiplier)

    def add_points(self, points, order_id=None, description="Points earned"):
        """Add points to customer account and create transaction record"""
        self.total_points += points
        self.lifetime_points += points
        self.last_activity = datetime.utcnow()
        
        # Update tier if necessary
        self.update_tier()
        
        # Create transaction record
        from app.models import PointTransaction
        transaction = PointTransaction(
            user_id=self.user_id,
            order_id=order_id,
            points_earned=points,
            balance_after=self.total_points,
            transaction_type='earned',
            description=description
        )
        
        db.session.add(transaction)
        return transaction

    def __repr__(self):
        return f'<CustomerLoyalty {self.user_id}>'

class PointTransaction(db.Model):
    """Point earning and redemption history"""
    __tablename__ = 'point_transactions'

    transaction_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.order_id'), nullable=True)
    points_earned = db.Column(db.Integer, nullable=False, default=0)
    points_redeemed = db.Column(db.Integer, nullable=False, default=0)
    balance_after = db.Column(db.Integer, nullable=True)  # Points balance after transaction
    transaction_type = db.Column(db.Enum('earned', 'redeemed', 'expired', 'bonus', 'adjustment', name='transaction_types'),
                               nullable=False)
    description = db.Column(db.String(255), nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    expiry_date = db.Column(db.DateTime, nullable=True)
    
    @property
    def customer(self):
        """Get customer loyalty account for this transaction"""
        return CustomerLoyalty.query.filter_by(user_id=self.user_id).first()

    def __repr__(self):
        return f'<PointTransaction {self.transaction_id}>'

# Alias for backward compatibility with test scripts
LoyaltyTransaction = PointTransaction

class RewardItem(db.Model):
    """Available rewards for point redemption"""
    __tablename__ = 'reward_items'

    reward_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    points_required = db.Column(db.Integer, nullable=False)
    item_id = db.Column(db.Integer, db.ForeignKey('menu_items.item_id'), nullable=True)
    category = db.Column(db.String(50), nullable=True)
    status = db.Column(db.Enum('active', 'inactive', 'expired', name='reward_status'),
                      nullable=False, default='active')
    expiry_date = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    redemptions = db.relationship('RewardRedemption', backref='reward', lazy='dynamic')

    def __repr__(self):
        return f'<RewardItem {self.name}>'

class RewardRedemption(db.Model):
    """Track reward usage"""
    __tablename__ = 'reward_redemptions'

    redemption_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    reward_id = db.Column(db.Integer, db.ForeignKey('reward_items.reward_id'), nullable=False)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.order_id'), nullable=True)
    points_used = db.Column(db.Integer, nullable=False)
    redemption_date = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.Enum('pending', 'completed', 'cancelled', name='redemption_status'),
                      nullable=False, default='pending')
    redemption_code = db.Column(db.String(20), nullable=True, unique=True)

    def __repr__(self):
        return f'<RewardRedemption {self.redemption_id}>'

class PromotionalCampaign(db.Model):
    """Bonus point campaigns"""
    __tablename__ = 'promotional_campaigns'

    campaign_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    bonus_multiplier = db.Column(db.Float, nullable=False, default=1.0)
    start_date = db.Column(db.DateTime, nullable=False)
    end_date = db.Column(db.DateTime, nullable=False)
    conditions = db.Column(db.Text, nullable=True)
    status = db.Column(db.Enum('active', 'inactive', 'expired', name='campaign_status'),
                      nullable=False, default='active')

    # Enhanced campaign settings
    minimum_order_amount = db.Column(db.Float, nullable=True, default=0.0)
    maximum_uses_per_customer = db.Column(db.Integer, nullable=True)
    total_usage_limit = db.Column(db.Integer, nullable=True)
    target_customer_tier = db.Column(db.String(20), nullable=True)  # bronze, silver, gold, platinum, all
    applicable_days = db.Column(db.String(20), nullable=True)  # all, weekdays, weekends, specific
    specific_menu_categories = db.Column(db.Text, nullable=True)  # JSON string of category IDs
    discount_type = db.Column(db.String(20), nullable=True)  # Changed from Enum to String for SQLite compatibility
    discount_value = db.Column(db.Float, nullable=True)  # For percentage or fixed discounts

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def is_active(self):
        """Check if campaign is currently active"""
        now = datetime.utcnow()
        return (self.status == 'active' and
                self.start_date <= now <= self.end_date)

    def is_applicable_for_customer(self, customer):
        """Check if campaign is applicable for a specific customer"""
        if not self.is_active():
            return False

        # Check customer tier requirement
        if self.target_customer_tier and self.target_customer_tier != 'all':
            if not customer or customer.tier_level != self.target_customer_tier:
                return False

        return True

    def is_applicable_for_order(self, order_amount, customer=None):
        """Check if campaign is applicable for a specific order"""
        if not self.is_active():
            return False

        # Check minimum order amount
        if self.minimum_order_amount and order_amount < self.minimum_order_amount:
            return False

        # Check customer-specific requirements
        if customer and not self.is_applicable_for_customer(customer):
            return False

        return True

    def get_applicable_categories(self):
        """Get list of applicable category IDs"""
        if not self.specific_menu_categories:
            return None
        try:
            import json
            return json.loads(self.specific_menu_categories)
        except:
            return None

    def __repr__(self):
        return f'<PromotionalCampaign {self.name}>'

class QRCode(db.Model):
    """Table-based QR codes"""
    __tablename__ = 'qr_codes'

    qr_id = db.Column(db.Integer, primary_key=True)
    table_id = db.Column(db.Integer, db.ForeignKey('tables.table_id'), nullable=False)
    url = db.Column(db.String(255), nullable=False)
    qr_type = db.Column(db.Enum('menu', 'login', 'payment', 'whatsapp', name='qr_types'),
                       nullable=False, default='menu')
    is_active = db.Column(db.Boolean, default=True)
    qr_image_data = db.Column(db.Text, nullable=True)  # Base64 encoded QR code image
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_scanned = db.Column(db.DateTime, nullable=True)
    scan_count = db.Column(db.Integer, default=0)
    
    def get_qr_image_url(self):
        """Get data URL for QR code image"""
        if self.qr_image_data:
            return f"data:image/png;base64,{self.qr_image_data}"
        return None

    def __repr__(self):
        return f'<QRCode {self.qr_id}>'

class AuditLog(db.Model):
    """System activity tracking"""
    __tablename__ = 'audit_logs'

    log_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=True)
    action_type = db.Column(db.String(50), nullable=False)
    description = db.Column(db.Text, nullable=False)
    ip_address = db.Column(db.String(45), nullable=True)
    user_agent = db.Column(db.String(255), nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<AuditLog {self.log_id}>'

class CustomerPreferences(db.Model):
    """Customer notification and privacy preferences"""
    __tablename__ = 'customer_preferences'

    preference_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False, unique=True)
    
    # Notification preferences
    notify_order_updates = db.Column(db.Boolean, default=True)
    notify_loyalty_points = db.Column(db.Boolean, default=True)
    notify_promotions = db.Column(db.Boolean, default=True)
    notify_service_requests = db.Column(db.Boolean, default=True)
    
    # Privacy preferences
    profile_visible = db.Column(db.Boolean, default=False)
    order_history_private = db.Column(db.Boolean, default=True)
    analytics_enabled = db.Column(db.Boolean, default=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship back to user
    user = db.relationship('User', backref=db.backref('preferences', uselist=False))

    def __repr__(self):
        return f'<CustomerPreferences {self.user_id}>'

class TableSession(db.Model):
    """Track customer sessions at tables"""
    __tablename__ = 'table_sessions'
    
    session_id = db.Column(db.Integer, primary_key=True)
    table_id = db.Column(db.Integer, db.ForeignKey('tables.table_id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=True)  # Can be anonymous
    session_token = db.Column(db.String(255), unique=True, nullable=False)  # For anonymous sessions
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    ended_at = db.Column(db.DateTime, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    device_info = db.Column(db.Text, nullable=True)  # Browser/device info
    ip_address = db.Column(db.String(45), nullable=True)  # IPv4/IPv6
    # last_activity = db.Column(db.DateTime, default=datetime.utcnow)  # Track session activity - Temporarily disabled
    
    # Relationships
    table = db.relationship('Table', backref='sessions')
    user = db.relationship('User', backref='table_sessions')
    
    @classmethod
    def create_session(cls, table_id, user_id=None, device_info=None, ip_address=None):
        """Create a new table session"""
        import uuid
        session_token = str(uuid.uuid4())
        
        session = cls(
            table_id=table_id,
            user_id=user_id,
            session_token=session_token,
            device_info=device_info,
            ip_address=ip_address
        )
        
        db.session.add(session)
        db.session.commit()
        return session
    
    @classmethod
    def get_active_session(cls, table_id, user_id=None, session_token=None):
        """Get active session for table"""
        query = cls.query.filter(
            cls.table_id == table_id,
            cls.is_active == True
        )
        
        if user_id:
            query = query.filter(cls.user_id == user_id)
        elif session_token:
            query = query.filter(cls.session_token == session_token)
            
        return query.first()
    
    def end_session(self):
        """End the current session"""
        self.ended_at = datetime.utcnow()
        self.is_active = False
        db.session.commit()
    
    def __repr__(self):
        return f'<TableSession {self.session_id}>'

class SystemSettings(db.Model):
    """System-wide configuration settings"""
    __tablename__ = 'system_settings'
    
    setting_id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.Text, nullable=True)
    description = db.Column(db.Text, nullable=True)
    setting_type = db.Column(db.Enum('string', 'integer', 'boolean', 'float', name='setting_types'), 
                           nullable=False, default='string')
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    @classmethod
    def get_setting(cls, key, default=None):
        """Get a system setting value by key"""
        setting = cls.query.filter_by(key=key, is_active=True).first()
        if setting:
            # Convert based on type
            if setting.setting_type == 'integer':
                return int(setting.value) if setting.value else default
            elif setting.setting_type == 'boolean':
                return setting.value.lower() in ('true', '1', 'yes') if setting.value else default
            elif setting.setting_type == 'float':
                return float(setting.value) if setting.value else default
            else:
                return setting.value if setting.value else default
        return default
    
    @classmethod
    def set_setting(cls, key, value, description=None, setting_type='string'):
        """Set or update a system setting"""
        setting = cls.query.filter_by(key=key).first()
        if setting:
            setting.value = str(value)
            setting.updated_at = datetime.utcnow()
            if description:
                setting.description = description
            if setting_type:
                setting.setting_type = setting_type
        else:
            setting = cls(
                key=key,
                value=str(value),
                description=description,
                setting_type=setting_type
            )
            db.session.add(setting)
        
        db.session.commit()
        return setting
    
    @classmethod
    def get_currency(cls):
        """Get the system currency setting"""
        return cls.get_setting('currency', 'EGP')
    
    @classmethod
    def set_currency(cls, currency):
        """Set the system currency"""
        return cls.set_setting('currency', currency, 'System currency for price display', 'string')
    
    def __repr__(self):
        return f'<SystemSettings {self.key}={self.value}>'
