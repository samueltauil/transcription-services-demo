"""
Azure Functions entry point
Healthcare Transcription Services Demo
"""
import azure.functions as func

from api.functions import upload_bp, process_bp, results_bp

# Create the main function app
app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

# Register blueprints
app.register_functions(upload_bp)
app.register_functions(process_bp)
app.register_functions(results_bp)
