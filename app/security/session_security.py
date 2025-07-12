"""
Session Security Module
Provides security utilities for WhatsApp table sessions
"""

from flask import request, session, current_app
from datetime import datetime, timedelta
import hashlib
import hmac
import secrets
from typing import Optional, Dict, Any

class SessionSecurity:
    """Security utilities for session management"""
    
    @staticmethod
    def generate_secure_token() -> str:
        """Generate a cryptographically secure session token"""
        return secrets.token_urlsafe(32)
    
    @staticmethod
    def create_session_fingerprint(user_agent: str, ip_address: str) -> str:
        """Create a session fingerprint for security validation"""
        fingerprint_data = f"{user_agent}:{ip_address}"
        return hashlib.sha256(fingerprint_data.encode()).hexdigest()
    
    @staticmethod
    def validate_session_fingerprint(stored_fingerprint: str, current_user_agent: str, current_ip: str) -> bool:
        """Validate session fingerprint to detect hijacking"""
        current_fingerprint = SessionSecurity.create_session_fingerprint(current_user_agent, current_ip)
        return hmac.compare_digest(stored_fingerprint, current_fingerprint)
    
    @staticmethod
    def is_session_expired(started_at: datetime, max_age_hours: int = 4) -> bool:
        """Check if session has expired"""
        return datetime.utcnow() - started_at > timedelta(hours=max_age_hours)
    
    @staticmethod
    def get_session_remaining_time(started_at: datetime, max_age_hours: int = 4) -> timedelta:
        """Get remaining time for session"""
        elapsed = datetime.utcnow() - started_at
        max_age = timedelta(hours=max_age_hours)
        return max_age - elapsed if elapsed < max_age else timedelta(0)
    
    @staticmethod
    def validate_table_access(customer_id: int, table_id: int, session_token: str) -> Dict[str, Any]:
        """Comprehensive validation of table access"""
        from app.models import TableSession, User, Table
        
        # Find session
        table_session = TableSession.query.filter_by(
            session_token=session_token,
            is_active=True
        ).first()
        
        if not table_session:
            return {
                'valid': False,
                'error': 'Session not found',
                'error_code': 'SESSION_NOT_FOUND'
            }
        
        # Check expiration
        if SessionSecurity.is_session_expired(table_session.started_at):
            table_session.is_active = False
            from app.models import db
            db.session.commit()
            return {
                'valid': False,
                'error': 'Session expired',
                'error_code': 'SESSION_EXPIRED'
            }
        
        # Validate customer
        if table_session.user_id != customer_id:
            return {
                'valid': False,
                'error': 'Customer mismatch',
                'error_code': 'CUSTOMER_MISMATCH'
            }
        
        # Validate table
        if table_session.table_id != table_id:
            return {
                'valid': False,
                'error': 'Table mismatch',
                'error_code': 'TABLE_MISMATCH'
            }
        
        return {
            'valid': True,
            'session': table_session,
            'remaining_time': SessionSecurity.get_session_remaining_time(table_session.started_at)
        }
    
    @staticmethod
    def log_security_event(event_type: str, session_token: str, details: Dict[str, Any]):
        """Log security events for monitoring"""
        timestamp = datetime.utcnow().isoformat()
        ip_address = request.remote_addr if request else 'unknown'
        user_agent = request.headers.get('User-Agent', 'unknown') if request else 'unknown'
        
        log_entry = {
            'timestamp': timestamp,
            'event_type': event_type,
            'session_token': session_token[:8] + '...',  # Partial token for privacy
            'ip_address': ip_address,
            'user_agent': user_agent,
            'details': details
        }
        
        # In production, send to proper logging system
        current_app.logger.warning(f"Security Event: {log_entry}")
    
    @staticmethod
    def detect_suspicious_activity(session_token: str, current_ip: str, current_user_agent: str) -> Dict[str, Any]:
        """Detect suspicious session activity"""
        from app.models import TableSession
        
        table_session = TableSession.query.filter_by(
            session_token=session_token,
            is_active=True
        ).first()
        
        if not table_session:
            return {'suspicious': False}
        
        suspicious_indicators = []
        
        # Check for IP address changes
        if table_session.ip_address and table_session.ip_address != current_ip:
            suspicious_indicators.append({
                'type': 'IP_CHANGE',
                'old_value': table_session.ip_address,
                'new_value': current_ip
            })
        
        # Check for User-Agent changes
        if table_session.device_info and table_session.device_info != current_user_agent:
            suspicious_indicators.append({
                'type': 'USER_AGENT_CHANGE',
                'old_value': table_session.device_info[:50] + '...',
                'new_value': current_user_agent[:50] + '...'
            })
        
        # Check for rapid location changes (if implementing geolocation)
        # This would require additional geolocation data
        
        # Check for unusual access patterns
        # This would require session activity tracking
        
        if suspicious_indicators:
            SessionSecurity.log_security_event(
                'SUSPICIOUS_ACTIVITY',
                session_token,
                {'indicators': suspicious_indicators}
            )
        
        return {
            'suspicious': len(suspicious_indicators) > 0,
            'indicators': suspicious_indicators,
            'risk_level': 'HIGH' if len(suspicious_indicators) > 1 else 'MEDIUM' if suspicious_indicators else 'LOW'
        }

class SecurityMiddleware:
    """Middleware for session security"""
    
    @staticmethod
    def before_request():
        """Run security checks before each request"""
        # Skip security checks for static files and API health checks
        if request.endpoint in ['static', 'api.health']:
            return
        
        # Check for WhatsApp session
        whatsapp_session_token = session.get('whatsapp_session_token')
        if whatsapp_session_token:
            # Detect suspicious activity
            current_ip = request.remote_addr
            current_user_agent = request.headers.get('User-Agent', '')
            
            activity_check = SessionSecurity.detect_suspicious_activity(
                whatsapp_session_token,
                current_ip,
                current_user_agent
            )
            
            if activity_check['suspicious'] and activity_check['risk_level'] == 'HIGH':
                # High risk - terminate session
                session.clear()
                SessionSecurity.log_security_event(
                    'SESSION_TERMINATED',
                    whatsapp_session_token,
                    {'reason': 'High risk activity detected'}
                )
    
    @staticmethod
    def after_request(response):
        """Run security checks after each request"""
        # Add security headers
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        
        # Add session security headers for WhatsApp sessions
        if session.get('whatsapp_session_token'):
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
        
        return response

def init_security_middleware(app):
    """Initialize security middleware with Flask app"""
    app.before_request(SecurityMiddleware.before_request)
    app.after_request(SecurityMiddleware.after_request)
