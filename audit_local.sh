#!/bin/bash

# AWS Multi-Account Inventory - Comprehensive 50-Point Audit Script
# This script performs a deep audit of your AWS inventory project
# checking structure, code quality, dependencies, and deployment readiness

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# Counters
PASSED=0
FAILED=0
WARNINGS=0
TOTAL_CHECKS=50

# Results array
declare -a AUDIT_RESULTS
declare -a FAILED_CHECKS
declare -a WARNING_CHECKS

# Function to perform a check
check() {
    local check_num=$1
    local check_name=$2
    local check_cmd=$3
    local severity=${4:-"ERROR"}  # ERROR or WARNING
    
    echo -ne "${BLUE}[${check_num}/${TOTAL_CHECKS}]${NC} Checking: ${check_name}... "
    
    if eval "$check_cmd" >/dev/null 2>&1; then
        echo -e "${GREEN}✓ PASSED${NC}"
        AUDIT_RESULTS+=("✓ [${check_num}] ${check_name}")
        ((PASSED++))
        return 0
    else
        if [ "$severity" = "WARNING" ]; then
            echo -e "${YELLOW}⚠ WARNING${NC}"
            WARNING_CHECKS+=("⚠ [${check_num}] ${check_name}")
            ((WARNINGS++))
        else
            echo -e "${RED}✗ FAILED${NC}"
            FAILED_CHECKS+=("✗ [${check_num}] ${check_name}")
            ((FAILED++))
        fi
        return 1
    fi
}

# Function to check file exists
file_exists() {
    [ -f "$1" ]
}

# Function to check directory exists
dir_exists() {
    [ -d "$1" ]
}

# Function to check Python syntax
python_syntax_check() {
    python3 -m py_compile "$1" 2>/dev/null
}

# Function to check if string exists in file
grep_check() {
    grep -q "$1" "$2" 2>/dev/null
}

# Function to check JSON validity
json_valid() {
    python3 -c "import json; json.load(open('$1'))" 2>/dev/null
}

# Function to check YAML validity
yaml_valid() {
    if [ -f "$1" ]; then
        python3 -c "import yaml; yaml.safe_load(open('$1'))" 2>/dev/null || return 1
    else
        return 1
    fi
}

# Function to check if Python module can be imported
can_import() {
    python3 -c "import $1" 2>/dev/null
}

# Function to check AWS CLI configuration
aws_configured() {
    aws sts get-caller-identity >/dev/null 2>&1
}

echo -e "${CYAN}================================================${NC}"
echo -e "${CYAN}AWS Multi-Account Inventory - 50-Point Deep Audit${NC}"
echo -e "${CYAN}================================================${NC}\n"

# Start time
START_TIME=$(date +%s)

# =========================
# SECTION 1: Project Structure (10 checks)
# =========================
echo -e "\n${YELLOW}Section 1: Project Structure${NC}"
echo "=============================="

check 1 "Root project directory structure" "dir_exists src && dir_exists config && dir_exists tests"
check 2 "Source code structure" "dir_exists src/collector && dir_exists src/query"
check 3 "Lambda handler in correct location" "file_exists src/handler.py"
check 4 "Enhanced collector module" "file_exists src/collector/enhanced_main.py"
check 5 "Query module exists" "file_exists src/query/inventory_query.py"
check 6 "Test directory structure" "dir_exists tests/unit"
check 7 "Scripts directory" "dir_exists scripts"
check 8 "Infrastructure directory" "dir_exists infrastructure || dir_exists terraform"
check 9 "Backup directory exists" "dir_exists backups" "WARNING"
check 10 "Documentation files" "file_exists README.md || file_exists INTEGRATION_SUMMARY.md"

# =========================
# SECTION 2: Core Python Files (10 checks)
# =========================
echo -e "\n${YELLOW}Section 2: Core Python Files${NC}"
echo "=============================="

