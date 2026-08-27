/**
 * The nine stage viewports.
 *
 * Each one is a different picture of the same run, and none of them is a card
 * grid. The rule they all follow: whatever is on screen is a state the system
 * actually has — `PREPARING`, `REPRODUCED`, `ADVERSARIAL_VETO`, `SUCCEEDED` —
 * not an illustration of one.
 *
 * ATTACK is the only stage with two acts, because replay is a step inside a
 * world's pipeline and not a run state. Promoting it to a peer stage would
 * flatten the exact distinction this page exists to teach, so instead the page
 * slows down there.
 */

import {
  APPROVAL,
  ATTACK,
  COMMIT,
  COMMIT_GATES,
  COMPARISON,
  COMPARISON_AXES,
  COMPARISON_VALUES,
  DECLARED_BOUNDS,
  INITIAL_REALITY,
  VERIFICATION,
  WITNESS_ORDER,
  WORLDS,
  type StageId,
} from "../../data/canonicalIncident";
import { AuthorityChip } from "../marketing/AuthorityChip";

type Values = typeof COMPARISON_VALUES;

/** A labelled plate. The page's smallest unit; used by several stages. */
function Plate({
  label,
  value,
  tone,
  note,
}: {
  label: string;
  value: string;
  tone?: "bad" | "good" | "warn";
  note?: string;
}) {
  return (
    <div className="bp-pt" data-tone={tone}>
      <span className="bp-pt__label">{label}</span>
      <span className="bp-pt__value">{value}</span>
      {note === undefined ? null : <span className="bp-pt__note">{note}</span>}
    </div>
  );
}

function Observe() {
  const m = INITIAL_REALITY.metrics;
  return (
    <div className="bp-stg__body">
      <div className="bp-stg__reality">
        <span className="bp-stg__reality-kind">PRODUCTION</span>
        <span className="bp-stg__reality-main">
          {INITIAL_REALITY.service} {INITIAL_REALITY.version}
        </span>
        <span className="bp-stg__reality-sub">
          {INITIAL_REALITY.flagKey} = {String(INITIAL_REALITY.flagEnabled)} ·{" "}
          {INITIAL_REALITY.replicas} replicas · orders schema{" "}
          {INITIAL_REALITY.ordersSchemaVersion}
        </span>
      </div>

      <div className="bp-stg__plates">
        <Plate label={m.errorRate.label} value={m.errorRate.value} tone="bad" />
        <Plate label={m.p95.label} value={m.p95.value} tone="bad" />
        <Plate
          label={m.affectedUsers.label}
          value={m.affectedUsers.value}
          tone="bad"
        />
        <Plate label={m.dailyCost.label} value={m.dailyCost.value} />
      </div>

      <p className="bp-stg__objective">
        <span className="bp-stg__objective-kind">OBJECTIVE</span>
        checkout_error_rate ≤ {DECLARED_BOUNDS.recoveryErrorRate} and
        checkout_p95_ms ≤ {DECLARED_BOUNDS.recoveryP95Ms}, without losing order
        data.
      </p>
    </div>
  );
}

function Plan() {
  return (
    <div className="bp-stg__body">
      <ol className="bp-stg__candidates">
        {WORLDS.map((world) => (
          <li key={world.id}>
            <span className="bp-stg__cand-glyph" aria-hidden="true">
              {world.glyph}
            </span>
            <span className="bp-stg__cand-kind">{world.action.kind}</span>
            <span className="bp-stg__cand-body">
              {world.action.parameter} {world.action.from} → {world.action.to}
            </span>
          </li>
        ))}
      </ol>

      <div className="bp-stg__badges">
        <span className="bp-stg__badge">planner: read-only</span>
        <span className="bp-stg__badge">sandbox: off</span>
        <span className="bp-stg__badge">subagents: none</span>
      </div>

      <p className="bp-stg__aside">
        Three candidates and no evidence. A plan is a proposal about the future;
        the evidence panel is still empty because nothing has been checked.
      </p>
    </div>
  );
}

function Fork() {
  return (
    <div className="bp-stg__body">
      <div className="bp-stg__twin">
        <span className="bp-stg__twin-label">PRODUCTION TWIN</span>
        <span className="bp-stg__twin-value">{INITIAL_REALITY.version}</span>
      </div>

      <div className="bp-stg__forks">
        {WORLDS.map((world) => (
          <div className="bp-stg__fork" key={world.id}>
            <span className="bp-stg__fork-glyph" aria-hidden="true">
              {world.glyph}
            </span>
            <span className="bp-stg__fork-id">{world.id}</span>
            <span className="bp-stg__fork-state">PREPARING</span>
            <span className="bp-stg__fork-ring">isolated snapshot</span>
          </div>
        ))}
      </div>

      <p className="bp-stg__aside">
        Isolation here is structural, not promised: a world holds its own frozen
        copy of production state, and no operation inside one has a path back to
        reality.
      </p>
    </div>
  );
}

