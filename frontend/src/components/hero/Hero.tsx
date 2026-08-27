/**
 * The hero — one baked-monitor world, one crisp HTML message system, and the
 * copy.
 *
 * Desktop and wide tablet:
 *
 *   1  the world     the 16:9 loop, monitor narrative baked in    (HeroBackdrop)
 *   2  the product   a status stack beside the desk, at most      (HeroMessages)
 *                    three cards, synced to the video's clock
 *   3  the copy      headline, lead, calls to action
 *
 * Phone:
 *
 *   1  the world     the dedicated 9:16 loop, full bleed behind   (HeroBackdrop)
 *                    everything, same baked monitor narrative
 *   2  the product   one narrative card at a time                 (HeroMobileCard)
 *   3  the copy      headline, lead, calls to action
 *
 * The monitor's own states — REHEARSAL ACTIVE, VETOED, RECOMMENDED, AWAITING
 * APPROVAL — are pixels in the video now, not HTML: there is no terminal, no
 * clip-path glass, and no independent narrative timer. The message stack is
 * real HTML text, but it reads the video's own clock via
 * `useHeroVideoNarrative` so the two never drift apart.
 */

import { ArrowRight } from "lucide-react";
import { Link } from "react-router-dom";

import { HeroBackdrop } from "./HeroBackdrop";
import { HeroMessages } from "./HeroMessages";
import { HeroMobileCard } from "./HeroMobileCard";
import { useAmbientVideo, useMobileHero } from "./heroMedia";
import { HERO_DESCRIPTION, NARRATIVE_STEPS } from "./heroNarrative";
import { useHeroVideoNarrative } from "./useHeroNarrative";

export function Hero() {
  const mobile = useMobileHero();
  const ambient = useAmbientVideo();
  const { step, attach } = useHeroVideoNarrative(ambient);

  return (
    <section className="bp-hero" aria-labelledby="bp-hero-title">
      <div className="bp-hero__viewport">
        <div className="bp-hero__scene">
          <HeroBackdrop videoRef={attach} />
          {/* `--bp-px`, the source-pixel unit the stack's geometry is built
              from, is a custom property scoped to this box — the stack has to
              live inside it to inherit that value. */}
          {mobile ? null : <HeroMessages step={step} />}
        </div>
      </div>

      <div className="bp-hero__content">
        <div className="bp-hero__copy">
          <p className="bp-eyebrow">Evidence &gt; confidence</p>

          <h1 id="bp-hero-title" className="bp-display mt-4">
            Agents get branches <br />
            before they get permissions.
          </h1>

          <p className="bp-lead mt-5">
            Rehearse consequential agent actions across counterfactual worlds.
            Attack them, reproduce failures, and ask a human before changing
            reality.
          </p>

          <div className="bp-hero__ctas">
            <Link className="bp-cta bp-cta--primary" to="/runs">
              SEE LIVE DEMO
              <ArrowRight
                className="h-3.5 w-3.5"
                strokeWidth={2.5}
                aria-hidden="true"
              />
            </Link>
            <Link className="bp-cta bp-cta--ghost" to="/how-it-works">
              HOW IT WORKS
            </Link>
          </div>
        </div>
      </div>

      {mobile ? <HeroMobileCard step={step} /> : null}

      {/*
        The world, the status stack and the phone's card are all decorative
        and `aria-hidden`; they cycle, and announcing them would interrupt a
        screen reader every few seconds forever. These two blocks are the only
        copy of the story assistive technology gets, they never change, and
        they are true with no video and no animation at all.
      */}
      <div className="sr-only">
        <p>{HERO_DESCRIPTION}</p>
        <h2>What this run did</h2>
        <ol>
          {NARRATIVE_STEPS.map((entry) => (
            <li key={entry}>{entry}</li>
          ))}
        </ol>
      </div>
    </section>
  );
}
