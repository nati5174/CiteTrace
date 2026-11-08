$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$repositoryPath = $PSScriptRoot.Replace('\', '/')

git -c "safe.directory=$repositoryPath" add .
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

git -c "safe.directory=$repositoryPath" diff --cached --check
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

git -c "safe.directory=$repositoryPath" commit -m "feat: complete resolution, evaluation, reporting, and milestone audit"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

git -c "safe.directory=$repositoryPath" status --short
exit $LASTEXITCODE
