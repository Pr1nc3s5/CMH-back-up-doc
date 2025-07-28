"""Patient and document search functionality"""
import re
from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy import or_, and_, func
from app import db
from app.patient.models import Patient, PatientDocument
from app.audit.logger import log_search_event


class PatientSearchEngine:
    """Search engine for patients and documents"""
    
    # PHI patterns to detect and redact
    PHI_PATTERNS = {
        'ssn': re.compile(r'\b\d{3}-?\d{2}-?\d{4}\b'),
        'mrn': re.compile(r'\b[A-Z0-9]{6,10}\b'),
        'phone': re.compile(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b'),
        'email': re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')
    }
    
    @classmethod
    def search_patients(cls, query: str, user_id: int, 
                       include_inactive: bool = False) -> List[Patient]:
        """Search patients by name, MRN, or other identifiers"""
        # Sanitize query
        query = cls._sanitize_query(query)
        
        # Log search
        log_search_event('PATIENT_SEARCH', user_id, {'query': query})
        
        # Build search conditions
        conditions = []
        
        # Search by name
        name_condition = or_(
            func.lower(Patient.first_name).contains(query.lower()),
            func.lower(Patient.last_name).contains(query.lower()),
            func.lower(func.concat(Patient.first_name, ' ', Patient.last_name)).contains(query.lower())
        )
        conditions.append(name_condition)
        
        # Search by MRN (exact match only for security)
        if re.match(r'^[A-Z0-9]+$', query.upper()):
            conditions.append(Patient.mrn == query.upper())
        
        # Active status filter
        if not include_inactive:
            base_condition = and_(Patient.is_active == True, or_(*conditions))
        else:
            base_condition = or_(*conditions)
        
        # Execute search
        results = Patient.query.filter(base_condition).limit(50).all()
        
        return results
    
    @classmethod
    def search_documents(cls, query: str, patient_id: Optional[int], 
                        user_id: int) -> List[PatientDocument]:
        """Search documents by OCR content"""
        # Sanitize and prepare query
        query = cls._sanitize_query(query)
        
        # Log search
        log_search_event('DOCUMENT_SEARCH', user_id, {
            'query': query,
            'patient_id': patient_id
        })
        
        # Build base query
        base_query = PatientDocument.query.filter(
            PatientDocument.archived == False
        )
        
        # Filter by patient if specified
        if patient_id:
            base_query = base_query.filter(
                PatientDocument.patient_id == patient_id
            )
        
        # Search in OCR text (using indexed search_text field)
        if query:
            # Use PostgreSQL-style full text search on SQLite
            search_condition = func.lower(PatientDocument.search_text).contains(
                query.lower()
            )
            base_query = base_query.filter(search_condition)
        
        # Order by relevance (simple implementation)
        results = base_query.order_by(
            PatientDocument.document_date.desc()
        ).limit(100).all()
        
        return results
    
    @classmethod
    def fuzzy_search(cls, query: str, threshold: float = 0.8) -> List[Dict[str, Any]]:
        """Fuzzy search across patients and documents"""
        # This would use a more sophisticated search library in production
        # For Pi Zero, we keep it simple
        results = []
        
        # Search patients
        patients = cls.search_patients(query, user_id=1, include_inactive=True)
        for patient in patients[:10]:
            results.append({
                'type': 'patient',
                'id': patient.id,
                'title': patient.full_name,
                'subtitle': f"MRN: {patient.mrn}",
                'score': cls._calculate_relevance(query, patient.full_name)
            })
        
        # Search recent documents
        documents = cls.search_documents(query, None, user_id=1)
        for doc in documents[:10]:
            results.append({
                'type': 'document',
                'id': doc.id,
                'title': doc.original_filename,
                'subtitle': f"Patient: {doc.patient.full_name}",
                'score': 0.5  # Lower score for document matches
            })
        
        # Sort by relevance score
        results.sort(key=lambda x: x['score'], reverse=True)
        
        return results
    
    @staticmethod
    def _sanitize_query(query: str) -> str:
        """Sanitize search query to prevent injection"""
        # Remove special characters that could break search
        sanitized = re.sub(r'[^\w\s\-.]', '', query)
        # Limit length
        return sanitized[:100]
    
    @staticmethod
    def _calculate_relevance(query: str, text: str) -> float:
        """Simple relevance scoring"""
        query_lower = query.lower()
        text_lower = text.lower()
        
        # Exact match
        if query_lower == text_lower:
            return 1.0
        
        # Starts with query
        if text_lower.startswith(query_lower):
            return 0.9
        
        # Contains query
        if query_lower in text_lower:
            return 0.7
        
        # Word match
        query_words = set(query_lower.split())
        text_words = set(text_lower.split())
        if query_words.intersection(text_words):
            return 0.5
        
        return 0.0


class MedicalOCRIndexer:
    """Index OCR text for searchability with medical term optimization"""
    
    # Common medical abbreviations to expand
    MEDICAL_ABBREVIATIONS = {
        'pt': 'patient',
        'hx': 'history',
        'dx': 'diagnosis',
        'rx': 'prescription',
        'tx': 'treatment',
        'sx': 'symptoms',
        'bp': 'blood pressure',
        'hr': 'heart rate',
        'prn': 'as needed',
        'qd': 'daily',
        'bid': 'twice daily',
        'tid': 'three times daily',
        'qid': 'four times daily'
    }
    
    @classmethod
    def index_document_text(cls, document_id: int, ocr_text: str) -> str:
        """Process and index OCR text for search"""
        # Clean and normalize text
        processed_text = cls._normalize_text(ocr_text)
        
        # Expand medical abbreviations
        processed_text = cls._expand_abbreviations(processed_text)
        
        # Remove PHI before indexing
        processed_text = cls._remove_phi(processed_text)
        
        # Update document search field
        doc = PatientDocument.query.get(document_id)
        if doc:
            doc.search_text = processed_text
            doc.ocr_processed = True
            db.session.commit()
        
        return processed_text
    
    @classmethod
    def _normalize_text(cls, text: str) -> str:
        """Normalize text for consistent search"""
        # Convert to lowercase
        text = text.lower()
        
        # Replace multiple spaces with single space
        text = re.sub(r'\s+', ' ', text)
        
        # Remove special characters but keep medical notation
        text = re.sub(r'[^\w\s\-\.\/\#]', ' ', text)
        
        return text.strip()
    
    @classmethod
    def _expand_abbreviations(cls, text: str) -> str:
        """Expand common medical abbreviations"""
        words = text.split()
        expanded_words = []
        
        for word in words:
            # Check if word is an abbreviation
            if word in cls.MEDICAL_ABBREVIATIONS:
                expanded_words.append(cls.MEDICAL_ABBREVIATIONS[word])
                expanded_words.append(word)  # Keep original too
            else:
                expanded_words.append(word)
        
        return ' '.join(expanded_words)
    
    @classmethod
    def _remove_phi(cls, text: str) -> str:
        """Remove PHI from text before indexing"""
        # Remove SSNs
        text = re.sub(r'\b\d{3}-?\d{2}-?\d{4}\b', '[SSN]', text)
        
        # Remove phone numbers
        text = re.sub(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b', '[PHONE]', text)
        
        # Remove email addresses
        text = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '[EMAIL]', text)
        
        # Remove dates (but keep years)
        text = re.sub(r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b', '[DATE]', text)
        
        # Remove potential MRNs (6-10 digit numbers)
        text = re.sub(r'\b\d{6,10}\b', '[MRN]', text)
        
        return text