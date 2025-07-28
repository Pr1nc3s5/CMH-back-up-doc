"""Image compression utilities optimized for medical documents"""
from PIL import Image
import subprocess
from pathlib import Path
from typing import Tuple, Optional
import tempfile


class MedicalImageCompressor:
    """Compress medical images while preserving text quality"""
    
    # Compression settings for different content types
    TEXT_HEAVY_SETTINGS = {
        'webp': {'lossless': True, 'quality': 95},
        'jpeg2000': {'quality_mode': 'rates', 'quality_layers': [40]}
    }
    
    PHOTO_SETTINGS = {
        'webp': {'lossless': False, 'quality': 85},
        'jpeg2000': {'quality_mode': 'rates', 'quality_layers': [25]}
    }
    
    @classmethod
    def compress_for_storage(cls, image_path: str, 
                           is_text_heavy: bool = True) -> Tuple[str, float]:
        """Compress image for long-term storage"""
        settings = cls.TEXT_HEAVY_SETTINGS if is_text_heavy else cls.PHOTO_SETTINGS
        
        # Try WebP first (better browser support)
        webp_path = cls._compress_to_webp(image_path, settings['webp'])
        webp_size = Path(webp_path).stat().st_size
        
        # Try JPEG2000 for better compression
        jp2_path = cls._compress_to_jpeg2000(image_path, settings['jpeg2000'])
        jp2_size = Path(jp2_path).stat().st_size if jp2_path else float('inf')
        
        # Choose smaller file
        if jp2_size < webp_size:
            Path(webp_path).unlink()
            compression_ratio = jp2_size / Path(image_path).stat().st_size
            return jp2_path, compression_ratio
        else:
            if jp2_path:
                Path(jp2_path).unlink()
            compression_ratio = webp_size / Path(image_path).stat().st_size
            return webp_path, compression_ratio
    
    @staticmethod
    def _compress_to_webp(image_path: str, settings: dict) -> str:
        """Compress to WebP format"""
        output_path = f"{image_path}.webp"
        
        with Image.open(image_path) as img:
            img.save(output_path, 'WEBP', **settings)
        
        return output_path
    
    @staticmethod
    def _compress_to_jpeg2000(image_path: str, settings: dict) -> Optional[str]:
        """Compress to JPEG2000 using OpenJPEG"""
        try:
            output_path = f"{image_path}.jp2"
            
            # Convert to temporary PPM for OpenJPEG
            with tempfile.NamedTemporaryFile(suffix='.ppm', delete=False) as tmp:
                with Image.open(image_path) as img:
                    img.save(tmp.name, 'PPM')
                
                # Use opj_compress for JPEG2000
                cmd = [
                    'opj_compress',
                    '-i', tmp.name,
                    '-o', output_path,
                    '-r', ','.join(map(str, settings['quality_layers']))
                ]
                
                subprocess.run(cmd, check=True, capture_output=True)
                Path(tmp.name).unlink()
            
            return output_path
            
        except (subprocess.CalledProcessError, FileNotFoundError):
            # OpenJPEG not available
            return None
    
    @staticmethod
    def is_text_heavy(image_path: str) -> bool:
        """Detect if image is primarily text"""
        with Image.open(image_path) as img:
            # Convert to grayscale
            gray = img.convert('L')
            
            # Calculate histogram
            hist = gray.histogram()
            
            # Text images have high contrast (peaks at black/white)
            black_pixels = sum(hist[:50])  # Near black
            white_pixels = sum(hist[200:])  # Near white
            total_pixels = sum(hist)
            
            contrast_ratio = (black_pixels + white_pixels) / total_pixels
            
            return contrast_ratio > 0.7