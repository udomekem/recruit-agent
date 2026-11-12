# Hira — Recruitment Dashboard Design Handoff

Prepared 8 November 2026. This package contains the latest Hira recruitment dashboard concept from the conversation. It replaces the earlier Assemble recruitment concept as the reference for this handoff. It is unrelated to the separate ICM workspace methodology discussion.

## Files

- `hira-dashboard.html`: standalone browser preview. Open this file in a browser to inspect the interface and interactions. Its wrapper embeds the design in an iframe.
- `hira-source.html`: readable design source, including scoped CSS, semantic markup, sample data and interaction logic. Use this file as the implementation reference.
- `DESIGN-BRIEF.md`: intent, design specification, interaction behaviour and implementation boundaries.

The preview loads fonts and supporting display resources from the internet. System fonts provide a fallback if web fonts cannot load. Do not expect fully offline rendering of every icon and font. The readable source expects an icon runtime and optional host helpers; the standalone preview supplies its own wrapper. The source is a design fragment, not an independent application entry point.

## Product purpose

Give HR staff a clear place to browse applications, read candidate CVs, record private review notes, and approve or decline applications. All people and records supplied in this design are fictional demonstration data. Decisions affect only the prototype; no candidate communication is sent.

## Visual direction

A minimal editorial workspace with warm neutral surfaces, cobalt accents, confident typography and generous spacing. Candidates and their qualifications are the focal point. Avoid adding decorative charts, artificial matching scores, large dashboard cards or a permanent sidebar.

Use the supplied source as visual truth. Keep the compact Hira brand header, company breadcrumb, reviewer identity, headline, inline application counts, status filters, role selector, candidate queue and spacious review panel.

### Colour tokens

| Purpose | Light | Dark |
|---|---|---|
| Canvas | `#f7f7f4` | `#16191c` |
| Surface | `#ffffff` | `#202429` |
| Primary text | `#202529` | `#f1f2ef` |
| Secondary text | `#69716f` | `#adb5b4` |
| Divider | `#e5e7e2` | `#363c40` |
| Subtle surface | `#f0f2ee` | `#292f32` |
| Accent text | `#354fd5` | `#a4b4ff` |
| Selected candidate | `#eef1ff` | `#29334f` |
| Approved text | `#32725b` | `#8ed2b1` |
| Approved surface | `#e9f5ee` | `#213d32` |
| Declined text | `#a14949` | `#ecaaaa` |

Primary action buttons use cobalt `#354fd5` with white text in both themes. Follow the active light/dark appearance. Status is always communicated with text as well as colour.

### Typography and geometry

- DM Sans for interface and CV text; Manrope for branding, headings and numerical summaries.
- Desktop page headline: 35px, weight 600, tight letter spacing. Candidate name: 27px, weight 600.
- Main CV summary: 14px with generous 1.85 line height. Preserve legibility when translating to a production design system.
- Outer shell radius: 18px; workbench: 12px; controls: approximately 7–8px.
- Desktop content inset: approximately 29px. Review-panel inset: approximately 27px.
- At wide desktop sizes, candidate queue is 280px and the review panel takes the remaining width. At intermediate widths the queue becomes 235px.
- At 680px and below, use separate list and review screens. Do not squeeze the queue and CV beside each other.
- Keep native keyboard focus visible. On touch devices, controls should have effective targets of at least 44px.

## Screen and interaction specification

1. **Application overview:** live counts for total, to review and approved applications. Counts refer to the entire sample dataset; the queue separately shows the number matching its current filters.
2. **Filters:** All candidates, To review, Approved and Declined; an open-role selector; and a name search. Filters combine. An empty result must show an appropriate empty state without retaining an unrelated candidate.
3. **Candidate queue:** initials avatar, name, role, status and application recency. A selected row has a subtle cobalt surface and left accent. Selecting a candidate updates the complete review panel.
4. **Review header:** candidate name, role, location, experience, status, application position and previous/next controls.
5. **Résumé tab:** document label, supplied summary, work history, skills and education. This is a readable fictional CV preview; a live PDF viewer and real file upload are not implemented.
6. **Focus view:** expands the review area on desktop. Mobile must still show a usable list or review screen if focus mode was previously enabled.
7. **Review notes:** candidate-specific private notes. The prototype stores interaction state through its host bridge; production will require authorised persistence.
8. **Activity:** sample application history plus decisions made during the prototype session.
9. **Approve:** updates status, counts and activity; exposes an Undo action. It does not send email, create an employment offer or onboard a worker.
10. **Decline:** opens a confirmation form requiring a job-related reason, with optional context. Submission updates status and activity and can be undone. Missing reasons show validation feedback.
11. **Mobile:** initially show the candidate list. Selecting a person opens their full-width review. An All candidates back control returns to the list.

## Suggested implementation structure

Components: workspace header, application summary, status filters, role filter, candidate search, candidate list/row, review header, résumé panel, review notes, activity timeline, decision controls, decline form and feedback message.

Keep candidate records separate from review state. Maintain selected candidate, filters, active tab, focus mode, notes, decisions and activity. Keep all names, notes, reasons and other user-controlled content safely rendered as text. The supplied prototype uses fixed sample data; do not extend its HTML interpolation to untrusted API records without escaping or a safe rendering framework.

The original inline version uses optional `window.openai` state helpers and an optional design-control helper. These are demonstration infrastructure. Use the target application's state management and persistence when implementing the actual product.

## Scope and checks

This is a UI design and interactive prototype, not production recruitment software. Authentication, roles, backend storage, secure CV upload, candidate consent/retention, real notifications, and server-side audit history still require separate implementation decisions.

Before accepting a production implementation, verify candidate switching, combined filters, empty results, all tabs, candidate-specific notes, approve/undo, decline validation/undo, desktop focus mode, mobile back navigation, keyboard access, and responsive layouts at 1024px, 736px, 390px and 320px. Test desktop-to-mobile resizing with focus enabled and restoration of an empty filter state.

The source passed JavaScript syntax and duplicate-ID checks. A source review found and corrected the mobile focus and empty-selection restoration cases. Live browser screenshot verification was unavailable during the design session; do not describe visual or end-to-end QA as completed.

## Ready-to-use request for Claude

Implement the Hira recruitment dashboard from the attached design package. Start by inspecting hira-dashboard.html and reading hira-source.html and DESIGN-BRIEF.md. Preserve the visual direction, typography, palette, spacing, candidate queue, readable CV panel, status filters, notes, activity, approve/decline actions and responsive list-to-review flow. Adapt the implementation to the existing project's framework and conventions. Begin with the fictional data supplied unless a backend is already available. Identify backend requirements separately and do not claim live hiring or notification functionality when only the prototype is implemented. Verify the interaction and responsive checks listed in the brief, and report what was actually tested.
