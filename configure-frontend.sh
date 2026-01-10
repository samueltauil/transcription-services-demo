#!/bin/bash
# configure-frontend.sh - Update frontend API URL after deployment
# Usage: ./configure-frontend.sh <function-app-name>

FUNCTION_APP_NAME=$1

if [ -z "$FUNCTION_APP_NAME" ]; then
    echo "Usage: ./configure-frontend.sh <function-app-name>"
    echo "Example: ./configure-frontend.sh healthtranscript-dev-func-abc123"
    exit 1
fi

API_URL="https://${FUNCTION_APP_NAME}.azurewebsites.net/api"

echo "Updating frontend to use API: $API_URL"

# Update app.js
sed -i "s|return 'https://[^']*\.azurewebsites\.net/api'|return '${API_URL}'|g" frontend/app.js

# Update staticwebapp.config.json
sed -i "s|\"[^\"]*\.azurewebsites\.net\"|\"${FUNCTION_APP_NAME}.azurewebsites.net\"|g" frontend/staticwebapp.config.json

echo "✓ Frontend updated!"
echo ""
echo "Next steps:"
echo "1. Commit and push changes"
echo "2. GitHub Actions will deploy the updated frontend"
