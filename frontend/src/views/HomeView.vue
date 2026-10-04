<script setup lang="ts">
import { BookOpen, Library, PenLine, MailQuestionMark, Settings, UserRound, type LucideIcon } from '@lucide/vue'
import heroImage from '@/assets/home-hero.jpg'

interface FeatureCard {
  title: string
  desc: string
  to: string | null
  cta: string | null
  status: 'live' | 'soon'
  icon: LucideIcon
}

// Icons match the nav bar's (AppShell.vue) where the feature has a live
// route, so the shape is already familiar by the time someone reaches it.
const FEATURES: FeatureCard[] = [
  {
    title: 'Message Decoder',
    desc: "See what a message covers, what it leaves out, and what to ask next.",
    to: '/decode',
    cta: 'Decode message',
    status: 'live',
    icon: MailQuestionMark,
  },
  {
    title: 'Pattern Library',
    desc: 'Common workplace phrasings, and what they actually imply.',
    to: '/library',
    cta: 'Browse the library',
    status: 'live',
    icon: Library,
  },
  {
    title: 'Study & Flashcards',
    desc: 'Save what you learn. Review whenever you want',
    to: '/study',
    cta: 'Open Study',
    status: 'live',
    icon: BookOpen,
  },
  {
    title: 'Comfort Settings',
    desc: 'Switch to dark mode, color themes, and different text size & weight.',
    to: '/settings',
    cta: 'Adjust settings',
    status: 'live',
    icon: Settings,
  },
  {
    title: 'Message Composer',
    desc: 'See what a message might be missing before you send it.',
    to: '/compose',
    cta: 'Compose message',
    status: 'live',
    icon: PenLine,
  },
  {
    title: 'Accounts & Progress',
    desc: 'An optional account to keep your history across devices.',
    to: '/account',
    cta: 'Check account',
    status: 'live',
    icon: UserRound,
  },
]
</script>

<template>
  <section class="hero-section">
    <img :src="heroImage" alt="A team celebrating together around a meeting table" class="hero-bg-img" />
    <div class="hero-scrim" />
    <div class="hero-fade" />
    <div class="hero-inner">
      <div class="hero-panel">
        <h1 class="hero-title">Clear communication, <br />with no hidden "surprises".</h1>
        <p class="hero-subtitle">
          Analyse incoming messages to spot unstated expectations and subtext, and see
          the exact words each reading came from. Drafting help is coming next.
        </p>
        <div class="actions">
          <RouterLink to="/decode" class="btn btn--primary">Decode a message</RouterLink>
          <!-- Pointed at /compose, which is an unbuilt stub: the most
               prominent secondary action on the site led to a page reading
               "Coming Soon...". The library is a real destination that serves
               the same visitor - someone not yet ready to paste anything. -->
          <RouterLink to="/library" class="btn btn--secondary">Browse the pattern library</RouterLink>
        </div>
      </div>
    </div>
  </section>
  <div class="home">
    <section class="features">
      <h2>What we provide</h2>
      <div class="feature-grid">
        <component
          :is="feature.to ? 'RouterLink' : 'div'"
          v-for="feature in FEATURES"
          :key="feature.title"
          :to="feature.to ?? undefined"
          class="feature"
          :class="{ 'feature--soon': feature.status === 'soon' }"
        >
          <span class="feature__icon">
            <component :is="feature.icon" :size="20" :stroke-width="1.75" aria-hidden="true" />
          </span>
          <div class="feature__head">
            <strong>{{ feature.title }}</strong>
            <span v-if="feature.status === 'soon'" class="badge">Coming soon</span>
          </div>
          <span class="feature__desc">{{ feature.desc }}</span>
          <span v-if="feature.cta" class="feature__cta">{{ feature.cta }}</span>
        </component>
      </div>
    </section>

  </div>
</template>

<style scoped>
.home {
  display: flex;
  flex-direction: column;
  gap: 44px;
  padding-top: 8px;
  padding-bottom: 16px;
}

/* Breaks out of AppShell's centered, padded `.main__inner` (max-width
   1240px) so the photo runs edge-to-edge as full screen. 
   The negative top margin cancels out `.main`'s own
   top padding so the photo
   sits flush under the sticky header. */
.hero-section {
  position: relative;
  width: 100vw;
  margin-left: calc(50% - 50vw);
  margin-right: calc(50% - 50vw);
  margin-top: -32px;
  height: 72vh;
  min-height: 420px;
  display: flex;
  align-items: center;
  overflow: hidden;
}

.hero-bg-img {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  z-index: 0;
}

/* Darkens the photo so the white text stays readable over it.
   ---------------------------------------------------------------------------
   The first version faded 0.5 -> 0.1 across the full viewport, which is the
   same direction the text runs, so every line ended where the scrim was
   weakest. Measured against the composited pixels, the worst point under the
   title was 2.01:1 and under the subtitle 2.12:1, with roughly a fifth of each
   line below its threshold - over the pale shirt and table on the right.

   White on a photo is only as good as the darkest guarantee underneath it. At
   0.62 alpha even a pure-white pixel composites to 6.2:1, so the text band is
   held at or above that and the photo is only allowed to come back up in the
   right-hand margin, where no text reaches.

   The tiers exist because the text panel is a fixed 620px while the viewport
   is not: the narrower the window, the further across the gradient the text
   runs, so the fade has to flatten as the window shrinks. */
