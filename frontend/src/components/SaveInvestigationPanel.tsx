import { useMemo, useState, type FormEvent } from "react";
import { ApiError, createInvestigation } from "../api";
import {
  DEFAULT_SOURCE_ID,
  NOTE_MAX,
  TITLE_MAX,
  shareUrlForId,
  type SavedInvestigation,
} from "../investigations";

interface Props {
  sensorId: string | null;
  cursor: string | null;
  windowStart: string | null;
  windowEnd: string | null;
  disabled?: boolean;
  onSaved: (row: SavedInvestigation) => void;
}

export default function SaveInvestigationPanel({
  sensorId,
  cursor,
  windowStart,
  windowEnd,
  disabled,
  onSaved,
}: Props) {
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [note, setNote] = useState("");
  const [status, setStatus] = useState<"idle" | "saving" | "error">("idle");
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<SavedInvestigation | null>(null);

  const canSave = Boolean(sensorId && cursor && windowStart && windowEnd) && !disabled;

  const shareUrl = useMemo(
    () => (saved ? shareUrlForId(saved.id) : null),
    [saved],
  );

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!sensorId || !cursor || !windowStart || !windowEnd) return;
    setStatus("saving");
    setError(null);
    try {
      const row = await createInvestigation({
        title: title.trim(),
        note: note.trim() ? note.trim() : null,
        sensor_id: sensorId,
        cursor,
        window_start: windowStart,
        window_end: windowEnd,
        source_id: DEFAULT_SOURCE_ID,
      });
      setSaved(row);
      setStatus("idle");
      onSaved(row);
    } catch (err) {
      setStatus("error");
      if (err instanceof ApiError && err.status === 429) {
        setError("Creation rate limit reached. Try again later.");
      } else {
        setError(err instanceof Error ? err.message : String(err));
      }
    }
  }

  async function copyShare() {
    if (!shareUrl) return;
    try {
      await navigator.clipboard.writeText(shareUrl);
    } catch {
      /* ignore — user can still select the text */
    }
  }

  return (
    <section className="save-investigation" aria-label="Save investigation">
      <div className="save-investigation-bar">
        <button
          type="button"
          className="btn btn-ghost"
          disabled={!canSave}
          onClick={() => {
            setOpen((v) => !v);
            setError(null);
          }}
        >
          {open ? "Close save form" : "Save investigation"}
        </button>
        {!sensorId && (
          <span className="save-investigation-hint">Select a sensor to save.</span>
        )}
      </div>

      {open && (
        <form className="save-investigation-form" onSubmit={onSubmit}>
          <p className="save-investigation-public" role="note">
            Shared notes are <strong>public</strong>. Do not enter private or sensitive
            data. Opaque link ids are not authentication. Saved views reload live
            historical measurements — they are not frozen evidence.
          </p>
          <label className="save-field">
            <span>Title</span>
            <input
              type="text"
              value={title}
              maxLength={TITLE_MAX}
              required
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Short public title"
            />
          </label>
          <label className="save-field">
            <span>Note (optional, plain text)</span>
            <textarea
              value={note}
              maxLength={NOTE_MAX}
              rows={3}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Public observation note only"
            />
          </label>
          <p className="save-investigation-meta">
            Sensor {sensorId} · cursor {cursor}
            <br />
            Window {windowStart} → {windowEnd}
            <br />
            Source {DEFAULT_SOURCE_ID}
          </p>
          <div className="save-actions">
            <button type="submit" className="btn" disabled={status === "saving" || !canSave}>
              {status === "saving" ? "Saving…" : "Save & get share link"}
            </button>
          </div>
          {error && (
            <p className="save-investigation-error" role="alert">
              {error}
            </p>
          )}
          {saved && shareUrl && (
            <div className="save-investigation-result">
              <p className="save-investigation-result-title">Saved</p>
              <p className="save-investigation-note-plain">{saved.title}</p>
              {saved.note ? (
                <p className="save-investigation-note-plain">{saved.note}</p>
              ) : null}
              <label className="save-field">
                <span>Shareable URL (opaque id — not a login)</span>
                <input type="text" readOnly value={shareUrl} onFocus={(e) => e.target.select()} />
              </label>
              <button type="button" className="btn btn-ghost" onClick={copyShare}>
                Copy link
              </button>
            </div>
          )}
        </form>
      )}
    </section>
  );
}
