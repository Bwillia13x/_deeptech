# Manual Integration Testing Checklist

**Status**: ✅ Backend API ready, Frontend contract tests pass, ready for manual browser testing

## ✅ Backend Test Results (2025-11-14)

See `BACKEND_TEST_RESULTS.md` for full details

**API Endpoints:** 100% functional
- ✅ `GET /experiments` - 200 OK
- ✅ `GET /labels` - 200 OK
- ✅ `GET /health/live` - 200 OK
- ✅ `GET /health/ready` - 200 OK
- ✅ `POST /experiments` - Experiment creation
- ✅ `POST /experiments/run` - Run experiment
- ✅ `GET /experiments/compare` - A/B comparison

**Workflow Tests:** 100% passing
- ✅ Experiment creation (2 experiments)
- ✅ Run recording & metrics calculation
- ✅ A/B comparison (delta calculations, winner determination)
- ✅ Labels CRUD (create, list, export)
- ✅ Data integrity (FK constraints, unique constraints)

**Database Schema:** ✅ Validated
- All tables created: experiments, experiment_runs, discovery_labels, artifacts
- All indexes created for performance
- Foreign key constraints enforced
- JSON config serialization working

## ✅ Completed Prerequisites

- [x] **Contract Tests**: 11/11 passing (tests/test_experiment_ui.py)
- [x] **Type Check**: Clean (`npm run typecheck`)
- [x] **React Hooks Fix**: Resolved conditional hook execution errors in:
  - `src/pages/ExperimentDetail.tsx`
  - `src/pages/TopicDetail.tsx`
- [x] **Missing Dependencies**: Added `toast` to useEffect dependency arrays
- [x] **Backend API**: 100% functional
- [x] **Database**: Schema validated, migrations applied
- [x] **Integration Tests**: `test_workflow.py` passes completely

## 🚀 Ready for Manual Browser Testing

**Setup Backend API:**
```bash
cd /Users/benjaminwilliams/_deeptech/signal-harvester
python -m signal_harvester.api
# Runs on http://localhost:8000
```

**Setup Frontend Dev Server:**
```bash
cd /Users/benjaminwilliams/_deeptech/signal-harvester/frontend
npm run dev
# Opens http://localhost:5173/
```

**Expected Test Data:**
When you open `/experiments`, you should see:
- 2 experiments created by integration test
- Both experiments have 1 run each
- Comparison shows Experiment B as winner (higher precision)
- Metrics values: precision 0.88 vs 0.91, recall 0.98, F1 ~0.93-0.94

When you open `/labels`, you should see:
- 2 labeled artifacts (IDs 1 and 2)
- Labels: true_positive (0.95 confidence), false_positive (0.85 confidence)
- Annotator: integration-test-173163...

**Browser Checklist:**

### Experiments Dashboard (`/experiments`)
- [ ] List loads with proper loading states
- [ ] Charts render without console errors
- [ ] Metrics display correctly (precision/recall/F1/accuracy)
- [ ] New Experiment button works
- [ ] Mobile layouts are responsive

### Experiment Creation/Run
- [ ] Create a new experiment via form
- [ ] Run experiment shows progress indicator
- [ ] Metrics calculate correctly after run completion
- [ ] Success toast appears

### A/B Comparison
- [ ] Create second experiment with different config
- [ ] Run second experiment
- [ ] Compare results shows delta calculations
- [ ] Winner logic displays correctly
- [ ] Trend charts render properly

### Ground Truth Labels (`/labels`)
- [ ] List shows labeled artifacts
- [ ] Add new label form works
- [ ] Edit existing label (upsert) works
- [ ] Export CSV downloads file
- [ ] Grid updates without manual refresh

### Navigation/Responsiveness
- [ ] Sidebar has "A/B Testing" (FlaskConical icon) entry
- [ ] Sidebar has "Ground Truth" (Tag icon) entry
- [ ] Active states highlight correctly
- [ ] Mobile menu collapses/expands
- [ ] Tables scroll horizontally on mobile
- [ ] Charts are responsive
- [ ] Action button rows wrap gracefully
- [ ] Loading skeletons appear where expected
- [ ] Empty states display for no data

### Cross-Linking
- [ ] Experiment detail has link to labels
- [ ] Labels page has link back to experiments
- [ ] Breadcrumb navigation works

## Lint Issues (Non-Blocking)

**Remaining warnings/errors:**
- Unused imports (TypeScript types, Lucide icons)
- Unused variables in TopicList/Labels/ExperimentDetail

**Status:** These are cleanup items that don't affect functionality. Reference: CROSS_SOURCE_CORROBORATION_UI_COMPLETION_REPORT.md notes that lint flags unused imports but they're non-blocking.

## ✅ Ready for Manual QA!

**Test Database Location:** `/Users/benjaminwilliams/_deeptech/var/harvester.db`
**Test Script:** `/Users/benjaminwilliams/_deeptech/test_workflow.py`

Once you complete the checklist above:
1. Update `AGENTS.md` to mark Experiments UI as complete (Phase Two: 5/6 priorities done)
2. Update `CROSS_SOURCE_CORROBORATION_UI_COMPLETION_REPORT.md` with manual QA results
3. Copy browser console output and network requests to completion report
4. Note any responsive issues found on mobile/tablet views

## 🎯 Success Criteria (Check these off as you test)

**Before moving to Phase Three, verify:**
- [ ] `/experiments` list loads with the 2 test experiments
- [ ] Experiment detail pages show correct metrics (precision/recall/F1/accuracy)
- [ ] A/B comparison shows delta calculations and winner (Experiment B)
- [ ] Charts render without console errors
- [ ] `/labels` shows 2 labeled artifacts
- [ ] Add new label form works and appears in list
- [ ] CSV export downloads file properly
- [ ] Mobile responsive layout works (test 320px, 768px, 1024px widths)
- [ ] Navigation sidebar shows "A/B Testing" and "Ground Truth"
- [ ] No critical errors in browser console
- [ ] Network requests (200 OK) for all API calls

## 📋 Next Phase (Phase Three)

After manual QA is signed off:
1. **Environment Review** - Check `.env` and Docker configs
2. **Production Build** - Test frontend production build
3. **Docker/Grafana Setup** - Production monitoring stack
4. **Deployment Guide** - Update `docs/PRODUCTION_DEPLOYMENT.md` if needed
5. **Optional**: Clean up unused TypeScript types and imports

**Phase Three Week 6 Tasks:**
- Distributed rate limiting (Redis-backed)
- Prometheus metrics export
- Health check endpoints (K8s-ready)
- Final security audit and secrets rotation

## ℹ️ Notes

**Remaining Lint Issues (49 errors, all non-blocking):**
- Unused TypeScript type imports (from API contracts)
- Unused Lucide icons (kept for future use)
- Unused variables in WIP features

**Status:** These don't affect functionality and can be cleaned up in a dedicated refactoring session after Phase Two is fully validated.

**Reference:** CROSS_SOURCE_CORROBORATION_UI_COMPLETION_REPORT.md notes that lint flags unused imports but they're non-blocking.
