import { useEffect, useState } from "react";
import { fetchBenchmarkOutcome } from "../api";
import type { BenchmarkOutcomeResponse } from "../types";

interface Props {
  onReturnToReplay: () => void;
}

export default function BenchmarkOutcomePanel({ onReturnToReplay }: Props) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<BenchmarkOutcomeResponse | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    fetchBenchmarkOutcome(controller.signal)
      .then((res) => {
        if (controller.signal.aborted) return;
        setData(res);
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        setError(err instanceof Error ? err.message : String(err));
        setLoading(false);
      });
    return () => controller.abort();
  }, []);

  const ex = data?.verified_example;
  const summary = data?.diagnostic_summary;

  return (
    <section
      id="panel-benchmark-outcome"
      className="benchmark-outcome-panel app-panel"
      aria-label="Benchmark answers evaluation"
      tabIndex={-1}
    >
      <header className="benchmark-outcome-header">
        <p className="benchmark-outcome-kicker">Evaluation view</p>
        <h2 className="benchmark-outcome-title">
          Benchmark answers — retrospective evaluation
        </h2>
        <p className="benchmark-outcome-disclaimer" role="note">
          Labels shown here were not available during investigation. Return to
          replay to clear ground-truth overlays.
        </p>
        <button type="button" className="btn" onClick={onReturnToReplay}>
          Return to investigation replay
        </button>
      </header>

      {loading && (
        <p className="channel-note" role="status">
          Loading benchmark outcome…
        </p>
      )}
      {error && (
        <p className="state-copy" role="alert">
          {error}
        </p>
      )}

      {data && ex && summary && (
        <div className="benchmark-outcome-body">
          <section className="benchmark-outcome-section" aria-labelledby="bo-example">
            <h3 id="bo-example">Verified example — 24 Jan abrupt (p827)</h3>
            <p className="channel-note">
              One verified case from the frozen diagnostic record — not a claim
              of overall detection accuracy.
            </p>
            <dl className="benchmark-outcome-dl">
              <div className="detail-row">
                <dt>Frozen notification time</dt>
                <dd>{ex.frozen_notification_time}</dd>
              </div>
              <div className="detail-row">
                <dt>Official labeled onset</dt>
                <dd>{ex.official_labeled_onset}</dd>
              </div>
              <div className="detail-row">
                <dt>Delay (five-minute resolution)</dt>
                <dd>
                  {ex.delay_five_minute_steps} five-minute step
                  {ex.delay_five_minute_steps === 1 ? "" : "s"} ({ex.delay_hours}{" "}
                  h) — same five-minute timestamp
                </dd>
              </div>
              <div className="detail-row">
                <dt>Actual labeled pipe</dt>
                <dd>
                  <code>{ex.pipe_id}</code>
                  <span className="truth-pill">{ex.truth_map_label}</span>
                </dd>
              </div>
            </dl>
          </section>

          <details className="method-m-tech" open={false}>
            <summary>Method and evaluation</summary>
            <p className="channel-note">
              Delay note: {ex.delay_note} {ex.contributing_sensor_note}
            </p>
            <h4 className="details-section">Complete diagnostic evaluation (2019)</h4>
            <ul className="benchmark-outcome-list">
              <li>
                Abrupt:{" "}
                <strong>
                  {summary.abrupt_recall_excluding_development_example_p523}
                </strong>{" "}
                excluding development example;{" "}
                <strong>{summary.abrupt_recall_inclusive}</strong> inclusive.
              </li>
              <li>
                Incipient: <strong>{summary.incipient_recall}</strong>.
              </li>
              <li>
                Unmatched notifications:{" "}
                <strong>{summary.unmatched_notifications_2019}</strong>.
              </li>
              <li>{data.year_examined_note}</li>
              <li>{data.localization_note}</li>
            </ul>
            <p className="channel-note">
              Artifact <code>{data.artifact_id}</code> v{data.version} · sha256{" "}
              <code>{data.artifact_sha256.slice(0, 16)}…</code>
            </p>
            <p className="channel-note">
              Official onset verified against BattLeDIM Zenodo 4017659{" "}
              <code>2019_Leakages.csv</code> (first non-zero discharge on p827).
              Frozen notify hash{" "}
              <code>
                {String(
                  (data.provenance as { frozen_notifications?: { sha256?: string } })
                    ?.frozen_notifications?.sha256 ?? "—",
                ).slice(0, 16)}
                …
              </code>
              . Matching protocol: six-hour one-to-one abrupt credit on frozen
              five-minute Method M — outcomes unchanged from the research record.
            </p>
            <p className="channel-note">
              Evaluation labels are not loaded into detector inputs, warning APIs,
              timeline responses, saved investigations, or printed briefs.
            </p>
          </details>
        </div>
      )}
    </section>
  );
}
