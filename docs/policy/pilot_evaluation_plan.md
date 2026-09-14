# Pilot evaluation plan (short)

Purpose: decide whether the companion guarantee with diversity optimisation serves students better than the current seating procedure, and whether the default penalty for extra listed companions should change. No student feedback exists yet; the synthetic study cannot supply it. Nothing below is a claim about outcomes.

## Questions

1. Comfortable companionship. Do students who submitted a list report that lunch felt comfortable, and does the reported comfort differ between rotations with exactly one listed companion and rotations with two or more?
2. Meaningful new interactions. Do students report conversations with tablemates they did not know before, and how does that compare with the previous procedure? "Met" in the traces means "seated together"; only students can say whether an interaction was meaningful.
3. Poorly served students. Which students end the pilot with few distinct peers, with the same listed companion in most rotations, or with waived obligations, and what do they and their teachers say about it?

## Design

- Duration: at least eight rotations (four mixed, four same-grade), so that repeat effects appear.
- Groups: the year group as a whole under the proposed procedure; the previous procedure's rules must be written down before the pilot so that a comparison is possible. If those rules are not available, the comparison is against the matched random baseline computed by the software, and this limitation is stated.
- Weight variants: a pilot can run two rotations at the default extra-companion penalty and two at a lower penalty (for example 0.5), in either order, and compare the responses to question 1. This does not identify a socially optimal weight; it shows whether students notice the difference.
- Consent and notice: the draft submission notice, adapted and approved by the school, must go out before lists are collected.

## Measures

From the software, per student and per rotation, computed by `sim/metrics.py` and recorded in every trace:

- at-least-one and exactly-one coverage among obligated students (separately from participation and admission counts);
- extra listed companions;
- distinct peers, including the minimum and the 5th and 10th percentiles;
- the maximum number of rotations spent with the same listed peer, and the share of obligated rotations spent with the most frequent listed peer;
- pending requests, approved exceptions, voluntary nonsubmission, absences and waived obligations per rotation;
- release statuses (optimized, incumbent, fallback) and any unscheduled outcome.

From students and staff (to be designed with the school; not part of this repository):

- a short questionnaire after selected rotations covering comfort, new conversations, and whether the student wanted to change their list;
- a supervising-teacher observation of tables that appear in the recurring-group diagnostics, without naming the diagnostics as evidence of anything;
- an interview with each student in the lowest decile of distinct peers or the highest decile of same-companion repeats, and with any student whose obligation was waived.

## Analysis and reporting

- Report participation and admission first, then guarantee satisfaction among the obligated, then the distributions above, then questionnaire results.
- Do not treat an unlisted tablemate as unfamiliar, and do not treat exactly-one coverage as wellbeing.
- Report the weight comparison as observed differences with the pilot's sample size, not as an optimum.
- Report privacy: how charts were distributed, whether any student raised a concern about deductions from charts, and the co-seating exposure statistic for the pilot charts.

## Stop rules

Stop the pilot and revert to the previous procedure if a rotation cannot be scheduled and no decision can be reached in time, if a student's stated distress is linked to a forced table or a deduced list entry, or if the school cannot maintain the review workflow.
