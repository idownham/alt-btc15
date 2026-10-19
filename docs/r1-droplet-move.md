# R1 recorder: move from the laptop to the `alt-arb` droplet — plan

*Written 2026-10-18 (CDT). Owner decision: HQ `docs/decisions.md` 2026-10-15 and this project's `docs/decisions.md`
2026-10-18. **Not deployed yet.** Deployment waits until Ian confirms the droplet resize is finished.*

## Why
The laptop sleeps when its lid closes and after 1 idle minute. Book coverage per Chicago day was Oct 15 24%, Oct 16 53%,
Oct 17 3% and Oct 18 39% (journal 2026-10-15 → 10-18). Most windows since Oct 14 evening will fail the ≥ 95% coverage
rule. The droplet doesn't sleep.

## Target
- Droplet `alt-arb` (sfo2, Ubuntu 24.04), after the resize to Basic 1 vCPU / 2 GB / 50 GB (~$12/mo). Osprey's scanner
  already runs there as user `altarb` from `/opt/alt-arb`. **Nothing of Osprey's is touched.**
- Own Linux user `altbtc15`, own folder `/opt/alt-btc15` (git clone of `idownham/alt-btc15`, own `.venv`), and own
  systemd unit `alt-btc15-recorder.service` (`Restart=always`, `KillSignal=SIGTERM`, since the recorder stops cleanly on SIGTERM).
- Read-only, **no keys and no `.env` secrets**. Kalshi public REST and Coinbase public ticker only. **No Polymarket calls**
  (Osprey only, per-IP limit). The 10 s back-off on 429 stays, because Osprey and Coin Toss share this IP.
- The clock is set by NTP (`timedatectl` must show synchronized), since snapshot times come from the host clock.

## Disk sizing (measured on the laptop DB, 2026-10-18)
| Part | Size | Rate |
|---|---|---|
| Trade tape + 2 indexes | 4.19 GB for Oct 14 20:00 → Oct 19 03:24 UTC (4.3 days) | **≈ 1.0 GB/day**, whatever the book coverage (the tape is backfilled after gaps) |
| Book snapshots + index | 68 MB for 118k snapshots (~580 B each) | ≈ 50 MB/day at full coverage |
| BTC, events, gaps, windows | < 10 MB | negligible |
The first-day estimate of 1.4 GB/day came from a busy afternoon. Plan for **1.0–1.5 GB/day**.

**R1 range plus extension.** The droplet's DB starts empty on move day, so only server days count against its disk.
At 96 windows a day, 900 usable windows need ≥ 9.4 days of near-full coverage. If the move is around Oct 20, the end-date
extension in the pre-registration is likely to land around **Oct 30 – Nov 3**. That's about 11–15 server days ≈
**11–23 GB**. Osprey used ~4 GB of the old 25 GB disk, so 50 GB leaves ≥ 20 GB of headroom even at the high end.
A fresh disk check is part of the deploy.
**Guard:** the deploy adds a daily check, and if free space falls under 5 GB it is raised in a session (no automatic deletion).

## Bringing the data together
1. **Overlap.** Start the droplet recorder while the laptop agent keeps running. Both record for at least one full window
   (~30 min). Check on the droplet: 60 snapshots/min, tape current, 0 errors, 0 rate-limit pauses.
2. **Cutover.** Stop and unload the laptop agent (`com.idownham.slot.recorder`). The cutover time *T* is the start of the first
   window the droplet recorded in full. Log *T*, the overlap and any gap in `decisions.md` and `journal.md`.
3. **Analysis copy (after 2026-10-28 05:00 UTC, or the amended end date).** Copy the droplet DB to the laptop (`sqlite3 .backup`
   on the droplet, then `scp`). A merge script (to be written and tested on synthetic data before the end date) builds
   one analysis DB:
   - `books` and `btc`: laptop rows before *T*, droplet rows from *T*. No mixing of hosts within a window.
   - `trades`: the union, deduplicated on `trade_id`. During the overlap the two tapes must match on `trade_id`, which is a
     consistency check written into the merge output.
   - `windows`: the union. A result recorded by either host fills a missing one.
   - `gaps` and `events`: kept per host, with a `host` column added, so gap accounting stays honest.
   The pre-registration's rules are unchanged. They are applied to the merged DB exactly as written.
4. The laptop DB is kept as is (evidence). Nothing is deleted.

## Deploy steps (when Ian confirms the resize)
1. Check the resize: `df -h /`, `free -m`, Osprey's service still active (read-only checks).
2. Create user `altbtc15` and `/opt/alt-btc15`, clone the repo, create `.venv`, `pip install -e .`, and run the tests.
3. Install the systemd unit (`scripts/alt-btc15-recorder.service`, to be added) with `--db /opt/alt-btc15/data/recorder/book.sqlite`.
4. Start it, then follow steps 1–2 of "Bringing the data together".
5. Update CLAUDE.md's infrastructure section, the README and the journal, and tell HQ (HQ's CLAUDE.md "Running services").