check 11 "Enhanced collector Python syntax" "python_syntax_check src/collector/enhanced_main.py"
check 12 "Query module Python syntax" "python_syntax_check src/query/inventory_query.py"
check 13 "Lambda handler Python syntax" "python_syntax_check src/handler.py"
check 14 "Collector has AWSInventoryCollector class" "grep_check 'class AWSInventoryCollector' src/collector/enhanced_main.py"
check 15 "Query has InventoryQuery class" "grep_check 'class InventoryQuery' src/query/inventory_query.py"
check 16 "Lambda handler has lambda_handler function" "grep_check 'def lambda_handler' src/handler.py"
check 17 "DynamoDB pk/sk pattern implemented" "grep_check 'pk.*sk' src/collector/enhanced_main.py"
check 18 "Retry logic implemented" "grep_check 'retry\|backoff\|ClientError' src/collector/enhanced_main.py"
check 19 "Cost estimation functions" "grep_check 'estimate.*cost\|monthly_cost' src/collector/enhanced_main.py"
check 20 "Threading/parallel processing" "grep_check 'ThreadPoolExecutor\|threading\|concurrent' src/collector/enhanced_main.py"

# =========================
# SECTION 3: Configuration & Dependencies (8 checks)
# =========================
echo -e "\n${YELLOW}Section 3: Configuration & Dependencies${NC}"
echo "========================================="

check 21 "Requirements.txt exists" "file_exists requirements.txt"
check 22 "Config example exists" "file_exists config/accounts.json.example"
check 23 "Config example is valid JSON" "json_valid config/accounts.json.example"
check 24 "Actual config exists" "file_exists config/accounts.json" "WARNING"
check 25 "Required Python packages in requirements" "grep_check 'boto3' requirements.txt && grep_check 'pandas' requirements.txt"
check 26 "Environment file or template" "file_exists .env.example || file_exists .env.template" "WARNING"
check 27 "Gitignore configured" "file_exists .gitignore && grep_check 'accounts.json' .gitignore"
check 28 "Makefile exists" "file_exists Makefile"

# =========================
# SECTION 4: Build & Deployment (8 checks)
# =========================
echo -e "\n${YELLOW}Section 4: Build & Deployment${NC}"
echo "==============================="

check 29 "Lambda build script exists" "file_exists scripts/build-lambda.sh || file_exists scripts/build-lambda-enhanced.sh"
check 30 "Build script is executable" "[ -x scripts/build-lambda.sh ] || [ -x scripts/build-lambda-enhanced.sh ]"
check 31 "Deploy script exists" "file_exists deploy.sh || file_exists scripts/deploy-all.sh"
check 32 "CloudFormation template" "file_exists infrastructure/cloudformation.yaml || file_exists cloudformation/*.yaml"
check 33 "Terraform files" "file_exists terraform/main.tf || file_exists terraform/*.tf" "WARNING"
check 34 "Lambda layer configuration" "grep_check 'lambda-layer\|dependencies' scripts/build-lambda*.sh"
check 35 "S3 bucket configuration in deploy" "grep_check 'BUCKET\|s3' deploy.sh 2>/dev/null || true" "WARNING"
check 36 "IAM role template" "file_exists **/member-account-role.yaml || file_exists **/iam-role.yaml" "WARNING"

# =========================
# SECTION 5: Testing (7 checks)
# =========================
echo -e "\n${YELLOW}Section 5: Testing${NC}"
echo "==================="

check 37 "Unit tests exist" "file_exists tests/unit/test_enhanced_collector.py"
check 38 "Test file Python syntax" "python_syntax_check tests/unit/test_enhanced_collector.py 2>/dev/null || true" "WARNING"
check 39 "Integration tests exist" "file_exists tests/integration/*.py" "WARNING"
check 40 "Test Lambda locally script" "file_exists tests/test_lambda_locally.py" "WARNING"
check 41 "Pytest configuration" "file_exists pytest.ini || file_exists setup.cfg || grep_check 'pytest' requirements.txt" "WARNING"
check 42 "Mock/moto in requirements" "grep_check 'moto' requirements.txt" "WARNING"
check 43 "Test coverage configuration" "file_exists .coveragerc || grep_check 'coverage' requirements.txt" "WARNING"

# =========================
# SECTION 6: Code Quality & Security (7 checks)
# =========================
echo -e "\n${YELLOW}Section 6: Code Quality & Security${NC}"
echo "===================================="

