# Signal Harvester - Codebase Bug Report

## Executive Summary

A comprehensive sweep of the signal-harvester codebase identified **147 linting errors**, **35+ mypy type errors**, and several security, performance, and reliability issues. The codebase is functional (all tests pass) but requires significant cleanup for production readiness.

---

## 1. Code Quality Issues (Linting)

### Import Organization Issues
- **49 files** have unsorted/unformatted import blocks
- **Multiple unused imports** across the codebase
  - `typing.Iterable`, `typing.Tuple`, `typing.List`, `typing.Any`, `typing.Dict`, `typing.Optional`
  - Various module imports that are imported but never used

### Line Length Violations
- **40+ instances** of lines exceeding 120 characters
- Some lines exceed 160+ characters (e.g., retain.py:739, 762)

### F-String Issues
- **2 instances** of f-strings without placeholders (site.py:163, validation.py:29)

### Unused Variables
- **5+ instances** of variables assigned but never used
- Example: `s` in cli.py:29, `to_keep` in prune.py:65, `blocked` in quota.py:253

---

## 2. Security Issues

### Input Validation Concerns
- **No SQL injection prevention** - Direct string concatenation in some SQL queries
- **File path handling** - Some paths constructed with string concatenation instead of `os.path.join()`
- **No rate limiting** on CLI daemon loop (cli.py:67-70)

### Exception Handling Issues
- **59 instances** of bare `except Exception` blocks that could swallow security-relevant errors
- Some exception handlers silently pass without logging (retain.py:131)
- Potential for information leakage through verbose error messages

### File Operations
- All file operations use `with open()` (good), but no validation of file sizes before reading
- No verification that file paths stay within allowed directories (path traversal risk)

---

## 3. Performance Issues

### Database Operations
- **No connection pooling** - New connection created for each DB operation
- **Missing transaction batching** - Individual commits instead of bulk operations
- Inefficient queries with `LIKE` operators without proper indexing

### Memory Usage
- **No streaming** for large file operations - Everything loaded into memory
- Snapshot operations read entire files into memory (snapshot.py:44)
- CSV export loads all rows before writing (cli/data_commands.py)

### Inefficient DateTime Handling
- **Mixed timezone usage**: `datetime.utcnow()` (deprecated) and `datetime.now(tz=timezone.utc)`
- Repeated timezone conversions instead of using UTC consistently
- Date parsing with multiple try/except blocks (retain.py:27-31)

### String Operations
- **Inefficient string building**: Using `+=` in loops instead of `join()`
- Repeated JSON serialization/deserialization without caching

---

## 4. Reliability Issues

### Error Handling
- **Silent failures**: Several functions return `None` on error without proper error propagation
- **Inconsistent error handling**: Mix of exceptions, return codes, and print statements
- **Missing validation**: Input parameters not validated before use

### Race Conditions
- **SQLite with threading**: `check_same_thread=False` set (db.py:21) but no locking mechanism
- **File operations**: No atomic operations for file writes
- **Shared state**: Global variables used without synchronization

### Resource Management
- **No timeout handling** for network operations (x_client.py)
- **No retry logic** for transient failures
- **File descriptors**: Potential leaks if exceptions occur during file operations

---

## 5. Code Maintainability Issues

### Type Safety (Mypy Errors)
- **35+ type errors** including:
  - Incompatible return types
  - Missing type annotations
  - Incorrect type assignments
  - Unused `type: ignore` comments
- Mix of `typing` imports and built-in types (List vs list, Dict vs dict)

### Code Duplication
- **Similar functions** across modules (retain.py, quota.py, prune.py share logic)
- **Repeated patterns** for CLI argument parsing
- **Duplicate constants** and magic numbers scattered throughout

### Documentation
- **Inconsistent docstrings**: Some functions have no documentation
- **No type hints** for many public functions
- **Magic numbers** without explanation (e.g., timeout=10.0, chunk_size=1024*1024)

---

## 6. Specific File Issues

### src/signal_harvester/db.py
- **Line 21**: `check_same_thread=False` without thread safety measures
- **Lines 24-27**: PRAGMA settings repeated for every connection
- **Line 163**: Potential SQL injection via `row.get("tweet_id")`

### src/signal_harvester/cli.py
- **Lines 67-70**: Infinite loop without proper shutdown handling
- **Line 29**: Unused variable `s`

### src/signal_harvester/retain.py
- **Lines 204-224**: Type incompatibility with tuple assignments
- **Line 384**: Potential `None` comparison in datetime operation
- **Line 495**: Unsafe `int()` conversion without validation

### src/signal_harvester/api.py
- **Lines 217, 223**: Overly long lines with inline dictionaries
- **Line 302-304**: PRAGMA queries could be cached

### src/signal_harvester/x_client.py
- **Line 64**: Broad exception handling swallows network errors
- **Lines 70-88**: Multiple `.get()` calls without default values

### src/signal_harvester/serve.py
- **Lines 8-11**: Multiple unused imports
- **Line 88**: Unsafe bytes to string conversion

---

## 7. Testing Issues

### Test Coverage Gaps
- **No error path testing**: Most tests only cover happy paths
- **No concurrency tests**: Threading issues not tested
- **No security tests**: Input validation not tested
- **No performance tests**: No benchmarks for critical paths

### Test Quality
- **Test duplication**: Similar test patterns repeated
- **Hardcoded values**: Magic numbers in tests
- **No mocking**: Some tests hit real filesystem/DB

---

## 8. Configuration Issues

### Settings Management
- **Environment variable mixing**: Direct `os.getenv()` calls scattered throughout
- **No validation**: Settings not validated on load
- **No defaults documentation**: Unclear which settings are required

---

## Priority Recommendations

### 🔴 Critical (Fix Immediately)
1. **SQL injection vulnerabilities** - Parameterize all queries
2. **Thread safety** - Add proper locking for SQLite access
3. **Exception handling** - Remove bare `except:` clauses
4. **Input validation** - Validate all user inputs

### 🟡 High (Fix Soon)
1. **Type safety** - Fix all mypy errors
2. **Error handling** - Standardize error handling across codebase
3. **Performance** - Add connection pooling and streaming
4. **Code quality** - Fix all linting errors

### 🟢 Medium (Fix When Possible)
1. **Documentation** - Add docstrings and type hints
2. **Code duplication** - Refactor common patterns
3. **Testing** - Add tests for error paths and edge cases
4. **Configuration** - Centralize settings management

---

## Files with Most Issues

1. **src/signal_harvester/retain.py** - 25+ issues (type errors, long lines, complexity)
2. **src/signal_harvester/api.py** - 15+ issues (linting, type errors)
3. **src/signal_harvester/quota.py** - 15+ issues (similar to retain.py)
4. **src/signal_harvester/db.py** - 10+ issues (security, type errors)
5. **src/signal_harvester/cli.py** - 10+ issues (unused imports, variables)

---

## Conclusion

The codebase is functional but shows signs of rapid development without sufficient code review. The good news is that all tests pass, indicating core functionality works. However, the numerous linting errors, type issues, and security concerns suggest the need for a comprehensive cleanup before production deployment.

**Estimated cleanup effort**: 2-3 days for critical issues, 1-2 weeks for all issues
**Risk level**: Medium-High (functional but with security and reliability concerns)
**Recommendation**: Address critical issues before production deployment
