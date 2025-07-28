"""Document processing pipeline with OCR and compression"""
import os
import tempfile
import asyncio
import subprocess
from typing import Tuple, Optional, Dict, Any
from pathlib import Path
from datetime import datetime
import pytesseract
from PIL import Image, ImageOps
import pillow_heif
from wand.image import Image as WandImage
import magic
from flask import current_app
from app import db, logger
from app.auth.security import FileEncryption, generate_file_key
from app.audit.logger import log_document_event
from config.constraints import PI_ZERO_LIMITS


# Register HEIF opener with Pillow
pillow_heif.register_heif_opener()


class DocumentProcessor:
    """Main document processing pipeline optimized for Pi Zero"""
    
    # Supported formats
    SUPPORTED_FORMATS = {
        'image/jpeg', 'image/png', 'image/tiff', 'image/bmp',
        'image/webp', 'image/heif', 'image/heic',
        'application/pdf'
    }
    
    # OCR optimization settings
    OCR_DPI = 200  # Balanced quality/performance
    OCR_MAX_SIZE = (2000, 2000)  # Limit image size for OCR
    
    def __init__(self):
        self.temp_dir = Path(current_app.config['TEMP_FOLDER'])
        self.temp_dir.mkdir(exist_ok=True)
        
        # Configure Tesseract
        self.tesseract_config = current_app.config.get(
            'TESSERACT_CONFIG',
            '--psm 11 -l medical --oem 1'
        )
    
    async def process_upload(self, file_stream, filename: str, 
                           patient_id: int, user_id: int) -> Dict[str, Any]:
        """Main processing pipeline for uploaded documents"""
        temp_path = None
        processed_path = None
        
        try:
            # Step 1: Save temporary file
            temp_path = await self._save_temp_file(file_stream, filename)
            
            # Step 2: Validate file type
            mime_type = self._detect_mime_type(temp_path)
            if mime_type not in self.SUPPORTED_FORMATS:
                raise ValueError(f"Unsupported file type: {mime_type}")
            
            # Step 3: Process based on type
            if mime_type == 'application/pdf':
                processed_path = await self._process_pdf(temp_path)
            else:
                processed_path = await self._process_image(temp_path)
            
            # Step 4: Run OCR
            ocr_result = await self._run_ocr(processed_path)
            
            # Step 5: Encrypt files
            encrypted_data = await self._encrypt_document(
                processed_path, ocr_result, patient_id, user_id
            )
            
            # Step 6: Save to patient folder
            document_id = await self._save_to_storage(
                encrypted_data, patient_id, filename
            )
            
            # Log successful processing
            log_document_event('DOCUMENT_UPLOADED', user_id, {
                'document_id': document_id,
                'patient_id': patient_id,
                'filename': filename,
                'size': os.path.getsize(temp_path),
                'ocr_confidence': ocr_result.get('confidence', 0)
            })
            
            return {
                'success': True,
                'document_id': document_id,
                'ocr_text': ocr_result.get('text', ''),
                'confidence': ocr_result.get('confidence', 0)
            }
            
        except Exception as e:
            logger.error(f"Document processing failed: {str(e)}")
            log_document_event('PROCESSING_FAILED', user_id, {
                'error': str(e),
                'filename': filename
            })
            raise
            
        finally:
            # Cleanup temp files
            for path in [temp_path, processed_path]:
                if path and os.path.exists(path):
                    os.unlink(path)
    
    async def _save_temp_file(self, file_stream, filename: str) -> str:
        """Save uploaded file to temporary location"""
        temp_fd, temp_path = tempfile.mkstemp(
            suffix=Path(filename).suffix,
            dir=self.temp_dir
        )
        
        try:
            # Write in chunks to limit memory usage
            chunk_size = current_app.config['UPLOAD_CHUNK_SIZE']
            with os.fdopen(temp_fd, 'wb') as f:
                while True:
                    chunk = file_stream.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
            
            return temp_path
        except Exception:
            os.unlink(temp_path)
            raise
    
    def _detect_mime_type(self, file_path: str) -> str:
        """Detect file MIME type"""
        mime = magic.Magic(mime=True)
        return mime.from_file(file_path)
    
    async def _process_image(self, image_path: str) -> str:
        """Process and optimize image for OCR and storage"""
        output_path = f"{image_path}_processed.webp"
        
        try:
            # Open image
            with Image.open(image_path) as img:
                # Convert to RGB if necessary
                if img.mode not in ('RGB', 'L'):
                    img = img.convert('RGB')
                
                # Auto-orient based on EXIF
                img = ImageOps.exif_transpose(img)
                
                # Resize if too large (memory constraint)
                if img.width > self.OCR_MAX_SIZE[0] or img.height > self.OCR_MAX_SIZE[1]:
                    img.thumbnail(self.OCR_MAX_SIZE, Image.Resampling.LANCZOS)
                
                # Enhance for OCR
                img = self._enhance_for_ocr(img)
                
                # Save as WebP (lossless for text)
                img.save(output_path, 'WEBP', lossless=True, quality=95)
            
            return output_path
            
        except Exception as e:
            logger.error(f"Image processing failed: {str(e)}")
            raise
    
    def _enhance_for_ocr(self, img: Image.Image) -> Image.Image:
        """Enhance image for better OCR results"""
        from PIL import ImageEnhance, ImageFilter
        
        # Convert to grayscale for text
        if img.mode != 'L':
            img = img.convert('L')
        
        # Enhance contrast
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(1.5)
        
        # Sharpen
        img = img.filter(ImageFilter.SHARPEN)
        
        # Denoise
        img = img.filter(ImageFilter.MedianFilter(size=3))
        
        return img
    
    async def _process_pdf(self, pdf_path: str) -> str:
        """Convert PDF to image for OCR"""
        output_path = f"{pdf_path}_page1.png"
        
        try:
            # Use ImageMagick for PDF conversion (memory efficient)
            with WandImage(filename=f"{pdf_path}[0]", resolution=self.OCR_DPI) as img:
                img.format = 'png'
                img.save(filename=output_path)
            
            return output_path
            
        except Exception as e:
            logger.error(f"PDF processing failed: {str(e)}")
            raise
    
    async def _run_ocr(self, image_path: str) -> Dict[str, Any]:
        """Run Tesseract OCR with resource limits"""
        try:
            # Set resource limits for OCR process
            def run_tesseract():
                import resource
                limits = PI_ZERO_LIMITS.get_process_limits()
                for limit_type, limit_value in limits.items():
                    resource.setrlimit(limit_type, limit_value)
                
                # Run OCR
                data = pytesseract.image_to_data(
                    image_path,
                    config=self.tesseract_config,
                    output_type=pytesseract.Output.DICT
                )
                
                text = pytesseract.image_to_string(
                    image_path,
                    config=self.tesseract_config
                )
                
                # Calculate average confidence
                confidences = [int(conf) for conf in data['conf'] if int(conf) > 0]
                avg_confidence = sum(confidences) / len(confidences) if confidences else 0
                
                return {
                    'text': text,
                    'data': data,
                    'confidence': avg_confidence
                }
            
            # Run in thread pool with timeout
            loop = asyncio.get_event_loop()
            result = await asyncio.wait_for(
                loop.run_in_executor(None, run_tesseract),
                timeout=PI_ZERO_LIMITS.OCR_TIMEOUT
            )
            
            return result
            
        except asyncio.TimeoutError:
            logger.error("OCR timeout exceeded")
            return {'text': '', 'confidence': 0, 'error': 'timeout'}
        except Exception as e:
            logger.error(f"OCR failed: {str(e)}")
            return {'text': '', 'confidence': 0, 'error': str(e)}
    
    async def _encrypt_document(self, image_path: str, ocr_result: Dict[str, Any],
                               patient_id: int, user_id: int) -> Dict[str, Any]:
        """Encrypt document and OCR text"""
        from app.auth.models import User
        
        # Get user's file encryption key
        user = User.query.get(user_id)
        if not user.file_key:
            user.file_key = generate_file_key()
            db.session.commit()
        
        # Create encryptor
        encryptor = FileEncryption(user.file_key)
        
        # Encrypt image
        enc_image_path = f"{image_path}.enc"
        encrypted_image, nonce = encryptor.encrypt_file(image_path, enc_image_path)
        
        # Encrypt OCR text
        ocr_text = ocr_result.get('text', '').encode('utf-8')
        encrypted_text = encryptor.aesgcm.encrypt(nonce, ocr_text, None)
        
        return {
            'encrypted_image_path': encrypted_image,
            'encrypted_text': encrypted_text,
            'nonce': nonce,
            'ocr_confidence': ocr_result.get('confidence', 0)
        }
    
    async def _save_to_storage(self, encrypted_data: Dict[str, Any],
                             patient_id: int, filename: str) -> int:
        """Save encrypted document to patient folder"""
        from app.patient.models import PatientDocument
        
        # Create patient folder if not exists
        patient_folder = Path(current_app.config['PATIENT_DATA_FOLDER']) / str(patient_id)
        patient_folder.mkdir(parents=True, exist_ok=True)
        
        # Generate document ID
        doc = PatientDocument(
            patient_id=patient_id,
            original_filename=filename,
            ocr_confidence=encrypted_data['ocr_confidence']
        )
        db.session.add(doc)
        db.session.flush()  # Get ID
        
        # Move encrypted file to final location
        final_path = patient_folder / f"doc_{doc.id}.enc"
        os.rename(encrypted_data['encrypted_image_path'], final_path)
        
        # Save encrypted OCR text
        text_path = patient_folder / f"doc_{doc.id}_ocr.enc"
        with open(text_path, 'wb') as f:
            f.write(encrypted_data['nonce'])
            f.write(encrypted_data['encrypted_text'])
        
        # Update document record
        doc.file_path = str(final_path)
        doc.text_path = str(text_path)
        doc.file_size = os.path.getsize(final_path)
        doc.encryption_nonce = encrypted_data['nonce']
        
        db.session.commit()
        return doc.id