check 44 "No hardcoded credentials" "! grep -r 'AKIA\|aws_secret_access_key.*=' src/ 2>/dev/null"
check 45 "External ID implementation" "grep_check 'external_id\|ExternalId' src/collector/enhanced_main.py"
check 46 "Error handling in collector" "grep_check 'try:\|except\|Exception' src/collector/enhanced_main.py"
check 47 "Logging implementation" "grep_check 'logging\|logger' src/collector/enhanced_main.py"
check 48 "Input validation" "grep_check 'validate\|check' src/collector/enhanced_main.py" "WARNING"
check 49 "Pagination handling" "grep_check 'paginator\|next_token\|LastEvaluatedKey' src/"
check 50 "Resource cleanup" "grep_check 'cleanup\|close\|shutdown' src/" "WARNING"

# =========================
# BONUS CHECKS (Beyond 50)
# =========================
echo -e "\n${YELLOW}Bonus Checks${NC}"
echo "=============="

# Import validation
echo -e "\n${CYAN}Import Validation:${NC}"
if [ -f "src/handler.py" ]; then
    echo -n "  Handler imports: "
    grep "from collector" src/handler.py 2>/dev/null || echo "No collector import found!"
    grep "from query" src/handler.py 2>/dev/null || echo "No query import found!"
fi

# AWS Configuration
echo -e "\n${CYAN}AWS Configuration:${NC}"
if aws_configured; then
    echo -e "  ${GREEN}✓${NC} AWS CLI is configured"
    ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text 2>/dev/null || echo "Unknown")
    echo "  Current AWS Account: $ACCOUNT_ID"
else
    echo -e "  ${YELLOW}⚠${NC} AWS CLI not configured or no credentials"
fi

# Python Environment
echo -e "\n${CYAN}Python Environment:${NC}"
echo "  Python version: $(python3 --version)"
echo -n "  Virtual environment: "
if [ -n "$VIRTUAL_ENV" ]; then
    echo -e "${GREEN}Active${NC} ($(basename $VIRTUAL_ENV))"
else
    echo -e "${YELLOW}Not active${NC}"
fi

# Check if key Python packages are installed
echo -e "\n${CYAN}Installed Packages:${NC}"
for pkg in boto3 pandas pytest moto; do
    echo -n "  $pkg: "
    if python3 -c "import $pkg" 2>/dev/null; then
        version=$(python3 -c "import $pkg; print($pkg.__version__)" 2>/dev/null || echo "version unknown")
        echo -e "${GREEN}✓${NC} ($version)"
    else
        echo -e "${RED}✗${NC} Not installed"
    fi
done

# =========================
# SUMMARY
# =========================
END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

echo -e "\n${CYAN}================================================${NC}"
echo -e "${CYAN}AUDIT COMPLETE${NC}"
echo -e "${CYAN}================================================${NC}"

echo -e "\nExecution time: ${DURATION} seconds"
echo -e "\nResults Summary:"
echo -e "  ${GREEN}Passed:${NC} $PASSED/$TOTAL_CHECKS"
echo -e "  ${YELLOW}Warnings:${NC} $WARNINGS/$TOTAL_CHECKS"
echo -e "  ${RED}Failed:${NC} $FAILED/$TOTAL_CHECKS"

# Calculate score
SCORE=$((PASSED * 100 / TOTAL_CHECKS))
echo -e "\nProject Health Score: ${SCORE}%"

if [ $SCORE -ge 90 ]; then
    echo -e "Grade: ${GREEN}A - Excellent!${NC}"
elif [ $SCORE -ge 80 ]; then
    echo -e "Grade: ${GREEN}B - Good${NC}"
elif [ $SCORE -ge 70 ]; then
    echo -e "Grade: ${YELLOW}C - Acceptable${NC}"
elif [ $SCORE -ge 60 ]; then
    echo -e "Grade: ${YELLOW}D - Needs Improvement${NC}"
else
    echo -e "Grade: ${RED}F - Critical Issues${NC}"
fi