.hero-scrim {
  position: absolute;
  inset: 0;
  background: linear-gradient(
    90deg,
    rgba(0, 0, 0, 0.74) 0%,
    rgba(0, 0, 0, 0.66) 52%,
    rgba(0, 0, 0, 0.3) 82%,
    rgba(0, 0, 0, 0.12) 100%
  );
  z-index: 1;
}

@media (max-width: 1100px) {
  .hero-scrim {
    background: linear-gradient(
      90deg,
      rgba(0, 0, 0, 0.74) 0%,
      rgba(0, 0, 0, 0.68) 76%,
      rgba(0, 0, 0, 0.5) 100%
    );
  }
}

/* Below this the text runs the full width of the screen, so there is no
   longer a right-hand margin to give the photograph back. */
@media (max-width: 720px) {
  .hero-scrim {
    background: linear-gradient(90deg, rgba(0, 0, 0, 0.74) 0%, rgba(0, 0, 0, 0.68) 100%);
  }
}

/* Dissolves the photo into the page background instead of cutting to it on
   a hard edge. Sits above the scrim/image but below the text, and never
   intercepts clicks even if a tall viewport puts it near the buttons. */
.hero-fade {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  height: 140px;
  background: linear-gradient(to bottom, transparent, var(--color-bg));
  pointer-events: none;
  z-index: 1;
}

/* Re-establishes the same content column the rest of the page uses
   (AppShell's `.main__inner`/`.main`), now that the section itself has
   broken out of it. */
.hero-inner {
  position: relative;
  z-index: 2;
  width: 100%;
  max-width: 1240px;
  margin: 0 auto;
  padding: 0 24px;
}

.hero-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
  max-width: 620px;
  font-style: italic;
}

.hero-title {
  font-family: var(--font-serif);
  font-size: 42px;
  line-height: 1.14;
  font-weight: 500;
  letter-spacing: -0.02em;
  margin: 0;
  /* Literal white rather than a token: this text is never on the page
     surface, only ever on the scrim, which is the same darkness in both
     appearances. The shadow is margin against the photo's bright patches,
     not a style. */
  color: #ffffff;
  text-shadow: 0 1px 3px rgba(0, 0, 0, 0.5);
}

.hero-subtitle {
  margin: 0;
  font-size: 16.5px;
  line-height: 1.62;
  /* Was 0.88 alpha, which spent contrast this text could not afford. */
  color: #ffffff;
  text-shadow: 0 1px 3px rgba(0, 0, 0, 0.5);
}

@media (max-width: 720px) {
  .hero-title {
    font-size: 31px;
  }
}

.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  font-style: normal;
  margin-top: 4px;
}

.btn {
  padding: 13px 22px;
  border-radius: var(--radius-sm);
  font-size: 15px;
  font-weight: 500;
  cursor: pointer;
}

.moments {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 1px;
  background: var(--color-border-soft);
  border: 1px solid var(--color-border-soft);
  border-radius: 12px;
  overflow: hidden;
}

.moment {
  background: var(--color-surface-soft);
  padding: 20px 22px;
  display: flex;
  flex-direction: column;
  gap: 7px;
}

.moment strong {
  font-size: 15px;
  font-weight: 600;
  color: var(--color-text);
}

.moment span {
  font-size: 13.5px;
  line-height: 1.55;
  color: var(--color-text-muted);
}

.features h2 {
  font-family: var(--font-serif);
  font-size: 24px;
  font-weight: 500;
  letter-spacing: -0.015em;
  margin: 0 0 18px;
  color: var(--color-text);
}

.feature-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 14px;
}

.feature {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 18px 18px 20px;
  border: 1px solid var(--color-border-soft);
  border-radius: var(--radius-md);
  background: var(--color-surface);
  color: inherit;
}

a.feature:hover {
  border-color: var(--color-primary-soft-border);
  background: var(--color-primary-soft-bg);
}

.feature__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 38px;
  height: 38px;
  border-radius: 999px;
  background: var(--color-primary-soft-bg);
  color: var(--color-primary-strong-text);
  margin-bottom: 2px;
}

.feature--soon .feature__icon {
  background: var(--color-border-soft);
  color: var(--color-text-faint);
}

.feature--soon {
  background: var(--color-surface-soft);
}

.feature__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.feature__head strong {
  font-size: 14.5px;
  font-weight: 600;
  color: var(--color-text);
}

.badge {
  flex: 0 0 auto;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.02em;
  text-transform: uppercase;
  padding: 3px 8px;
  border-radius: 999px;
  background: var(--color-warn-bg);
  color: var(--color-warn-text);
  border: 1px solid var(--color-warn-border);
}

.feature__desc {
  font-size: 13.5px;
  line-height: 1.55;
  color: var(--color-text-muted);
}

.feature__cta {
  margin-top: auto;
  padding-top: 6px;
  font-size: 13px;
  font-weight: 600;
  color: var(--color-primary-strong-text);
}

.closing {
  border-top: 1px solid var(--color-border-soft);
  padding-top: 20px;
}

.closing p {
  margin: 0;
  font-size: 13.5px;
  color: var(--color-text-faint);
}

@media (max-width: 860px) {
  .hero-section {
    margin-top: -24px;
  }

  .feature-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 720px) {
  .moments {
    grid-template-columns: 1fr;
  }

  .feature-grid {
    grid-template-columns: 1fr;
  }
}
</style>
