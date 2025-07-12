import qrcode
import io
import base64
from flask import url_for, current_app
from app.models import QRCode, Table
from app.extensions import db
import os
import logging

logger = logging.getLogger(__name__)

class QRCodeService:
    """Service for generating and managing QR codes"""
    
    def __init__(self):
        self.qr_dir = os.path.join(current_app.static_folder, 'qr_codes')
        self.ensure_qr_directory()
    
    def ensure_qr_directory(self):
        """Ensure QR codes directory exists"""
        if not os.path.exists(self.qr_dir):
            os.makedirs(self.qr_dir)
    
    def generate_table_qr_code(self, table_id, qr_type='menu'):
        """Generate QR code for a table"""
        try:
            table = Table.query.get(table_id)
            if not table:
                return {'success': False, 'message': 'Table not found'}

            # Generate URL based on QR type
            if qr_type == 'menu':
                url = url_for('customer.menu', table_id=table_id, _external=True)
            elif qr_type == 'login':
                url = url_for('auth.login', table_id=table_id, _external=True)
            elif qr_type == 'payment':
                url = url_for('payment.checkout', table_id=table_id, _external=True)
            elif qr_type == 'whatsapp':
                # Generate WhatsApp URL with table information
                from flask import current_app, request

                # Try to get WhatsApp number from request (QR settings) or config
                whatsapp_number = None
                message_template = None

                if request and hasattr(request, '_whatsapp_settings'):
                    # Settings passed from admin route
                    whatsapp_number = request._whatsapp_settings.get('whatsapp_number')
                    message_template = request._whatsapp_settings.get('message_template')
                elif request and request.is_json:
                    # Settings from direct JSON request
                    data = request.get_json()
                    whatsapp_number = data.get('whatsapp_number') if data else None
                    message_template = data.get('whatsapp_message') if data else None

                if not whatsapp_number:
                    whatsapp_number = current_app.config.get('WHATSAPP_BOT_NUMBER', '201234567890')

                if not message_template:
                    message_template = "Hello! I'm at table {table_number} and would like to place an order."

                # Remove any non-numeric characters except +
                import re
                whatsapp_number = re.sub(r'[^\d+]', '', whatsapp_number)
                if not whatsapp_number.startswith('+'):
                    whatsapp_number = '+' + whatsapp_number.lstrip('+')

                # Create message with table number and unique code for security
                import uuid
                unique_code = str(uuid.uuid4())[:8].upper()

                # Get table info for message
                table = Table.query.get(table_id)
                table_number = table.table_number if table else str(table_id)

                # Create message using template
                message = message_template.replace('{table_number}', str(table_number))
                message += f" (Code: {unique_code})"

                # URL encode the message
                import urllib.parse
                encoded_message = urllib.parse.quote(message)
                url = f"https://wa.me/{whatsapp_number.lstrip('+')}?text={encoded_message}"
            else:
                url = url_for('main.index', table_id=table_id, _external=True)
            
            # Generate QR code
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(url)
            qr.make(fit=True)
            
            # Create QR image
            img = qr.make_image(fill_color="black", back_color="white")

            # Save as file
            filename = f"table_{table_id}_{qr_type}.png"
            filepath = os.path.join(self.qr_dir, filename)
            img.save(filepath)

            # Convert to base64 for database storage
            buffer = io.BytesIO()
            img.save(buffer, format='PNG')
            img_str = base64.b64encode(buffer.getvalue()).decode()

            # Save to database
            existing_qr = QRCode.query.filter_by(
                table_id=table_id,
                qr_type=qr_type
            ).first()

            if existing_qr:
                existing_qr.url = url
                existing_qr.is_active = True
                existing_qr.qr_image_data = img_str
            else:
                qr_code = QRCode(
                    table_id=table_id,
                    url=url,
                    qr_type=qr_type,
                    is_active=True,
                    qr_image_data=img_str
                )
                db.session.add(qr_code)
            
            db.session.commit()
            
            return {
                'success': True,
                'filename': filename,
                'url': url,
                'file_path': url_for('static', filename=f'qr_codes/{filename}')
            }
            
        except Exception as e:
            logger.error(f"Error generating QR code: {str(e)}")
            db.session.rollback()
            return {'success': False, 'message': str(e)}
    
    def generate_qr_as_base64(self, table_id, qr_type='menu'):
        """Generate QR code as base64 for inline display"""
        try:
            table = Table.query.get(table_id)
            if not table:
                return {'success': False, 'message': 'Table not found'}
            
            # Generate URL
            if qr_type == 'menu':
                url = url_for('customer.menu', table_id=table_id, _external=True)
            elif qr_type == 'login':
                url = url_for('auth.login', table_id=table_id, _external=True)
            elif qr_type == 'payment':
                url = url_for('payment.checkout', table_id=table_id, _external=True)
            elif qr_type == 'whatsapp':
                # Generate WhatsApp URL with table information
                from flask import current_app, request

                # Try to get WhatsApp number from request (QR settings) or config
                whatsapp_number = None
                message_template = None

                if request and hasattr(request, '_whatsapp_settings'):
                    # Settings passed from admin route
                    whatsapp_number = request._whatsapp_settings.get('whatsapp_number')
                    message_template = request._whatsapp_settings.get('message_template')
                elif request and request.is_json:
                    # Settings from direct JSON request
                    data = request.get_json()
                    whatsapp_number = data.get('whatsapp_number') if data else None
                    message_template = data.get('whatsapp_message') if data else None

                if not whatsapp_number:
                    whatsapp_number = current_app.config.get('WHATSAPP_BOT_NUMBER', '201234567890')

                if not message_template:
                    message_template = "Hello! I'm at table {table_number} and would like to place an order."

                # Remove any non-numeric characters except +
                import re
                whatsapp_number = re.sub(r'[^\d+]', '', whatsapp_number)
                if not whatsapp_number.startswith('+'):
                    whatsapp_number = '+' + whatsapp_number.lstrip('+')

                # Create message with table number and unique code for security
                import uuid
                unique_code = str(uuid.uuid4())[:8].upper()

                # Get table info for message
                table = Table.query.get(table_id)
                table_number = table.table_number if table else str(table_id)

                # Create message using template
                message = message_template.replace('{table_number}', str(table_number))
                message += f" (Code: {unique_code})"

                # URL encode the message
                import urllib.parse
                encoded_message = urllib.parse.quote(message)
                url = f"https://wa.me/{whatsapp_number.lstrip('+')}?text={encoded_message}"
            else:
                url = url_for('main.index', table_id=table_id, _external=True)
            
            # Generate QR code
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(url)
            qr.make(fit=True)
            
            # Create image in memory
            img = qr.make_image(fill_color="black", back_color="white")
            
            # Convert to base64
            buffer = io.BytesIO()
            img.save(buffer, format='PNG')
            img_str = base64.b64encode(buffer.getvalue()).decode()

            # Save to database
            existing_qr = QRCode.query.filter_by(
                table_id=table_id,
                qr_type=qr_type
            ).first()

            if existing_qr:
                existing_qr.url = url
                existing_qr.is_active = True
                existing_qr.qr_image_data = img_str
            else:
                qr_code = QRCode(
                    table_id=table_id,
                    url=url,
                    qr_type=qr_type,
                    is_active=True,
                    qr_image_data=img_str
                )
                db.session.add(qr_code)

            db.session.commit()

            return {
                'success': True,
                'base64': f"data:image/png;base64,{img_str}",
                'url': url
            }
            
        except Exception as e:
            logger.error(f"Error generating QR code as base64: {str(e)}")
            return {'success': False, 'message': str(e)}
    
    def generate_bulk_qr_codes(self, table_ids, qr_type='menu'):
        """Generate QR codes for multiple tables"""
        results = []
        
        for table_id in table_ids:
            result = self.generate_table_qr_code(table_id, qr_type)
            results.append({
                'table_id': table_id,
                'result': result
            })
        
        return results
    
    def get_table_qr_codes(self, table_id):
        """Get all QR codes for a table"""
        qr_codes = QRCode.query.filter_by(table_id=table_id, is_active=True).all()
        return [
            {
                'qr_id': qr.qr_id,
                'qr_type': qr.qr_type,
                'url': qr.url,
                'scan_count': qr.scan_count,
                'last_scanned': qr.last_scanned.isoformat() if qr.last_scanned else None,
                'created_at': qr.created_at.isoformat(),
                'file_path': url_for('static', filename=f'qr_codes/table_{table_id}_{qr.qr_type}.png')
            }
            for qr in qr_codes
        ]
    
    def track_qr_scan(self, table_id, qr_type='menu'):
        """Track QR code scan"""
        try:
            qr_code = QRCode.query.filter_by(
                table_id=table_id,
                qr_type=qr_type,
                is_active=True
            ).first()
            
            if qr_code:
                qr_code.scan_count += 1
                qr_code.last_scanned = db.func.now()
                db.session.commit()
                
                return {'success': True, 'scan_count': qr_code.scan_count}
            else:
                return {'success': False, 'message': 'QR code not found'}
                
        except Exception as e:
            logger.error(f"Error tracking QR scan: {str(e)}")
            db.session.rollback()
            return {'success': False, 'message': str(e)}
    
    def deactivate_qr_code(self, qr_id):
        """Deactivate a QR code"""
        try:
            qr_code = QRCode.query.get(qr_id)
            if not qr_code:
                return {'success': False, 'message': 'QR code not found'}
            
            qr_code.is_active = False
            db.session.commit()
            
            return {'success': True, 'message': 'QR code deactivated'}
            
        except Exception as e:
            logger.error(f"Error deactivating QR code: {str(e)}")
            db.session.rollback()
            return {'success': False, 'message': str(e)}
    
    def get_qr_analytics(self):
        """Get QR code usage analytics"""
        try:
            total_qr_codes = QRCode.query.filter_by(is_active=True).count()
            total_scans = db.session.query(db.func.sum(QRCode.scan_count)).scalar() or 0
            
            # Most scanned QR codes
            most_scanned = db.session.query(QRCode, Table).join(Table).order_by(
                QRCode.scan_count.desc()
            ).limit(10).all()
            
            # Recent scans
            recent_scans = QRCode.query.filter(
                QRCode.last_scanned.isnot(None)
            ).order_by(QRCode.last_scanned.desc()).limit(10).all()
            
            return {
                'success': True,
                'total_qr_codes': total_qr_codes,
                'total_scans': total_scans,
                'most_scanned': [
                    {
                        'table_id': qr.table_id,
                        'table_number': table.table_number if table else f"Table {qr.table_id}",
                        'qr_type': qr.qr_type,
                        'scan_count': qr.scan_count,
                        'last_scanned': qr.last_scanned.isoformat() if qr.last_scanned else None
                    }
                    for qr, table in most_scanned
                ],
                'recent_scans': [
                    {
                        'table_id': qr.table_id,
                        'qr_type': qr.qr_type,
                        'scan_count': qr.scan_count,
                        'last_scanned': qr.last_scanned.isoformat() if qr.last_scanned else None
                    }
                    for qr in recent_scans
                ]
            }
            
        except Exception as e:
            logger.error(f"Error getting QR analytics: {str(e)}")
            return {'success': False, 'message': str(e)}
    
    def regenerate_all_qr_codes(self):
        """Regenerate all QR codes (useful after URL changes)"""
        try:
            tables = Table.query.all()
            qr_types = ['menu', 'login', 'payment']
            
            results = []
            for table in tables:
                for qr_type in qr_types:
                    result = self.generate_table_qr_code(table.table_id, qr_type)
                    results.append({
                        'table_id': table.table_id,
                        'qr_type': qr_type,
                        'result': result
                    })
            
            return {
                'success': True,
                'message': f'Regenerated QR codes for {len(tables)} tables',
                'results': results
            }
            
        except Exception as e:
            logger.error(f"Error regenerating QR codes: {str(e)}")
            return {'success': False, 'message': str(e)}
    
    def create_custom_qr_code(self, data, filename=None):
        """Create a custom QR code with arbitrary data"""
        try:
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(data)
            qr.make(fit=True)
            
            img = qr.make_image(fill_color="black", back_color="white")
            
            if filename:
                filepath = os.path.join(self.qr_dir, filename)
                img.save(filepath)
                return {
                    'success': True,
                    'filename': filename,
                    'file_path': url_for('static', filename=f'qr_codes/{filename}')
                }
            else:
                # Return as base64
                buffer = io.BytesIO()
                img.save(buffer, format='PNG')
                img_str = base64.b64encode(buffer.getvalue()).decode()
                
                return {
                    'success': True,
                    'base64': f"data:image/png;base64,{img_str}"
                }
                
        except Exception as e:
            logger.error(f"Error creating custom QR code: {str(e)}")
            return {'success': False, 'message': str(e)}
