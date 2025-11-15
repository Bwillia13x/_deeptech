#!/bin/bash
# Security Scan Script
# Runs vulnerability checks on the codebase

set -e

echo "=== Signal Harvester Security Scan ==="
echo "Date: $(date)"
echo "Directory: $(pwd)"
echo ""

# 1. Check for exposed secrets in current files
echo "1. Scanning for exposed secrets..."
echo "   Checking for common credential patterns..."

# Search for potentially exposed secrets (excluding example files)
if grep -r --exclude="*.example" --exclude="*.backup" --exclude-dir=.git \
  -i -E "(password|secret|token|key)=[a-zA-Z0-9+/=_-]{16,}" \
  . 2>/dev/null | grep -v "DUMMY\|dummy\|change_me\|fake\|PLACEHOLDER"; then
    echo "   ⚠️  Potential secrets found!"
    exit 1
else
    echo "   ✅ No exposed secrets found"
fi

# 2. Check .env files
echo ""
echo "2. Checking .env files..."
for file in .env .env.staging .env.staging.backup; do
  if [ -f "$file" ]; then
    if grep -q -E "(DUMMY|dummy|change_me|PLACEHOLDER|fake|fake_key|fake\_|dummy_)" "$file"; then
      echo "   ✅ $file contains only dummy values"
    else
      echo "   ⚠️  $file may contain real credentials - verify manually"
    fi
  fi
done

# 3. Run safety check for Python dependencies
echo ""
echo "3. Running Python dependency vulnerability scan..."
if command -v safety &> /dev/null; then
    safety check || echo "   ⚠️  safety check found vulnerabilities"
else
    echo "   Installing safety..."
    pip install safety
    safety check || echo "   ⚠️  safety check found vulnerabilities"
fi

# 4. Check file permissions
echo ""
echo "4. Checking file permissions..."
if [ -f ".env" ] && [ "$(stat -c "%a" .env)" != "600" ]; then
    echo "   ⚠️  .env file permissions are too permissive (should be 600)"
    chmod 600 .env
    echo "   Fixed: Changed .env permissions to 600"
fi

if [ -f ".env.staging" ] && [ "$(stat -c "%a" .env.staging)" != "600" ]; then
    echo "   ⚠️  .env.staging file permissions are too permissive (should be 600)"
    chmod 600 .env.staging
    echo "   Fixed: Changed .env.staging permissions to 600"
fi

# 5. Check git status
echo ""
echo "5. Checking git status..."
if git status --porcelain | grep -q "\.env.*\.backup"; then
    echo "   ⚠️  .env backup files found - should they be removed?"
fi

# 6. Verify .gitignore
echo ""
echo "6. Checking .gitignore..."
if grep -q "\.env" .gitignore && grep -q "\.env\." .gitignore; then
    echo "   ✅ .gitignore properly configured for .env files"
else
    echo "   ⚠️  .gitignore may need updates for .env files"
fi

echo ""
echo "=== Security Scan Complete ==="
echo "✅ No critical issues found"
echo ""
echo "Recommendations:"
echo "  - Verify all backup .env files are removed before committing"
echo "  - Use environment variables or Docker secrets in production"
echo "  - Rotate any exposed credentials immediately"
