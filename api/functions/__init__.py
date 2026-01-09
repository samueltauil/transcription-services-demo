"""Functions package"""
from .upload_audio import bp as upload_bp
from .process_transcription import bp as process_bp
from .get_results import bp as results_bp

__all__ = ["upload_bp", "process_bp", "results_bp"]
