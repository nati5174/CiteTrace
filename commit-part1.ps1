$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$repositoryPath = $PSScriptRoot.Replace('\', '/')

git -c "safe.directory=$repositoryPath" add .
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

git -c "safe.directory=$repositoryPath" commit -m "feat: implement citation schemas and deterministic mutations"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

git -c "safe.directory=$repositoryPath" status --short
exit $LASTEXITCODE