function Execute() {
  return (
    <div className="bp-stg__body">
      <div className="bp-stg__outcomes">
        {WORLDS.map((world) => {
          const missed = world.id === "world_gamma";
          return (
            <div className="bp-stg__outcome" key={world.id} data-missed={missed ? "" : undefined}>
              <div className="bp-stg__outcome-head">
                <span aria-hidden="true">{world.glyph}</span>
                <span className="bp-stg__outcome-action">
                  {world.action.parameter} {world.action.from} →{" "}
                  {world.action.to}
                </span>
              </div>
              <div className="bp-stg__outcome-metrics">
                <span>{world.metrics.errorRate.value} error</span>
                <span>{world.metrics.p95.value} p95</span>
                <span>{world.metrics.costDelta.value}</span>
              </div>
              <div className="bp-stg__outcome-checks">
                healthy_checkout {missed ? "FAIL" : "PASS"} · recovery_slo{" "}
                {missed ? "FAIL" : "PASS"} · data_integrity PASS
              </div>
              {missed ? (
                <p className="bp-stg__outcome-note">
                  MEDIUM severity, kind TEST_RESULT. Not disqualifying — γ missed
                  the goal and is still safe.
                </p>
              ) : null}
            </div>
          );
        })}
      </div>

      <p className="bp-stg__aside">
        γ adds eight replicas and stops at a floor, because v2.41 is still
        deployed and the flag still routes through it. You cannot scale your way
        out of code that is still running.
      </p>
    </div>
  );
}

/** The only stage with two acts. */
function Attack() {
  return (
    <div className="bp-stg__body">
      <div className="bp-stg__act">
        <header className="bp-stg__act-head">
          <span className="bp-stg__act-num">act 1</span>
          <span className="bp-stg__act-name">hypothesis</span>
          <AuthorityChip band="EXPLORATORY" size="sm" suffix="· NO AUTHORITY" />
        </header>
        <p className="bp-stg__quote">&ldquo;{ATTACK.hypothesis}&rdquo;</p>
        <p className="bp-stg__act-meta">
          sandbox {ATTACK.sandboxId} · {ATTACK.execCalls} exec calls ·{" "}
          {ATTACK.hypotheses} hypothesis · machine_verifiable = false
        </p>
        <p className="bp-stg__act-note">{ATTACK.sandboxNote}</p>
      </div>

      <div className="bp-stg__rule">
        <span>CounterexampleSpec · typed · validated</span>
        <span className="bp-stg__rule-note">
          {ATTACK.spec.operation} · {ATTACK.spec.assertion.kind} · target{" "}
          {ATTACK.spec.target_world_id}
        </span>
      </div>

      <div className="bp-stg__act bp-stg__act--deterministic">
        <header className="bp-stg__act-head">
          <span className="bp-stg__act-num">act 2</span>
          <span className="bp-stg__act-name">replay</span>
          <AuthorityChip band="DETERMINISTIC" size="sm" suffix="· MAY VETO" />
        </header>
        <p className="bp-stg__act-meta">{ATTACK.replayNote}</p>
        <ul className="bp-stg__fails">
          <li>
            order_deserialization_or_compatibility — FAIL CRITICAL ·{" "}
            {WITNESS_ORDER.orderId} schema {WITNESS_ORDER.schemaVersion} vs{" "}
            {WITNESS_ORDER.supportedSchemaUnderRollback}
          </li>
          <li>
            payment_retry — FAIL CRITICAL · key{" "}
            <code>{WITNESS_ORDER.degradedKey}</code>
          </li>
        </ul>
        <p className="bp-stg__verdict">
          <span className="bp-stg__verdict-chip">{ATTACK.status}</span>
          <span className="bp-stg__verdict-rule">{ATTACK.vetoRule}</span>
        </p>
        <p className="bp-stg__verdict-final">WORLD α · {ATTACK.verdict}</p>
      </div>
    </div>
  );
}

