# configure-frontend.ps1 - Update frontend API URL after deployment
# Usage: .\configure-frontend.ps1 -FunctionAppName <name>

param(
    [Parameter(Mandatory=$true)]
    [string]$FunctionAppName
)

$ApiUrl = "https://${FunctionAppName}.azurewebsites.net/api"

Write-Host "Updating frontend to use API: $ApiUrl" -ForegroundColor Cyan

# Update app.js
$appJsPath = "frontend/app.js"
$appJsContent = Get-Content $appJsPath -Raw
$appJsContent = $appJsContent -replace "return 'https://[^']*\.azurewebsites\.net/api'", "return '$ApiUrl'"
Set-Content -Path $appJsPath -Value $appJsContent -NoNewline

# Update staticwebapp.config.json
$configPath = "frontend/staticwebapp.config.json"
$configContent = Get-Content $configPath -Raw
$configContent = $configContent -replace '"[^"]*\.azurewebsites\.net"', "`"${FunctionAppName}.azurewebsites.net`""
Set-Content -Path $configPath -Value $configContent -NoNewline

Write-Host "Frontend updated!" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:"
Write-Host "1. Commit and push changes"
Write-Host "2. GitHub Actions will deploy the updated frontend"
