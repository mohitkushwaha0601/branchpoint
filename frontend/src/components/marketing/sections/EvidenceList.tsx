/**
 * One world's evidence chain.
 *
 * Every row states its own authority in words — `machine_verifiable = true` or
 * `false` — because that single bit is the only thing in the system that can
 * disqualify a world, and a reader should never have to infer it from a colour
 * or from the `source` string. The engine itself never infers it either.
 *
 * Rows are expandable rather than always-open: at six rows the expected/observed
 * pairs are longer than the rest of the section combined, and the reader needs
 * the shape of the list before its contents. Expansion is a real `<button>`
 * inside each row, so it works by keyboard and by tap with no hover anywhere.
 */

import { useState } from "react";

import type { EvidenceRow } from "../../../data/canonicalIncident";

function Row({ row, open, onToggle }: {
  row: EvidenceRow;
  open: boolean;
  onToggle: () => void;
}) {
  const panelId = `bp-ev-${row.id}`;

  return (
    <li className="bp-ev" data-outcome={row.outcome} data-open={open ? "" : undefined}>
      <button
        type="button"
        className="bp-ev__head"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={onToggle}
      >
        <span className="bp-ev__mark" aria-hidden="true">
          {row.machineVerifiable ? "■" : "░"}
        </span>
        <span className="bp-ev__claim">{row.claim}</span>
        <span className="bp-ev__outcome">{row.outcome}</span>
        {row.severity === "INFO" ? null : (
          <span className="bp-ev__sev">{row.severity}</span>
        )}
        <span className="bp-ev__chev" aria-hidden="true">
          {open ? "−" : "+"}
        </span>
      </button>

      <div className="bp-ev__meta">
        <span className="bp-ev__auth" data-verified={row.machineVerifiable ? "" : undefined}>
          machine_verifiable = {String(row.machineVerifiable)}
        </span>
        <span className="bp-ev__kind">{row.kind}</span>
        {row.disqualifies ? (
          <span className="bp-ev__dq">DISQUALIFIES</span>
        ) : null}
      </div>

      {open ? (
        <dl className="bp-ev__body" id={panelId}>
          <dt>source</dt>
          <dd>{row.source}</dd>
          <dt>expected</dt>
          <dd>{row.expected}</dd>
          <dt>observed</dt>
          <dd>{row.observed}</dd>
          {row.artifact === undefined ? null : (
            <>
              <dt>artifact</dt>
              <dd>{row.artifact}</dd>
            </>
          )}
        </dl>
      ) : null}
    </li>
  );
}

export function EvidenceList({
  rows,
  note,
  superseded = [],
}: {
  rows: readonly EvidenceRow[];
  note: string;
  /**
   * Evidence the world produced that its verdict does not rest on. Behind a
   * disclosure rather than absent: the argument is not "α looked bad", it is
   * "α looked fine and was disqualified anyway", and deleting the rows that
   * make α look fine would quietly weaken it.
   */
  superseded?: readonly EvidenceRow[];
}) {
  // Open by id, not by index: switching worlds changes the list underneath and
  // an index would carry a stale row's disclosure across the swap.
  const [open, setOpen] = useState<string | null>(null);
  const [showSuperseded, setShowSuperseded] = useState(false);

  return (
    <div className="bp-evlist">
      <div className="bp-evlist__head">
        <span className="bp-evlist__title">EVIDENCE</span>
        <span className="bp-evlist__count">{rows.length}</span>
        <span className="bp-evlist__scope">bearing on the verdict</span>
      </div>

      <ul className="bp-evlist__rows">
        {rows.map((row) => (
          <Row
            key={row.id}
            row={row}
            open={open === row.id}
            onToggle={() => setOpen((prev) => (prev === row.id ? null : row.id))}
          />
        ))}
      </ul>

      <p className="bp-evlist__note">{note}</p>

      {superseded.length === 0 ? null : (
        <div className="bp-evlist__superseded">
          <button
            type="button"
            className="bp-evlist__more"
            aria-expanded={showSuperseded}
            onClick={() => setShowSuperseded((prev) => !prev)}
          >
            {showSuperseded ? "−" : "+"} {superseded.length} superseded row
            {superseded.length === 1 ? "" : "s"} — this world&rsquo;s execution
            suite, which passed
          </button>

          {showSuperseded ? (
            <ul className="bp-evlist__rows">
              {superseded.map((row) => (
                <Row
                  key={row.id}
                  row={row}
                  open={open === row.id}
                  onToggle={() =>
                    setOpen((prev) => (prev === row.id ? null : row.id))
                  }
                />
              ))}
            </ul>
          ) : null}
        </div>
      )}
    </div>
  );
}
