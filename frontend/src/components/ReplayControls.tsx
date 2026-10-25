import { PRESENTER, WARNING_DEMO } from "../presenter";

interface Props {
  label: string;
  cursor: string;
  windowStart: string;
  windowEnd: string;
  playing: boolean;
  speed: number;
  stepSeconds: number;
  onTogglePlay: () => void;
  onStep: (direction: -1 | 1) => void;
  onSpeedChange: (speed: number) => void;
  onSeek: (ts: string) => void;
  onWindowStart: () => void;
  onMidpoint: () => void;
  onIllustrativeBookmark: () => void;
  onWarningDemoBookmark: () => void;
  index: number;
  totalSteps: number;
  timestamps: string[];
  midpointTs: string | null;
}

export default function ReplayControls({
  label,
  cursor,
  windowStart,
  windowEnd,
  playing,
  speed,
  onTogglePlay,
  onStep,
  onSpeedChange,
  onSeek,
  onWindowStart,
  onMidpoint,
  onIllustrativeBookmark,
  onWarningDemoBookmark,
  index,
  totalSteps,
  timestamps,
  midpointTs,
}: Props) {
  return (
    <div className="replay-bar">
      <div className="replay-label-row">
        <p className="replay-label">{label}</p>
        <span className="replay-cursor">{cursor}</span>
      </div>
      <p className="presenter-disclaimer">{PRESENTER.disclaimer}</p>
      <div className="presenter-bookmarks" role="group" aria-label="Jan 12 investigation preset">
        <span className="presenter-bookmarks-label">Jan 12 preset</span>
        <button type="button" className="btn btn-ghost-dark" onClick={onWindowStart}>
          Start 14:00
        </button>
        <button
          type="button"
          className="btn btn-accent"
          onClick={onIllustrativeBookmark}
          title={PRESENTER.bookmarks[1].note}
        >
          Illustrative Δ 15:00 (n54)
        </button>
        <button
          type="button"
          className="btn btn-ghost-dark"
          onClick={onMidpoint}
          disabled={!midpointTs}
        >
          Midpoint 15:30
        </button>
      </div>
      <div
        className="presenter-bookmarks warning-demo-bookmarks"
        role="group"
        aria-label="Experimental Method M warning demo"
      >
        <span className="presenter-bookmarks-label">Experimental warning demo</span>
        <button
          type="button"
          className="btn btn-ghost-dark"
          onClick={onWarningDemoBookmark}
          title={WARNING_DEMO.disclaimer}
        >
          Method M notify 23:00 (15 Jan)
        </button>
        <span className="warning-demo-hint">
          Hourly · not a confirmed leak · not localization
        </span>
      </div>
      <div className="replay-controls">
        <button type="button" className="btn" onClick={() => onStep(-1)} disabled={index <= 0}>
          −5 min
        </button>
        <button type="button" className="btn" onClick={onTogglePlay}>
          {playing ? "Pause" : "Play"}
        </button>
        <button
          type="button"
          className="btn"
          onClick={() => onStep(1)}
          disabled={index >= totalSteps - 1}
        >
          +5 min
        </button>
        <label className="speed-label">
          Speed
          <select value={speed} onChange={(e) => onSpeedChange(Number(e.target.value))}>
            <option value={0.5}>0.5×</option>
            <option value={1}>1×</option>
            <option value={2}>2×</option>
            <option value={4}>4×</option>
          </select>
        </label>
      </div>
      <input
        className="timeline"
        type="range"
        min={0}
        max={Math.max(totalSteps - 1, 0)}
        value={index}
        onChange={(e) => {
          const i = Number(e.target.value);
          if (timestamps[i]) onSeek(timestamps[i]);
        }}
        aria-label="Replay timeline"
      />
      <div className="timeline-ends">
        <span>{windowStart}</span>
        <span>{windowEnd}</span>
      </div>
    </div>
  );
}
