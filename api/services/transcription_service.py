"""
Azure Speech Services transcription client
Handles both batch and real-time transcription
"""
import logging
import time
from typing import Optional, Tuple
import azure.cognitiveservices.speech as speechsdk
from api.shared.config import AzureConfig

logger = logging.getLogger(__name__)


class TranscriptionService:
    """Service for Azure Speech Services transcription"""
    
    def __init__(self, config: AzureConfig):
        self.config = config
        self.speech_config = speechsdk.SpeechConfig(
            subscription=config.speech_key,
            region=config.speech_region
        )
        # Configure for medical/healthcare conversations
        self.speech_config.speech_recognition_language = "en-US"
        self.speech_config.enable_dictation()
        # Request detailed output including word-level timestamps
        self.speech_config.request_word_level_timestamps()
        self.speech_config.output_format = speechsdk.OutputFormat.Detailed
    
    def transcribe_audio_file(self, audio_file_path: str) -> Tuple[bool, str, Optional[dict]]:
        """
        Transcribe an audio file using Azure Speech Services
        
        Args:
            audio_file_path: Path to the audio file
            
        Returns:
            Tuple of (success, transcription_text, metadata)
        """
        try:
            logger.info(f"Starting transcription for: {audio_file_path}")
            start_time = time.time()
            
            # Configure audio input from file
            audio_config = speechsdk.AudioConfig(filename=audio_file_path)
            
            # Create speech recognizer
            speech_recognizer = speechsdk.SpeechRecognizer(
                speech_config=self.speech_config,
                audio_config=audio_config
            )
            
            # Collect all recognized text segments
            all_results = []
            done = False
            
            def recognized_callback(evt):
                """Callback for recognized speech"""
                if evt.result.reason == speechsdk.ResultReason.RecognizedSpeech:
                    all_results.append(evt.result.text)
                    logger.debug(f"Recognized: {evt.result.text[:50]}...")
            
            def session_stopped_callback(evt):
                """Callback when session stops"""
                nonlocal done
                done = True
                logger.info("Transcription session stopped")
            
            def canceled_callback(evt):
                """Callback for cancellation"""
                nonlocal done
                done = True
                if evt.reason == speechsdk.CancellationReason.Error:
                    logger.error(f"Transcription error: {evt.error_details}")
            
            # Connect callbacks
            speech_recognizer.recognized.connect(recognized_callback)
            speech_recognizer.session_stopped.connect(session_stopped_callback)
            speech_recognizer.canceled.connect(canceled_callback)
            
            # Start continuous recognition
            speech_recognizer.start_continuous_recognition()
            
            # Wait for completion
            while not done:
                time.sleep(0.5)
            
            speech_recognizer.stop_continuous_recognition()
            
            # Combine all recognized text
            full_transcription = " ".join(all_results)
            processing_time = time.time() - start_time
            
            metadata = {
                "processing_time_seconds": processing_time,
                "segments_count": len(all_results),
                "character_count": len(full_transcription),
                "word_count": len(full_transcription.split()) if full_transcription else 0
            }
            
            logger.info(f"Transcription completed in {processing_time:.2f}s, {metadata['word_count']} words")
            
            return True, full_transcription, metadata
            
        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            return False, str(e), None
    
    def transcribe_audio_bytes(self, audio_bytes: bytes, audio_format: str = "wav") -> Tuple[bool, str, Optional[dict]]:
        """
        Transcribe audio from bytes using push stream
        
        Args:
            audio_bytes: Audio content as bytes
            audio_format: Audio format (wav, mp3, etc.)
            
        Returns:
            Tuple of (success, transcription_text, metadata)
        """
        try:
            import tempfile
            import os
            
            logger.info(f"Starting transcription for audio bytes ({len(audio_bytes)} bytes)")
            
            # Write bytes to temporary file (Speech SDK works better with files)
            with tempfile.NamedTemporaryFile(suffix=f".{audio_format}", delete=False) as tmp_file:
                tmp_file.write(audio_bytes)
                tmp_path = tmp_file.name
            
            try:
                # Transcribe the temporary file
                success, text, metadata = self.transcribe_audio_file(tmp_path)
                return success, text, metadata
            finally:
                # Clean up temporary file
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
                    
        except Exception as e:
            logger.error(f"Transcription from bytes failed: {e}")
            return False, str(e), None
    
    def transcribe_from_url(self, audio_url: str) -> Tuple[bool, str, Optional[dict]]:
        """
        Transcribe audio from a URL (e.g., blob storage URL)
        Note: For production, consider using batch transcription API for URLs
        
        Args:
            audio_url: URL to the audio file
            
        Returns:
            Tuple of (success, transcription_text, metadata)
        """
        try:
            import requests
            import tempfile
            import os
            from urllib.parse import urlparse
            
            logger.info(f"Downloading audio from URL for transcription")
            
            # Download the audio file
            response = requests.get(audio_url, timeout=300)
            response.raise_for_status()
            
            # Determine extension from URL
            parsed_url = urlparse(audio_url)
            path = parsed_url.path
            ext = os.path.splitext(path)[1] or ".wav"
            
            # Save to temporary file
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp_file:
                tmp_file.write(response.content)
                tmp_path = tmp_file.name
            
            try:
                success, text, metadata = self.transcribe_audio_file(tmp_path)
                return success, text, metadata
            finally:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
                    
        except Exception as e:
            logger.error(f"Transcription from URL failed: {e}")
            return False, str(e), None
