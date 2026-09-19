# 3-Minute Video Script — Track Access Scheduler (NebulaX PS1)

**Total target: ~3:00.** Times are cumulative. Narration is written to be read
aloud at a natural pace (~150 words/min). Screen directions are in _italics_.

> Tip: record the screen demo first (with the live Google Cloud app), then lay
> the voiceover on top. Use the **bundled sample instance** so it runs instantly.

---

## SCENE 1 — The 2 AM problem (0:00 – 0:30)

_On screen: title card "Track Access Scheduler", then a dark control-room / night
railway image, then the live app URL._

**Narration:**
> "It's 2 AM. The last train has gone, the first is a few hours away — and that
> tiny night window is the only time anyone can work on the tracks. Renewals,
> construction, maintenance — every contractor wants the same tunnels and
> platforms on the same nights. Today a works controller untangles this by hand:
> safety buffers, live-rail power cuts, who's allowed how many nights. It takes
> hours, and one disruption means starting over. We built a tool that does it in
> one click — and proves the plan is safe."

---

## SCENE 2 — What it does, at a glance (0:30 – 1:00)

_On screen: the live app landing page. Tick "Use bundled sample instance",
click "Run scheduler". Land on the Compare A/B/C dashboard._

**Narration:**
> "This is a decision-support tool for access planners. Upload the demand book —
> the eight instance files describing the network and the work — and it produces
> a complete possession schedule: which job runs, which week, on which track.
> It's built for the dual-line network, Line Alpha and Line Beta, including the
> shared interchange hubs. And it's not advisory — every plan is checked against
> the same hard safety rules the judges validate: exclusion buffers, live-rail
> mirroring, capacity limits, weekly caps."

---

## SCENE 3 — Three strategies, compared (1:00 – 1:35)

_On screen: point at the three scenario cards and the penalty bar chart._

**Narration:**
> "There's never enough track time, so the tool offers three planning strategies.
> Scenario A holds capacity rigid and lets a few low-priority jobs slip.
> Scenario B hits every deadline exactly and pays with extra work-nights.
> Scenario C balances the two. The comparison dashboard shows the trade-off
> instantly — here, A costs only a small priority-weighted delay, while B and C
> spend a handful of extra access-nights for zero overrun. All three are
> feasible, with zero safety violations. The controller picks the policy that
> fits the night."

---

## SCENE 4 — See it and understand it (1:35 – 2:25)

_On screen: open Scenario A tab. Scroll the Gantt chart, then the topology map
(drag the week slider), then the explainability section._

**Narration:**
> "Open any scenario and you can see the whole plan. The Gantt chart lays out
> every possession over time, colour-coded by line, so you can spot conflicts at
> a glance. The network map shows exactly which sectors are worked each week —
> drag the slider through the horizon — with live-rail closures highlighted in
> red, including the way they mirror onto the opposite track and cross between
> lines at the hubs.
>
> And crucially, it explains itself. It tells you the co-sharing efficiency — how
> much work was packed into shared possessions — flags the capacity hotspots,
> like the single-track interchange tunnel, and says in plain English *why* a
> contract was delayed: lower-priority work slips first, because the tool always
> protects Priority-1 programmes. That's the difference between a schedule and a
> schedule you can trust."

---

## SCENE 5 — Built on Google Cloud, ready to use (2:25 – 3:00)

_On screen: show the `.run.app` URL in the address bar; click "Download all 3
(zip)"; show the CSV files briefly._

**Narration:**
> "The whole thing runs live on Google Cloud Run — scalable, and open for the
> judges to upload their own hidden test instance and watch it solve in real
> time. When you're happy, download the submission files for every scenario in
> one click. From a night-by-night planning nightmare to a provably-safe
> possession schedule — in seconds, not hours. That's the Track Access
> Scheduler. Thanks for watching."

---

## Shot list / checklist

- [ ] Title card (app name + your team name)
- [ ] Landing page → tick sample → Run scheduler
- [ ] Compare A/B/C dashboard (cards + bar chart)
- [ ] Scenario A: Gantt chart scroll
- [ ] Topology map: drag the week slider (show a Live week in red if possible)
- [ ] Explainability section (co-share %, "why delayed", hotspots table)
- [ ] Address bar showing the `*.run.app` Google Cloud URL
- [ ] Download button → the 3 CSVs
- [ ] End card (GitLab repo URL + live app URL)

## Timing notes

- If you run long, trim Scene 2 — the landing-page explanation can be shortened.
- Keep Scene 4 (visuals + explainability) the longest; it's the strongest part
  and what the judging rubric rewards ("trade-offs explained, not just produced").
- Speak a touch slower than feels natural on camera; 3 minutes is tight.
