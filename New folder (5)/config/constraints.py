"""Resource constraints and limits for Raspberry Pi Zero"""
from dataclasses import dataclass
from typing import Dict, Any


@dataclass
class PiZeroConstraints:
    """Hardware constraints for Raspberry Pi Zero W"""
    CPU_CORES: int = 1
    CPU_FREQ_MHZ: int = 1000
    RAM_MB: int = 512
    GPU_SPLIT_MB: int = 16  # Minimal GPU memory
    AVAILABLE_RAM_MB: int = 496
    
    # Process limits
    MAX_WORKER_PROCESSES: int = 1
    MAX_THREADS_PER_WORKER: int = 2
    MAX_DB_CONNECTIONS: int = 3
    
    # Memory allocations (MB)
    WEB_SERVER_MEMORY: int = 100
    OCR_PROCESS_MEMORY: int = 200
    ENCRYPTION_BUFFER: int = 50
    DB_CACHE_MEMORY: int = 50
    OS_OVERHEAD: int = 96
    
    # I/O constraints
    SD_CARD_MAX_WRITE_MB_S: float = 10.0
    USB_2_MAX_MB_S: float = 35.0
    
    # Timeouts (seconds)
    OCR_TIMEOUT: int = 30
    ENCRYPTION_TIMEOUT: int = 10
    WEB_REQUEST_TIMEOUT: int = 60
    
    def validate_memory_allocation(self) -> bool:
        """Ensure memory allocations don't exceed available RAM"""
        total = (
            self.WEB_SERVER_MEMORY +
            self.OCR_PROCESS_MEMORY +
            self.ENCRYPTION_BUFFER +
            self.DB_CACHE_MEMORY +
            self.OS_OVERHEAD
        )
        return total <= self.AVAILABLE_RAM_MB
    
    def get_process_limits(self) -> Dict[str, Any]:
        """Get resource limits for process creation"""
        import resource
        return {
            resource.RLIMIT_AS: (self.OCR_PROCESS_MEMORY * 1024 * 1024, 
                               self.OCR_PROCESS_MEMORY * 1024 * 1024),
            resource.RLIMIT_CPU: (self.OCR_TIMEOUT, self.OCR_TIMEOUT + 5),
            resource.RLIMIT_NOFILE: (256, 256)
        }


# Global constraints instance
PI_ZERO_LIMITS = PiZeroConstraints()