import { useId, useState } from "react";
import {
  BRIEF_CAUSE_LABEL,
  BRIEF_CONTEXT_CHANNELS,
  BRIEF_PRODUCT_LABEL,
  findObs,
  fmtNum,
  fmtTs,
  freshnessLabel,
  pressureDeltaLine,
  warningStatusLine,
} from "../brief";
import type { PressureComparison } from "../investigation";
import { shareUrlForId, type SavedInvestigation } from "../investigations";
import type { MethodMWarningResponse, SnapshotObservation } from "../types";

interface Props {
  cursor: string | null;
  windowStart: string | null;
  windowEnd: string | null;
  selectedSensorId: string | null;
  observations: SnapshotObservation[];
  snapshotMatched: boolean;
  snapshotLoading: boolean;
  pressureComparison: PressureComparison | null;
  seriesMatched: boolean;
  seriesLoading: boolean;
  warning: MethodMWarningResponse | null;
  warningLoading: boolean;
  savedInvestigation: SavedInvestigation | null;
}

function ChannelLine({
  title,
  detail,
  unit,
  obs,
  loading,
}: {
  title: string;
  detail: string;
  unit: string;
  obs: SnapshotObservation | null;
  loading: boolean;
}) {
  if (loading) {
    return (
      <li>
        <strong>{title}</strong> ({unit}): loading…
        <span className="brief-muted"> — {detail}</span>
      </li>
    );
  }
  return (
    <li>
      <strong>{title}</strong> ({unit}):{" "}
      {obs?.value === null || obs?.value === undefined ? "—" : fmtNum(obs.value)}{" "}
      · {freshnessLabel(obs?.status ?? "missing")}
      {obs?.observation_ts ? ` · observed ${fmtTs(String(obs.observation_ts))}` : ""}
      <span className="brief-muted"> — {detail}</span>
    </li>
  );
}