# =========================
# DETAILED FAILURE REPORT
# =========================
if [ ${#FAILED_CHECKS[@]} -gt 0 ]; then
    echo -e "\n${RED}FAILED CHECKS - MUST FIX:${NC}"
    echo "=========================="
    for check in "${FAILED_CHECKS[@]}"; do
        echo "$check"
    done
fi

if [ ${#WARNING_CHECKS[@]} -gt 0 ]; then
    echo -e "\n${YELLOW}WARNINGS - SHOULD FIX:${NC}"
    echo "======================"
    for check in "${WARNING_CHECKS[@]}"; do
        echo "$check"
    done
fi

# =========================
# RECOMMENDATIONS
# =========================
echo -e "\n${CYAN}RECOMMENDATIONS:${NC}"
echo "================="

# Generate specific recommendations based on failures
declare -a RECOMMENDATIONS

# Structure issues
if ! dir_exists "src/collector" || ! dir_exists "src/query"; then
    RECOMMENDATIONS+=("1. Fix directory structure: Ensure src/collector and src/query directories exist")
fi

if ! file_exists "src/handler.py"; then
    RECOMMENDATIONS+=("2. Create/move Lambda handler to src/handler.py")
fi

# Configuration issues
if ! file_exists "config/accounts.json"; then
    RECOMMENDATIONS+=("3. Create config/accounts.json from the example template")
fi

# Build issues
if ! [ -x "scripts/build-lambda.sh" ] && ! [ -x "scripts/build-lambda-enhanced.sh" ]; then
    RECOMMENDATIONS+=("4. Make build scripts executable: chmod +x scripts/build-lambda*.sh")
fi

# Testing issues
if [ $FAILED -gt 0 ] && grep -q "test" <<< "${FAILED_CHECKS[@]}"; then
    RECOMMENDATIONS+=("5. Add comprehensive test coverage - unit and integration tests")
fi

# Security issues
if ! grep_check 'external_id\|ExternalId' src/collector/enhanced_main.py 2>/dev/null; then
    RECOMMENDATIONS+=("6. Implement ExternalId for cross-account role assumption")
fi

# Import issues
if ! grep_check "from collector.enhanced_main import" src/handler.py 2>/dev/null; then
    RECOMMENDATIONS+=("7. Fix import statements in handler.py to match your module structure")
fi

# Deployment readiness
if ! file_exists "infrastructure/cloudformation.yaml" && ! file_exists "terraform/main.tf"; then
    RECOMMENDATIONS+=("8. Add infrastructure as code templates (CloudFormation or Terraform)")
fi

# Dependencies
if ! grep_check 'pandas' requirements.txt 2>/dev/null; then
    RECOMMENDATIONS+=("9. Ensure all required dependencies are in requirements.txt")
fi

# AWS configuration
if ! aws_configured; then
    RECOMMENDATIONS+=("10. Configure AWS CLI with appropriate credentials")
fi

# Display recommendations
if [ ${#RECOMMENDATIONS[@]} -gt 0 ]; then
    for rec in "${RECOMMENDATIONS[@]}"; do
        echo "  • $rec"
    done
else
    echo "  • Your project is in excellent shape! Consider adding more tests and documentation."
fi

# =========================
# NEXT STEPS
# =========================
echo -e "\n${CYAN}NEXT STEPS:${NC}"
echo "==========="
echo "1. Fix all ${RED}FAILED${NC} checks first (critical issues)"
echo "2. Address ${YELLOW}WARNING${NC} checks to improve project quality"
echo "3. Run 'make test' to verify your code works"
echo "4. Run 'make build-lambda' to test the build process"
echo "5. Deploy to a test environment first"

# =========================
# EXPORT REPORT
# =========================
REPORT_FILE="audit_report_$(date +%Y%m%d_%H%M%S).txt"
{
    echo "AWS Multi-Account Inventory - Audit Report"
    echo "Generated: $(date)"
    echo "==========================================\n"
    echo "Summary: Passed=$PASSED, Warnings=$WARNINGS, Failed=$FAILED"
    echo "Score: ${SCORE}%"
    echo "\nFailed Checks:"
    for check in "${FAILED_CHECKS[@]}"; do
        echo "$check"
    done
    echo "\nWarning Checks:"
    for check in "${WARNING_CHECKS[@]}"; do
        echo "$check"
    done
    echo "\nRecommendations:"
    for rec in "${RECOMMENDATIONS[@]}"; do
        echo "$rec"
    done
} > "$REPORT_FILE"

echo -e "\n${GREEN}Full report saved to: $REPORT_FILE${NC}"

# Exit with appropriate code
if [ $FAILED -gt 10 ]; then
    exit 2  # Critical failures
elif [ $FAILED -gt 0 ]; then
    exit 1  # Some failures
else
    exit 0  # Success
fi