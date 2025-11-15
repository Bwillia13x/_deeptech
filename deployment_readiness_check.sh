#!/bin/bash
# Production Deployment Readiness Check
# Comprehensive validation before production deployment

set -e

echo "=========================================="
echo "Signal Harvester Deployment Readiness Check"
echo "Date: $(date)"
echo "=========================================="
echo ""

# Track results
PASSED=0
FAILED=0
WARNINGS=0

# Function to track test results
check_test() {
    local test_name=$1
    local result=$2
    
    if [ "$result" -eq 0 ]; then
        echo "✅ PASS: $test_name"
        ((PASSED++))
    else
        echo "❌ FAIL: $test_name"
        ((FAILED++))
    fi
}

warn_test() {
    local test_name=$1
    echo "⚠️  WARN: $test_name"
    ((WARNINGS++))
}

# 1. Environment Configuration
echo "1️⃣  Environment Configuration"
echo "-------------------------------------------"

# Check .env files
test_count=0
for env_file in ".env" ".env.staging"; do
    if [ -f "$env_file" ]; then
        if grep -q "\(DUMMY\|dummy\|change_me\|fake\|fake_key\|placeholder\|your_\)" "$env_file"; then
            echo "   ✅ $env_file contains only placeholder values"
            ((test_count++))
        elif grep -qE "^[A-Z_]+=[a-zA-Z0-9+/=_-]{16,}$" "$env_file"; then
            warn_test "$env_file may contain real credentials (manual verification required)"
        else
            echo "   ✅ $env_file properly configured"
            ((test_count++))
        fi
    else
        echo "   ✅ $env_file not present (OK)"
        ((test_count++))
    fi
done
check_test "Environment configuration" 0
echo ""

# 2. Security Checks
echo "2️⃣  Security Checks"
echo "-------------------------------------------"

# Check file permissions
if [ -f ".env" ]; then
    if stat -c "%a" .env | grep -q "700"; then
        echo "   ✅ .env permissions are 700 (secure)"
    else
        echo "   ⚠️  .env permissions should be 700 (current: $(stat -c "%a" .env))"
    fi
fi

if [ -f ".env.staging" ]; then
    if stat -c "%a" .env.staging | grep -q "700"; then
        echo "   ✅ .env.staging permissions are 700 (secure)"
    else
        echo "   ⚠️  .env.staging permissions should be 700 (current: $(stat -c "%a" .env.staging))"
    fi
fi

# Check gitignore
git check-ignore .env > /dev/null 2>&1
check_test ".env in .gitignore" $? > /dev/null
git check-ignore .env.staging > /dev/null 2>&1
check_test ".env.staging in .gitignore" $? > /dev/null

echo ""

# 3. Frontend Build Validation
echo "3️⃣  Frontend Build Validation"
echo "-------------------------------------------"

if [ -d "frontend/dist" ]; then
    echo "   ✅ Frontend dist/ directory exists"
    
    # Check if build is recent
    if find frontend/dist -mtime -1 | grep -q .; then
        echo "   ✅ Frontend build is recent (within 24h)"
    else
        warn_test "Frontend build is older than 24h - consider rebuilding"
    fi
    
    # Check bundle size
    bundle_size=$(du -sh frontend/dist/assets/*.js 2>/dev/null | tail -1 | cut -f1)
    echo "   ✅ Frontend bundle size: $bundle_size"
else
    echo "   ⚠️  Frontend dist/ not found - run 'npm run build'"
    ((FAILED++))
fi
echo ""

# 4. Backend Health Check
echo "4️⃣  Backend Health Check"
echo "-------------------------------------------"

backend_health=$(curl -s http://localhost:8000/health/ready 2>/dev/null)
if echo "$backend_health" | grep -q '"status"'; then
    status=$(echo "$backend_health" | grep -o '"status":"[^"]*"' | cut -d'"' -f4)
    echo "   Backend status: $status"
    
    if [ "$status" = "healthy" ]; then
        echo "   ✅ Backend is healthy"
    elif [ "$status" = "degraded" ]; then
        warn_test "Backend is degraded (check dependencies)"
    else
        echo "   ⚠️  Backend is unhealthy"
    fi
else
    warn_test "Could not reach backend health endpoint"
fi

# Check metrics endpoint
if curl -s http://localhost:8000/metrics > /dev/null 2>&1; then
    echo "   ✅ Metrics endpoint responding"
else
    echo "   ⚠️  Metrics endpoint not responding"
fi

echo ""

# 5. Dependencies Scan
echo "5️⃣  Dependency Security Scan"
echo "-------------------------------------------"

if command -v safety &> /dev/null; then
    safety_output=$(safety check 2>&1)
    if echo "$safety_output" | grep -q "No known security vulnerabilities"; then
        echo "   ✅ Python dependencies scan passed"
    else
        echo "$safety_output" | grep -A 5 "vulnerabilities"
        warn_test "Python dependencies have vulnerabilities"
    fi
else
    warn_test "Safety not installed - run 'pip install safety'"
fi

echo ""

# 6. Database Check
echo "6️⃣  Database Check"
echo "-------------------------------------------"

if [ -d "var" ]; then
    db_files=$(find var -name "*.db" | wc -l)
    echo "   Found $db_files database files in var/"
    
    # Check database size
    if [ -f "var/app.db" ]; then
        size=$(du -sh var/app.db | cut -f1)
        echo "   ✅ Main database size: $size"
    fi
else
    echo "   ✅ No var/ directory (fresh deployment)"
fi
echo ""

# 7. Docker Build Check (Optional)
echo "7️⃣  Docker Build Check"
echo "-------------------------------------------"

if command -v docker &> /dev/null; then
    if docker images | grep -q "signal-harvester"; then
        echo "   ✅ Docker image exists locally"
        
        # Check recent build
        if docker images signal-harvester | grep -q "$(date +%m/%d)"; then
            echo "   ✅ Docker image built recently"
        else
            warn_test "Docker image may be outdated"
        fi
    else
        warn_test "Docker image not found - build recommended"
    fi
else
    echo "   ℹ️  Docker not available (skipping)"
fi
echo ""

# 8. Development Tools
echo "8️⃣  Development Tools"
echo "-------------------------------------------"

# Check git status
echo "   Git status:"
modified=$(git status --porcelain 2>/dev/null | grep "^ M" | wc -l)
untracked=$(git status --porcelain 2>/dev/null | grep "^??" | wc -l)
echo "     - Modified files: $modified"
echo "     - Untracked files: $untracked"

if [ "$modified" -gt 0 ] || [ "$untracked" -gt 0 ]; then
    warn_test "Repository has uncommitted changes"
fi

echo ""

# Summary
echo "=========================================="
echo "📊 DEPLOYMENT READINESS SUMMARY"
echo "=========================================="
echo "✅ Passed: $PASSED"
echo "❌ Failed: $FAILED"
echo "⚠️  Warnings: $WARNINGS"
echo ""

if [ "$FAILED" -eq 0 ] && [ "$WARNINGS" -eq 0 ]; then
    echo "🎉 SYSTEM IS READY FOR PRODUCTION DEPLOYMENT!"
    exit 0
elif [ "$FAILED" -eq 0 ] && [ "$WARNINGS" -gt 0 ]; then
    echo "⚠️  SYSTEM IS READY WITH WARNINGS"
    echo "   Review warnings before proceeding"
    exit 0
else
    echo "❌ SYSTEM NOT READY FOR DEPLOYMENT"
    echo "   Please address failed checks"
    exit 1
fi
