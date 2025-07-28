"""Patient data models with PHI protection"""
from datetime import datetime
from typing import Optional, List
from sqlalchemy import Index, func
from sqlalchemy.ext.hybrid import hybrid_property
from app import db


class Patient(db.Model):
    """Patient model with HIPAA-compliant data storage"""
    __tablename__ = 'patients'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Demographics (encrypted at rest via SQLCipher)
    mrn = db.Column(db.String(20), unique=True, nullable=False)  # Medical Record Number
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    middle_name = db.Column(db.String(100))
    date_of_birth = db.Column(db.Date, nullable=False)
    ssn_encrypted = db.Column(db.LargeBinary)  # Extra encryption for SSN
    
    # Contact information
    phone = db.Column(db.String(20))
    email = db.Column(db.String(120))
    address_line1 = db.Column(db.String(200))
    address_line2 = db.Column(db.String(200))
    city = db.Column(db.String(100))
    state = db.Column(db.String(2))
    zip_code = db.Column(db.String(10))
    
    # Emergency contact
    emergency_contact_name = db.Column(db.String(200))
    emergency_contact_phone = db.Column(db.String(20))
    emergency_contact_relationship = db.Column(db.String(50))
    
    # Medical information
    blood_type = db.Column(db.String(5))
    allergies = db.Column(db.Text)
    medications = db.Column(db.Text)
    medical_history = db.Column(db.Text)
    
    # Psychiatric specific
    primary_diagnosis = db.Column(db.String(200))
    admission_date = db.Column(db.Date)
    discharge_date = db.Column(db.Date)
    treating_physician = db.Column(db.String(200))
    ward = db.Column(db.String(50))
    
    # Metadata
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    is_active = db.Column(db.Boolean, default=True)
    
    # Relationships
    documents = db.relationship('PatientDocument', backref='patient', 
                              cascade='all, delete-orphan')
    access_logs = db.relationship('PatientAccessLog', backref='patient',
                                cascade='all, delete-orphan')
    
    # Indexes for search performance
    __table_args__ = (
        Index('idx_patient_name', 'last_name', 'first_name'),
        Index('idx_patient_mrn', 'mrn'),
        Index('idx_patient_dob', 'date_of_birth'),
    )
    
    @hybrid_property
    def full_name(self) -> str:
        """Get patient full name"""
        parts = [self.first_name, self.middle_name, self.last_name]
        return ' '.join(filter(None, parts))
    
    @hybrid_property
    def age(self) -> int:
        """Calculate patient age"""
        from datetime import date
        today = date.today()
        return today.year - self.date_of_birth.year - (
            (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day)
        )
    
    def redacted_ssn(self) -> str:
        """Return redacted SSN for display"""
        return "XXX-XX-XXXX"
    
    def to_dict(self, include_phi: bool = False) -> dict:
        """Convert to dictionary with PHI control"""
        data = {
            'id': self.id,
            'mrn': self.mrn if include_phi else 'REDACTED',
            'full_name': self.full_name if include_phi else 'REDACTED',
            'age': self.age,
            'ward': self.ward,
            'treating_physician': self.treating_physician,
            'is_active': self.is_active
        }
        
        if include_phi:
            data.update({
                'first_name': self.first_name,
                'last_name': self.last_name,
                'date_of_birth': self.date_of_birth.isoformat() if self.date_of_birth else None,
                'phone': self.phone,
                'address': {
                    'line1': self.address_line1,
                    'line2': self.address_line2,
                    'city': self.city,
                    'state': self.state,
                    'zip': self.zip_code
                }
            })
        
        return data


class PatientDocument(db.Model):
    """Patient document records"""
    __tablename__ = 'patient_documents'
    
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    
    # Document metadata
    document_type = db.Column(db.String(50))  # lab_result, admission_note, etc.
    original_filename = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)  # Encrypted file location
    text_path = db.Column(db.String(500))  # Encrypted OCR text location
    file_size = db.Column(db.Integer)  # Bytes
    
    # Encryption metadata
    encryption_nonce = db.Column(db.LargeBinary(12))  # GCM nonce
    
    # OCR metadata
    ocr_confidence = db.Column(db.Float)
    ocr_processed = db.Column(db.Boolean, default=False)
    ocr_language = db.Column(db.String(10), default='en')
    
    # Clinical metadata
    document_date = db.Column(db.Date)
    author = db.Column(db.String(200))
    department = db.Column(db.String(100))
    
    # Audit fields
    uploaded_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_accessed = db.Column(db.DateTime)
    access_count = db.Column(db.Integer, default=0)
    
    # Archive status
    archived = db.Column(db.Boolean, default=False)
    archived_date = db.Column(db.DateTime)
    
    # Full-text search
    search_text = db.Column(db.Text)  # Indexed OCR text (sanitized)
    
    # Indexes
    __table_args__ = (
        Index('idx_document_patient', 'patient_id'),
        Index('idx_document_type', 'document_type'),
        Index('idx_document_date', 'document_date'),
        Index('idx_document_search', 'search_text'),  # Full-text search
    )
    
    def increment_access(self):
        """Track document access"""
        self.access_count += 1
        self.last_accessed = datetime.utcnow()
        db.session.commit()


class PatientAccessLog(db.Model):
    """HIPAA-required access logging"""
    __tablename__ = 'patient_access_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # Access details
    access_type = db.Column(db.String(50), nullable=False)  # view, edit, print, export
    accessed_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.String(200))
    
    # What was accessed
    fields_accessed = db.Column(db.JSON)  # List of fields viewed/modified
    document_id = db.Column(db.Integer, db.ForeignKey('patient_documents.id'))
    
    # Emergency access
    is_emergency = db.Column(db.Boolean, default=False)
    emergency_reason = db.Column(db.Text)
    
    # Relationships
    user = db.relationship('User', backref='patient_accesses')
    document = db.relationship('PatientDocument', backref='access_logs')
    
    # Indexes
    __table_args__ = (
        Index('idx_access_patient', 'patient_id'),
        Index('idx_access_user', 'user_id'),
        Index('idx_access_time', 'accessed_at'),
    )