/**
 * Optional four-step focus strip — scrolls to existing panels; does not
 * change replay cursor or invent completion state.
 */

const STEPS = [
  {
    id: "review-warning",
    label: "Review warning",
    targetId: "panel-warning",
    hint: "See when the pattern became unusual.",
  },
  {
    id: "inspect-sensor",
    label: "Inspect sensor",
    targetId: "panel-details",
    hint: "Check the measurements behind the warning.",
  },
  {
    id: "compare-conditions",
    label: "Compare conditions",
    targetId: "panel-conditions",
    hint: "Review supply, pump transfer, and tank level.",
  },
  {
    id: "prepare-brief",
    label: "Prepare brief",
    targetId: "panel-brief",
    hint: "Capture the evidence for review and handoff.",
  },
] as const;

function focusPanel(targetId: string) {
  const el = document.getElementById(targetId);
  if (!el) return;
  el.scrollIntoView({ behavior: "smooth", block: "start" });
  if (typeof el.focus === "function") {
    el.focus({ preventScroll: true });
  }
}

export default function InvestigationGuide() {
  return (
    <nav className="investigation-guide" aria-label="Investigation steps">
      <p className="investigation-guide-label">Investigation path</p>
      <ol className="investigation-guide-steps">
        {STEPS.map((step, index) => (
          <li key={step.id} className="investigation-guide-step">
            <button
              type="button"
              className="investigation-guide-btn"
              title={step.hint}
              aria-label={`${index + 1}. ${step.label}. ${step.hint}`}
              onClick={() => focusPanel(step.targetId)}
            >
              <span className="investigation-guide-num" aria-hidden="true">
                {index + 1}
              </span>
              <span className="investigation-guide-text">
                <span className="investigation-guide-title">{step.label}</span>
                <span className="investigation-guide-hint">{step.hint}</span>
              </span>
            </button>
          </li>
        ))}
      </ol>
    </nav>
  );
}
