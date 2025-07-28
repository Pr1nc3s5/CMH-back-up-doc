#!/usr/bin/env python3
"""
Batch import tool for migrating paper records to PSYWARD DMS
"""
import os
import sys
import asyncio
from pathlib import Path
import argparse
from datetime import datetime
import csv

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db
from app.documents.processing import DocumentProcessor
from app.patient.models import Patient

async def import_batch(scan_dir: Path, mapping_file: Path):
    """Import scanned documents based on CSV mapping"""
    app = create_app('production')
    
    with app.app_context():
        processor = DocumentProcessor()
        
        # Read mapping file
        # Format: filename,patient_mrn,document_type,document_date
        with open(mapping_file, 'r') as f:
            reader = csv.DictReader(f)
            
            for row in reader:
                filename = row['filename']
                mrn = row['patient_mrn']
                doc_type = row.get('document_type', 'scan')
                doc_date = row.get('document_date')
                
                file_path = scan_dir / filename
                if not file_path.exists():
                    print(f"File not found: {filename}")
                    continue
                
                # Find patient
                patient = Patient.query.filter_by(mrn=mrn).first()
                if not patient:
                    print(f"Patient not found: MRN {mrn}")
                    continue
                
                print(f"Importing {filename} for patient {patient.full_name}...")
                
                try:
                    # Process document
                    with open(file_path, 'rb') as f:
                        result = await processor.process_upload(
                            f,
                            filename,
                            patient.id,
                            1  # Admin user ID
                        )
                    
                    # Update metadata
                    if doc_type or doc_date:
                        from app.patient.models import PatientDocument
                        doc = PatientDocument.query.get(result['document_id'])
                        if doc_type:
                            doc.document_type = doc_type
                        if doc_date:
                            doc.document_date = datetime.strptime(doc_date, '%Y-%m-%d').date()
                        db.session.commit()
                    
                    print(f"✓ Imported successfully (OCR confidence: {result['confidence']}%)")
                    
                except Exception as e:
                    print(f"✗ Failed to import: {str(e)}")

def main():
    parser = argparse.ArgumentParser(description='Import paper records to PSYWARD DMS')
    parser.add_argument('scan_dir', help='Directory containing scanned documents')
    parser.add_argument('mapping_file', help='CSV file mapping documents to patients')
    
    args = parser.parse_args()
    
    scan_dir = Path(args.scan_dir)
    mapping_file = Path(args.mapping_file)
    
    if not scan_dir.exists():
        print(f"Error: Scan directory not found: {scan_dir}")
        sys.exit(1)
    
    if not mapping_file.exists():
        print(f"Error: Mapping file not found: {mapping_file}")
        sys.exit(1)
    
    # Run import
    asyncio.run(import_batch(scan_dir, mapping_file))

if __name__ == '__main__':
    main()