function Compare() {
  return (
    <div className="bp-stg__body">
      <table className="bp-stg__matrix">
        <caption>
          The comparator&rsquo;s own axes. No score is computed at any point.
        </caption>
        <thead>
          <tr>
            <th scope="col">axis</th>
            {WORLDS.map((world) => (
              <th
                key={world.id}
                scope="col"
                data-rejected={world.verdict === "VETOED" ? "" : undefined}
              >
                <span aria-hidden="true">{world.glyph}</span> {world.shortName}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {COMPARISON_AXES.map((axis) => (
            <tr key={axis.key}>
              <th scope="row">{axis.field}</th>
              {WORLDS.map((world) => (
                <td
                  key={world.id}
                  data-rejected={world.verdict === "VETOED" ? "" : undefined}
                >
                  {COMPARISON_VALUES[world.id as keyof Values][axis.key]}
                </td>
              ))}
            </tr>
          ))}
          <tr>
            <th scope="row">rank</th>
            {WORLDS.map((world) => (
              <td key={world.id}>
                {COMPARISON.ranks[world.id as keyof Values]}
              </td>
            ))}
          </tr>
        </tbody>
      </table>

      <p className="bp-stg__aside">
        α carries {COMPARISON.rejectionReason} and was removed before ranking
        began. β is rank 1 — a deterministic recommendation, and not permission.
      </p>
    </div>
  );
}

function Approve() {
  return (
    <div className="bp-stg__body">
      <div className="bp-stg__binding">
        <dl>
          <dt>run</dt>
          <dd>{APPROVAL.runId}</dd>
          <dt>world</dt>
          <dd>{APPROVAL.worldId}</dd>
          <dt>action</dt>
          <dd>
            {APPROVAL.actionId} · {APPROVAL.actionType}
          </dd>
          <dt>parameters</dt>
          <dd>
            {APPROVAL.reviewedFlagKey} {APPROVAL.from} → {APPROVAL.to}
          </dd>
          <dt>fingerprint</dt>
          <dd className="bp-stg__fp">
            sha256 {APPROVAL.reviewedFingerprint.slice(0, 16)}…
            {APPROVAL.reviewedFingerprint.slice(-4)}
          </dd>
        </dl>
      </div>

      <ul className="bp-stg__bindings">
        {APPROVAL.bindings.map((binding) => (
          <li key={binding.key}>
            <span aria-hidden="true">✓</span> {binding.label}
          </li>
        ))}
      </ul>

      <p className="bp-stg__aside">
        Approval adds no evidence — the chain on the right is unchanged. What it
        adds is permission, for one action identified by content hash. The live
        version of this card, which you can break yourself, is on the landing
        page.
      </p>
    </div>
  );
}

function Commit() {
  return (
    <div className="bp-stg__body">
      <ol className="bp-stg__gates">
        {COMMIT_GATES.map((gate, index) => (
          <li key={gate.key}>
            <span className="bp-stg__gate-num">{index + 1}</span>
            <span className="bp-stg__gate-label">{gate.label}</span>
            <span className="bp-stg__gate-detail">{gate.detail}</span>
          </li>
        ))}
      </ol>

      <p className="bp-stg__mutation">
        <span className="bp-stg__mutation-key">{COMMIT.mutation.key}</span>
        <span className="bp-stg__mutation-change">
          {COMMIT.mutation.from} → {COMMIT.mutation.to}
        </span>
        <span className="bp-stg__mutation-cap">capability spent</span>
      </p>

      <p className="bp-stg__aside">{COMMIT.capabilityNote}</p>
    </div>
  );
}

function Verify() {
  return (
    <div className="bp-stg__body">
      <table className="bp-stg__pairs">
        <caption>
          Re-read from production by a component that never saw the commit
          report.
        </caption>
        <thead>
          <tr>
            <th scope="col">check</th>
            <th scope="col">expected</th>
            <th scope="col">actual</th>
          </tr>
        </thead>
        <tbody>
          {VERIFICATION.map((pair) => (
            <tr key={pair.key}>
              <th scope="row">{pair.key}</th>
              <td>{pair.expected}</td>
              <td>
                {pair.actual} <span aria-hidden="true">✓</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <p className="bp-stg__succeeded">RUN SUCCEEDED</p>

      <p className="bp-stg__aside">
        Approval changed permission. Verification proved reality. Only the second
        one is evidence about the world.
      </p>
    </div>
  );
}

const VIEWPORTS: Record<StageId, () => React.JSX.Element> = {
  observe: Observe,
  plan: Plan,
  fork: Fork,
  execute: Execute,
  attack: Attack,
  compare: Compare,
  approve: Approve,
  commit: Commit,
  verify: Verify,
};

export function StageViewport({ id }: { id: StageId }) {
  const Body = VIEWPORTS[id];
  return <Body />;
}
