# Sasha 362 — every S2 tab is reachable at phone width

**Found (Tyler's dry run, step 2, iPhone Safari, /s2):** the top tab row (Sasha · Trip · Activity · My Keep · Group) ran off the right edge and couldn't be scrolled. The Group tab was unreachable on a phone.

Measured on production at 375 px: "My Keep" sat at x=334 and "Group" at x=408, and the nav's `overflow-x` was `visible`.

**Fix (one source):** S2's tabs are now ONE list (`S2_TABS` in `app/s2/S2App.tsx`), drawn by ONE component (`app/s2/TabBar.tsx`).
- Each tab keeps its size and never wraps.
- The bar scrolls sideways when the tabs don't fit, and is right-aligned when they do. It uses `margin-left: auto`, never `flex-end`, because `flex-end` with overflow cuts the start off where it can't be scrolled to.
- The chosen tab is scrolled into view.

**Tests:**
- `frontend/scripts/s2-tabs-362.test.mjs` (in `npm test`): one bar, one list holding every tab, and a bar that scrolls without shrinking or wrapping its tabs.
- The live check at 375 px (iPhone viewport) on production c1c826cf: the bar is 266 px wide holding 372 px of tabs, `overflow-x: auto`. "My Keep" and "Group" come into view when the bar scrolls; tapping Group opens it. Nothing unreachable.

The frontend-only push left the backend alone (Railway skipped), so nothing restarted during the dry run.