export default function InvestigationBriefPanel({
  cursor,
  windowStart,
  windowEnd,
  selectedSensorId,
  observations,
  snapshotMatched,
  snapshotLoading,
  pressureComparison,
  seriesMatched,
  seriesLoading,
  warning,
  warningLoading,
  savedInvestigation,
}: Props) {
  const titleId = useId();
  const [open, setOpen] = useState(false);
  const [sessionNote, setSessionNote] = useState("");

  const canPrepare = Boolean(cursor && windowStart && windowEnd);
  const selectedObs =
    selectedSensorId && snapshotMatched
      ? findObs(observations, selectedSensorId)
      : null;
  const shareUrl =
    savedInvestigation != null ? shareUrlForId(savedInvestigation.id) : null;
  const savedNote = savedInvestigation?.note?.trim() || null;
  const displayNote = sessionNote.trim() || savedNote;

  const onPrint = () => {
    if (!open) setOpen(true);
    // Allow React to paint the brief before the print dialog.
    window.setTimeout(() => window.print(), 50);
  };

  return (
    <section
      id="panel-brief"
      className="investigation-brief-panel app-panel"
      aria-labelledby={titleId}
      tabIndex={-1}
    >
      <div className="investigation-brief-toolbar no-print">
        <div>
          <h2 id={titleId} className="investigation-brief-title">
            Investigation brief
          </h2>
          <p className="channel-note">
            Assemble a printable summary from the current cursor-matched evidence.
            Does not create a saved investigation.
          </p>
        </div>
        <div className="investigation-brief-actions">
          <button
            type="button"
            className="btn btn-accent"
            disabled={!canPrepare}
            aria-expanded={open}
            onClick={() => setOpen((v) => !v)}
          >
            {open ? "Hide brief preview" : "Prepare investigation brief"}
          </button>
          <button
            type="button"
            className="btn"
            disabled={!canPrepare || !open}
            onClick={onPrint}
          >
            Print / Save as PDF
          </button>
        </div>
      </div>

      {!canPrepare && (
        <p className="channel-note no-print">
          Set a replay cursor and window to prepare a brief.
        </p>
      )}

      {open && canPrepare && (
        <article
          className="investigation-brief-print"
          aria-label="Investigation brief preview"
        >
          <header className="brief-header">
            <p className="brief-kicker">Ripple</p>
            <h3 className="brief-heading">Investigation brief</h3>
            <p className="brief-banner">{BRIEF_PRODUCT_LABEL}</p>
            <p className="brief-banner brief-banner-warn">{BRIEF_CAUSE_LABEL}</p>
          </header>

          <section className="brief-section">
            <h4>Scope</h4>
            <ul className="brief-list">
              <li>
                <strong>Selected sensor:</strong> {selectedSensorId ?? "None selected"}
              </li>
              <li>
                <strong>Benchmark timestamp (cursor):</strong> {fmtTs(cursor)}
              </li>
              <li>
                <strong>Playback window:</strong> {fmtTs(windowStart)} →{" "}
                {fmtTs(windowEnd)}
              </li>
              {savedInvestigation && (
                <li>
                  <strong>Saved title:</strong> {savedInvestigation.title}
                </li>
              )}
            </ul>
          </section>

          <section className="brief-section">
            <h4>Experimental warning</h4>
            {warningLoading || !warning ? (
              <p className="channel-note" role="status">
                {warningLoading
                  ? "Loading experimental warning…"
                  : warningStatusLine(null)}
              </p>
            ) : (
              <ul className="brief-list">
                <li>
                  <strong>Status:</strong> {warningStatusLine(warning)}
                  {warning.warning_active ? (
                    <span className="brief-muted">
                      {" "}
                      · Experimental — not a confirmed leak
                    </span>
                  ) : null}
                </li>
                <li>
                  <strong>Notification time (five-minute stamp):</strong>{" "}
                  {fmtTs(warning.notification?.notify_ts ?? null)}
                </li>
                <li>
                  <strong>Anomaly score / warning threshold:</strong>{" "}
                  {fmtNum(warning.score, 3)} / {fmtNum(warning.threshold, 3)}
                </li>
                <li>
                  <strong>Score stamp ≤ cursor:</strong>{" "}
                  {fmtTs(warning.score_hour ?? null)}
                </li>
                {warning.argmax_sensor_id ? (
                  <li>
                    <strong>Strongest contributing sensor:</strong>{" "}
                    {warning.argmax_sensor_id}
                  </li>
                ) : null}
              </ul>
            )}
            <p className="brief-muted">
              Experimental — not a confirmed leak. Anomaly score is not a
              probability. Method M identity and hashes are in the on-screen
              technical details, not repeated here.
            </p>
          </section>

          <section className="brief-section">
            <h4>Selected pressure</h4>
            {!selectedSensorId && (
              <p className="channel-note">No pressure sensor selected.</p>
            )}
            {selectedSensorId && snapshotLoading && (
              <p className="channel-note">Loading pressure snapshot…</p>
            )}
            {selectedSensorId && !snapshotLoading && (
              <ul className="brief-list">
                <li>
                  <strong>Pressure (m):</strong>{" "}
                  {selectedObs?.value === null || selectedObs?.value === undefined
                    ? "—"
                    : fmtNum(selectedObs.value)}{" "}
                  · {freshnessLabel(selectedObs?.status ?? "missing")}
                  {selectedObs?.observation_ts
                    ? ` · observed ${fmtTs(String(selectedObs.observation_ts))}`
                    : ""}
                </li>
                <li>
                  <strong>Change vs 30 minutes earlier:</strong>{" "}
                  {seriesLoading
                    ? "loading…"
                    : seriesMatched
                      ? pressureDeltaLine(pressureComparison)
                      : "—"}
                </li>
              </ul>
            )}
            <p className="brief-muted">
              Observation only — pressure change is not labeled as a leak.
            </p>
          </section>

          <section className="brief-section">
            <h4>Coordinated network context</h4>
            <ul className="brief-list">
              {BRIEF_CONTEXT_CHANNELS.map((ch) => (
                <ChannelLine
                  key={ch.id}
                  title={ch.title}
                  detail={ch.detail}
                  unit={ch.unit}
                  obs={snapshotMatched ? findObs(observations, ch.id) : null}
                  loading={snapshotLoading}
                />
              ))}
            </ul>
          </section>

          <section className="brief-section">
            <h4>Notes and share link</h4>
            <ul className="brief-list">
              <li>
                <strong>Operator note:</strong>{" "}
                {displayNote ? displayNote : "None"}
              </li>
              <li>
                <strong>Share URL:</strong>{" "}
                {shareUrl ? (
                  <span className="brief-url">{shareUrl}</span>
                ) : (
                  "None (save an investigation to attach a share link — optional)"
                )}
              </li>
            </ul>
            <label className="brief-note-field no-print">
              <span>Session note for this brief (not saved automatically)</span>
              <textarea
                rows={3}
                value={sessionNote}
                onChange={(e) => setSessionNote(e.target.value)}
                placeholder="Optional note included in the printed brief only"
                maxLength={1000}
              />
            </label>
          </section>

          <footer className="brief-footer">
            <p>{BRIEF_PRODUCT_LABEL}</p>
            <p>{BRIEF_CAUSE_LABEL}</p>
            <p className="brief-muted">
              Generated from live historical tables at the replay cursor. Evidence is
              not a frozen courtroom exhibit.
            </p>
          </footer>
        </article>
      )}
    </section>
  );
}
