# Draft data-handling policy for the companion-guarantee seating system

Status: draft for school review. Nothing here has been adopted. The repository contains only synthetic students; this policy describes what a real deployment would need.

## 1. Data the system holds

| Data | Sensitivity | Who needs it |
|---|---|---|
| Roster (identifier, grade, attendance per rotation) | personal | scheduling staff |
| Submitted lists and their submission state (accepted, pending review, approved exception, voluntary nonsubmission) | private preference data about the submitter and about the people named | scheduling staff, the reviewing administrator |
| Review decisions, notes, obligation waivers, staff constraints (prohibited pairs, placement restrictions) | sensitive administrative information | the reviewing administrator; scheduling staff |
| Screening diagnostics (candidate groups, certificates, recurring co-seated groups) | sensitive; can be misread as accusations | the reviewing administrator only |
| Released seating charts | operational; reveal preferences indirectly | students, supervising staff |
| Solver internals (stage snapshots, costs, fallback cache, statuses) | technical | scheduling staff |

The trace files written by `sim/` contain every row of this table. A trace file is therefore a staff record, never a student-facing document.

## 2. What may be distributed to students

Only the output of `sim/student_export.py`: the table assignment of one rotation, with identifiers and grades, plus the short notice about confidentiality limits. The export contains no lists, no anchors, no review information, no diagnostics, no solver internals, and no random comparison charts. A test (`tests/test_student_export.py`) checks that these fields are absent.

Default distribution is current-only: one rotation at a time, produced when that rotation is released. Distributing the year's history is an explicit option (`--history`) and should require a policy decision, because each additional chart narrows the set of lists consistent with the observations.

## 3. Confidentiality limits (what hiding does not achieve)

The following statements are supported by the analysis in the manuscript and by the privacy checks in the repository. They are limits, not guarantees.

- Hiding the lists does not hide the preferences. Under a stated public cap on list length, a fraction of directed list entries is logically forced by the published charts of a year; in the synthetic reference this is roughly a third. Every entry deduced this way is correct.
- Limiting the archive reduces logical forcing. With a public cap of eight names, no individual entry is logically forced from any window of eight or fewer consecutive charts, because a list can always be chosen to avoid a given name. This holds only under the stated observer model.
- Removing the public cap removes logical forcing but not statistical inference. The most frequent tablemate of an obligated student is a listed peer for the large majority of students under the proposed system, versus a few percent under random seating. An observer who counts co-seatings learns list entries with high confidence from any archive, with or without a cap.
- An observer who copies each chart as it is released is not bound by the school's retention policy.

Therefore: publishing charts is a disclosure of preference information. The school should decide who may see charts on that basis, and the submission notice should say so.

## 4. Access control and infrastructure

The demonstrator is a static GitHub Pages site with synthetic data. It has no authentication, no audience restriction, and no per-student views. A static page cannot implement access control; hiding an element in the browser is cosmetic and must not be described as protection.

The optional shared portrait preview reads a directory folder selected by the presenter on that device. It does not add photographs to the published site or upload them. The browser holds normalized portrait images for that tab, and clearing the preview or leaving the page revokes them. These portraits illustrate synthetic slots; they must not be interpreted as real student preferences, assignments, or diagnostic findings. All four tabs use the same synthetic-ID-to-portrait mapping. Individual lists and coalition behavior remain simulated examples, and the page is labeled Simulation. No real names or requests are read into the simulation. Clearing the preview removes portraits from visible and hidden views. The website's runtime libraries are served locally with its code.

Distributing real charts privately requires infrastructure that this project does not provide:

- an authenticated channel that the school already operates (a learning-management system, a student information system, or a school e-mail or messaging account), or paper distribution under supervision;
- a place to store trace files and review records that is restricted to scheduling staff, with backups and retention rules;
- a named administrator responsible for review decisions, waivers, and requests from students to withdraw or change a list.

Until such infrastructure exists, the school should not publish real charts on the demonstrator site or any other unrestricted web page.

## 5. Retention and deletion

- Submitted lists, review decisions and traces are kept for the school year and deleted at its end, unless the school's records policy says otherwise.
- The fallback cache and stage snapshots are operational data and can be deleted with the trace.
- Public demonstration data must remain synthetic. The repository test suite checks that the site data uses generated identifiers only; no real name, photo, e-mail, or identifiable derivative may be added to the public repository.

## 6. Use of diagnostics

Screening certificates and recurring-group reports identify structures in the submitted lists and in the released charts. They are inputs to a conversation, not findings of intent. A forced group can result from sincere, concentrated friendships or from small eligible pools. Staff should not label a student or group as dishonest on the basis of these reports.

## 7. Open decisions for the school

- Whether charts are distributed at all beyond the supervising staff, and through which channel.
- Whether the year's history is ever distributed.
- Who reviews pending requests and conflicts, and how quickly.
- Whether a public list-size cap is announced (it changes what can be deduced logically, but not statistically).
- Whether the penalty for extra listed companions is left at its default or changed after a pilot.
