# DeskCheck guided workspace — design QA

Date: 2026-10-28. Scope: actual native desktop implementation, not an HTML mock.

## Evidence and normalization

- Source visual truth: `docs/design/approved-concept.png`, user-approved combined
  Preview Studio layout with a guided flow and understandable failure results.
- Implementation: `docs/design/workspace-failure.png`; compact window:
  `docs/design/workspace-small.png`.
- Source pixels: 1487 × 1058, normalized to its requested 1440 × 1024 viewport.
  Implementation client pixels: 1440 × 1024 and 1050 × 680, native density 1.
  This is a Tk application: CSS viewport/deviceScaleFactor are not applicable.
- State: Windows synthetic sample; an intentional bad-save mode returns
  `Saved: Draft note` while the check expects `Saved: Synthetic acceptance check`.
  This is an actual failed assertion with an actual app-only capture, not a
  hard-coded PASS/FAIL screen. Expected/actual reveal was explicitly enabled
  only in the synthetic QA harness. Normal UI requires user confirmation.
- Same-input full comparison: `docs/design/comparison-full.png`. Focused
  inspector, header and footer comparisons are alongside it in `docs/design/`.
- Native captures obtained inside the isolated QA application's own process.
  Because Windows/Tk doesn't paint off-monitor child controls, the large
  fixed-size view is tiled from unchanged client pixels at different window
  positions. No desktop pixels, browser pages, or other user windows are included.
  `test/guided_demo.py` and `test/compare_design.py` reproduce this evidence.
- Independent user-side inspection used Windows Computer Use to select the
  actual DeskCheck window, load the sample, confirm capture, observe progress,
  and verify that the sample closed. An occluding unrelated browser capture
  was rejected and not saved as evidence.

## Comparison history and fixes

1. [P1, fixed] Tk integer subsampling discarded text detail in a small preview.
   Replaced it with bounded PNG validation plus Pillow LANCZOS resizing. The
   corrected native app capture is readable and can open at full size.
2. [P1, fixed] Repeated sample choices pushed Continue below the laptop fold.
   Selected-app setup now replaces those choices, and Next is in the persistent
   bottom toolbar. Navigation, Stop and evidence access remain outside the
   scrolling editor.
3. [P1, fixed] Listing every low-level action before the failure hid the reason
   for failure. A compact selectable action list and selected-step details
   replace the long stack. Small windows put the explanation first.
4. [P2, fixed] The initial render underemphasized headings and gave the inspector
   too much of the workspace. Main title is now 40px, section headings 22px,
   body 16px and secondary text 15px; the preview/inspector uses a 3:2 grid.
5. [P2, fixed] Expected/actual values lacked scannable differentiation. Revealed
   values now use contrasting grouped surfaces, readable bold text, and a red
   mismatch value. The sample was updated to reproduce the concept's actual
   bad-save behavior rather than merely giving a valid app a wrong expectation.
6. [P2, fixed] Tall legacy progress chrome competed with the content. Progress
   is now a thin strip and the final outcome has an explicit readable status.
7. [P2, fixed] Packaged laptop-size inspection found an overflowing Remove
   button and an action list that pushed editable fields below the fold.
   The four controls now share an equal-width grid. Compact windows use a
   step dropdown instead of a tall tree so the selected fields get priority.

After these fixes the implementation and reference were placed together again
in full and focused comparisons. No actionable P0/P1/P2 finding remains in this
guided native-desktop scope. This is design acceptance, not a claim of pixel-
identical custom web styling or a commercial release certification.

## Required fidelity surfaces

- **Typography:** native Segoe UI, 40/22/16/15px hierarchy. Long headings and
  inspector copy wrap; input labels are visible. Source's smoother Image Gen
  typography is not a font asset. Native antialiasing differences are expected.
- **Spacing/layout:** navy saved-check navigation, bright main surface, prominent
  preview, right inspector, horizontal four-stage guide and persistent footer.
  Both tested viewports keep the core controls on screen; long details scroll.
  Full-size preview is available rather than enlarging a low-resolution image.
- **Colors/tokens:** `#183247` navigation, `#173247` ink, `#008b89` primary,
  `#edf4f8` preview, restrained red errors; state has text and icons, not color alone.
- **Images/assets:** real bounded app capture, not a fake image of the app;
  pinned MIT Feather 4.29.2 PNG icons shipped offline with their license.
  No remote fonts, generated people, placeholder app imagery or handcrafted
  icon substitutes. Source's fake app-window bezel is intentionally not added
  to a client-area capture. Product name stays DeskCheck as agreed.
- **Copy:** Choose app → Add actions → Expected result → Review results.
  Only real saved checks populate the sidebar, not the mock's invented checks.
  Eight actual actions, including target clicks and capture assertions, are
  reported truthfully instead of the concept's four simplified logical stages.
  Simulated evidence is prominently labelled, failures never claim success.

## Functionality/accessibility verification

The local 80-test suite covers save/reopen/version preservation, editing and
invalidation of old results, add/reorder/remove, stage navigation, coordinate
mapping, mock capture versus test distinction, failure captures, private text
redaction, running/cancellation, validation recovery and the engine/MCP safety
suite. Real Windows fixture and packaged native/MCP checks are separate release
gates. Mouse and keyboard focus remain native; Ctrl+S saves, Tab reaches controls,
Escape closes full-size preview. No browser console exists for this native app;
source QA emitted no unhandled Tk callback errors in the final captures.

## Follow-up polish (P3)

- Native Treeview/Listbox selection and outline icons are less ornamental than
  the concept's fully custom rows and filled circular badges.
- The preview intentionally shows the whole app client area; screenshot text
  can be small at 1050px, with a full-size viewer provided.
- Whole actual values are tinted rather than only the differing substring.
- A screen-reader study with users is not claimed; this is functional native
  widget and visual QA, not a formal accessibility conformance certification.

## Implementation checklist

- [x] Chosen visual direction implemented in the real offline product.
- [x] Core setup/edit/run/result workflow works with synthetic evidence.
- [x] Source/actual full and focused comparisons reviewed after fixes.
- [x] Small-window navigation and scrolling retained.
- [x] No external publishing, telemetry, paid API calls or marketing.

final result: passed
